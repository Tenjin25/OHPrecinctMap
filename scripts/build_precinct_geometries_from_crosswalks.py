from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import shapefile
from shapely.geometry import Point, mapping, shape

from build_district_aggregates import LINES_SPECS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
CENSUS_DIR = DATA_ROOT / "census"
PRECINCT_DIR = DATA_ROOT / "precincts"
COUNTY_GEOJSON = CENSUS_DIR / "tl_2020_39_county20.geojson"
VTD20_SHP = CENSUS_DIR / "tl_2020_39_vtd20" / "tl_2020_39_vtd20.shp"
OUTPUT_PRECINCTS = PRECINCT_DIR / "oh_precincts.geojson"
OUTPUT_CENTROIDS = PRECINCT_DIR / "oh_precinct_centroids.geojson"
OUTPUT_MANIFEST = PRECINCT_DIR / "manifest.json"

PROPERTY_SPECS = {
    (2022, "congressional"): ("cd_2022", "cd_2022_splits"),
    (2024, "congressional"): ("cd_2024", "cd_2024_splits"),
    (2026, "congressional"): ("cd_2026", "cd_2026_splits"),
    (2022, "state_house"): ("sldl_2022", "sldl_2022_splits"),
    (2024, "state_house"): ("sldl_2024", "sldl_2024_splits"),
    (2022, "state_senate"): ("sldu_2022", "sldu_2022_splits"),
    (2024, "state_senate"): ("sldu_2024", "sldu_2024_splits"),
}


def clean_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def normalize_precinct_key(county: str, precinct_code: str) -> str:
    county_norm = clean_text(county).upper()
    precinct_norm = clean_text(precinct_code).upper()
    if not county_norm or not precinct_norm:
        return ""
    return f"{county_norm} - {precinct_norm}"


def district_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build precinct polygon and centroid GeoJSON artifacts from crosswalk-backed precinct keys."
    )
    parser.add_argument(
        "--lines",
        nargs="*",
        type=int,
        choices=sorted(LINES_SPECS.keys()),
        default=sorted(LINES_SPECS.keys()),
        help="Line vintages whose crosswalk precinct universe should be included.",
    )
    return parser.parse_args()


def load_county_fips_lookup() -> dict[str, str]:
    payload = json.load(COUNTY_GEOJSON.open("r", encoding="utf-8"))
    return {
        str(feature["properties"]["COUNTYFP"]).zfill(3): clean_text(str(feature["properties"]["NAME"]))
        for feature in payload.get("features", [])
    }


def load_crosswalk(path: Path) -> dict[str, list[tuple[str, float]]]:
    mapping_by_precinct: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            precinct_key = clean_text(row.get("precinct_key", "")).upper()
            district_num = clean_text(row.get("district_num", "") or row.get("district_code", ""))
            weight_raw = clean_text(row.get("area_weight", "") or row.get("vote_weight", "0"))
            if not precinct_key or not district_num or not weight_raw:
                continue
            try:
                weight = float(weight_raw)
            except ValueError:
                continue
            if weight <= 0:
                continue
            mapping_by_precinct[precinct_key].append((district_num, weight))
    return mapping_by_precinct


def choose_primary_district(rows: list[tuple[str, float]]) -> str:
    ordered = sorted(rows, key=lambda item: (-float(item[1]), district_sort_key(item[0])))
    return ordered[0][0] if ordered else ""


def format_split_string(rows: list[tuple[str, float]]) -> str:
    ordered = sorted(rows, key=lambda item: district_sort_key(item[0]))
    return "|".join(f"{district}:{weight:.6f}".rstrip("0").rstrip(".") for district, weight in ordered)


def collect_crosswalk_metadata(lines_years: list[int]) -> tuple[set[str], dict[str, dict[str, str]], dict[str, dict]]:
    precinct_keys: set[str] = set()
    properties_by_precinct: dict[str, dict[str, str]] = defaultdict(dict)
    manifest_summary: dict[str, dict] = {}

    for lines_year in lines_years:
        spec = LINES_SPECS[lines_year]
        for scope, path in sorted(spec.get("crosswalks", {}).items()):
            if not path.exists():
                manifest_summary[f"{lines_year}_{scope}"] = {
                    "path": str(path),
                    "exists": False,
                    "precinct_count": 0,
                    "row_count": 0,
                }
                continue

            mapping_by_precinct = load_crosswalk(path)
            row_count = sum(len(rows) for rows in mapping_by_precinct.values())
            manifest_summary[f"{lines_year}_{scope}"] = {
                "path": str(path),
                "exists": True,
                "precinct_count": len(mapping_by_precinct),
                "row_count": row_count,
            }

            field_names = PROPERTY_SPECS.get((lines_year, scope))
            if not field_names:
                continue

            primary_field, split_field = field_names
            for precinct_key, rows in mapping_by_precinct.items():
                precinct_keys.add(precinct_key)
                properties_by_precinct[precinct_key][primary_field] = choose_primary_district(rows)
                properties_by_precinct[precinct_key][split_field] = format_split_string(rows)

    return precinct_keys, properties_by_precinct, manifest_summary


def load_vtd20_precinct_geometries(county_by_fips: dict[str, str]) -> dict[str, dict]:
    geometries: dict[str, dict] = {}
    reader = shapefile.Reader(str(VTD20_SHP))
    try:
        fields = [field[0] for field in reader.fields[1:]]
        county_idx = fields.index("COUNTYFP20")
        code_idx = fields.index("VTDST20")
        name_idx = fields.index("NAME20") if "NAME20" in fields else None
        for shape_record in reader.iterShapeRecords():
            county_fips = str(shape_record.record[county_idx]).zfill(3)
            county_name = county_by_fips.get(county_fips, "")
            precinct_code = clean_text(str(shape_record.record[code_idx])).upper()
            if not county_name or not precinct_code or len(precinct_code) < 3:
                continue

            precinct_code = precinct_code[-3:]
            precinct_key = normalize_precinct_key(county_name, precinct_code)
            if not precinct_key:
                continue

            geom = shape(shape_record.shape.__geo_interface__)
            if geom.is_empty:
                continue
            if not geom.is_valid:
                geom = geom.buffer(0)
            if geom.is_empty:
                continue

            precinct_full_name = ""
            if name_idx is not None:
                precinct_full_name = clean_text(str(shape_record.record[name_idx]))

            geometries[precinct_key] = {
                "geometry": geom,
                "county_name": county_name,
                "precinct_code": precinct_code,
                "precinct_full_name": precinct_full_name,
            }
    finally:
        reader.close()
    return geometries


def build_base_properties(precinct_key: str, geometry_record: dict, crosswalk_properties: dict[str, str]) -> dict[str, str]:
    county_name = geometry_record["county_name"]
    precinct_code = geometry_record["precinct_code"]
    precinct_full_name = geometry_record.get("precinct_full_name", "")
    county_norm = clean_text(county_name).upper()
    precinct_name = f"{county_name} - {precinct_code}"
    base = {
        "county_nam": county_name,
        "county_norm": county_norm,
        "prec_id": precinct_code,
        "precinct_name": precinct_name,
        "precinct_norm": precinct_key,
        "precinct_full_name": precinct_full_name,
    }
    base.update(crosswalk_properties)
    return base


def feature(geometry, properties: dict) -> dict:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": mapping(geometry),
    }


def write_geojson(path: Path, features: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)
        fh.write("\n")


def main() -> int:
    args = parse_args()
    county_by_fips = load_county_fips_lookup()
    precinct_keys, crosswalk_properties, crosswalk_summary = collect_crosswalk_metadata(args.lines)
    geometry_by_precinct = load_vtd20_precinct_geometries(county_by_fips)

    precinct_features: list[dict] = []
    centroid_features: list[dict] = []
    matched_precincts: list[str] = []
    unmatched_precincts: list[str] = []

    for precinct_key in sorted(precinct_keys):
        geometry_record = geometry_by_precinct.get(precinct_key)
        if not geometry_record:
            unmatched_precincts.append(precinct_key)
            continue

        properties = build_base_properties(
            precinct_key,
            geometry_record,
            crosswalk_properties.get(precinct_key, {}),
        )
        polygon = geometry_record["geometry"]
        centroid = polygon.representative_point()
        if not isinstance(centroid, Point):
            centroid = polygon.centroid

        precinct_features.append(feature(polygon, properties))
        centroid_features.append(feature(centroid, properties))
        matched_precincts.append(precinct_key)

    write_geojson(OUTPUT_PRECINCTS, precinct_features)
    write_geojson(OUTPUT_CENTROIDS, centroid_features)

    manifest = {
        "generated_by": "scripts/build_precinct_geometries_from_crosswalks.py",
        "lines_years": sorted(args.lines),
        "sources": {
            "county_geojson": str(COUNTY_GEOJSON),
            "vtd20_shapefile": str(VTD20_SHP),
            "crosswalks": crosswalk_summary,
        },
        "outputs": {
            "precincts": str(OUTPUT_PRECINCTS),
            "centroids": str(OUTPUT_CENTROIDS),
        },
        "summary": {
            "crosswalk_precinct_count": len(precinct_keys),
            "geometry_precinct_count": len(geometry_by_precinct),
            "matched_precinct_count": len(matched_precincts),
            "unmatched_precinct_count": len(unmatched_precincts),
        },
        "unmatched_precincts": unmatched_precincts,
    }
    OUTPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_MANIFEST.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
