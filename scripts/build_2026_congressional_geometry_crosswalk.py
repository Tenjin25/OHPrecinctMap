from __future__ import annotations

import csv
import glob
import json
from collections import defaultdict
from pathlib import Path

import shapefile
from shapely.geometry import shape
from shapely.strtree import STRtree


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
INPUT_PRECINCT_CSV = DATA_ROOT / "2024" / "20241105__oh__general__precinct.csv"
COUNTY_GEOJSON = DATA_ROOT / "census" / "tl_2020_39_county20.geojson"
VTD20_SHP = DATA_ROOT / "census" / "tl_2020_39_vtd20" / "tl_2020_39_vtd20.shp"
VTD10_DIR = DATA_ROOT / "census" / "tl_2010_39_vtd10"
DISTRICT_GEOJSON = DATA_ROOT / "tileset" / "oh_cd2026.geojson"
OUTPUT_CSV = DATA_ROOT / "crosswalks" / "precinct_to_cd2026_sl2025_95.csv"
OUTPUT_MANIFEST = DATA_ROOT / "crosswalks" / "district_crosswalk_manifest.json"
MIN_AREA_WEIGHT = 1e-9


def normalize_whitespace(value: str) -> str:
    return " ".join((value or "").strip().split())


def normalize_precinct_key(county: str, precinct_code: str) -> str:
    county_norm = normalize_whitespace(county).upper()
    code_norm = normalize_whitespace(precinct_code).upper()
    if not county_norm or not code_norm:
        return ""
    return f"{county_norm} - {code_norm}"


def load_target_precinct_keys() -> set[str]:
    out: set[str] = set()
    with INPUT_PRECINCT_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = normalize_precinct_key(row.get("county", ""), row.get("precinct code", ""))
            if key:
                out.add(key)
    return out


def load_county_fips_lookup() -> dict[str, str]:
    data = json.load(COUNTY_GEOJSON.open("r", encoding="utf-8"))
    return {
        str(feature["properties"]["COUNTYFP"]).zfill(3): str(feature["properties"]["NAME"]).strip()
        for feature in data.get("features", [])
    }


def load_district_geometries() -> tuple[list, dict[int, str]]:
    data = json.load(DISTRICT_GEOJSON.open("r", encoding="utf-8"))
    geometries = []
    district_by_geom_id: dict[int, str] = {}
    for feature in data.get("features", []):
        district_num = str(feature.get("properties", {}).get("DISTRICT", "")).strip()
        geom = shape(feature.get("geometry"))
        if not district_num or geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
        geometries.append(geom)
        district_by_geom_id[id(geom)] = district_num
    return geometries, district_by_geom_id


def load_vtd20_geometries(county_by_fips: dict[str, str]) -> dict[str, object]:
    out: dict[str, object] = {}
    if not VTD20_SHP.exists():
        return out

    reader = shapefile.Reader(str(VTD20_SHP))
    try:
        fields = [field[0] for field in reader.fields[1:]]
        county_idx = fields.index("COUNTYFP20")
        vtd_idx = fields.index("VTDST20")
        for shape_record in reader.iterShapeRecords():
            county_fips = str(shape_record.record[county_idx]).zfill(3)
            county = county_by_fips.get(county_fips, "").strip()
            if not county:
                continue
            vtd_code = str(shape_record.record[vtd_idx]).strip().upper()
            if not vtd_code or len(vtd_code) < 3:
                continue
            precinct_key = normalize_precinct_key(county, vtd_code[-3:])
            if not precinct_key:
                continue
            geom = shape(shape_record.shape.__geo_interface__)
            if geom.is_empty:
                continue
            if not geom.is_valid:
                geom = geom.buffer(0)
            out[precinct_key] = geom
    finally:
        reader.close()
    return out


def load_vtd10_geometries(county_by_fips: dict[str, str]) -> dict[str, object]:
    out: dict[str, object] = {}
    for shp_path in sorted(glob.glob(str(VTD10_DIR / "*.shp"))):
        reader = shapefile.Reader(shp_path)
        try:
            records = reader.shapeRecords()
            if not records:
                continue
            county_fips = str(records[0].record[1]).zfill(3)
            county = county_by_fips.get(county_fips, "").strip()
            if not county:
                continue
            for shape_record in records:
                vtd_code = str(shape_record.record[2]).strip().upper()
                if not vtd_code or len(vtd_code) < 3:
                    continue
                precinct_key = normalize_precinct_key(county, vtd_code[-3:])
                if not precinct_key:
                    continue
                geom = shape(shape_record.shape.__geo_interface__)
                if geom.is_empty:
                    continue
                if not geom.is_valid:
                    geom = geom.buffer(0)
                out[precinct_key] = geom
        finally:
            reader.close()
    return out


def load_fallback_rows() -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    with OUTPUT_CSV.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = normalize_whitespace(row.get("precinct_key", "")).upper()
            if key:
                out[key].append(dict(row))
    return out


def build_geometry_rows(
    precinct_keys: set[str],
    precinct_geometries: dict[str, object],
    district_geometries: list,
    district_by_geom_id: dict[int, str],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    tree = STRtree(district_geometries)
    rows: list[dict[str, str]] = []
    matched_precincts = 0
    split_precincts = 0
    no_overlap_precincts = 0

    for precinct_key in sorted(precinct_keys):
        geom = precinct_geometries.get(precinct_key)
        if geom is None or geom.is_empty:
            continue
        matched_precincts += 1
        overlaps: list[tuple[str, float]] = []
        candidate_indices = tree.query(geom)
        for idx in candidate_indices:
            district_geom = district_geometries[int(idx)]
            inter = geom.intersection(district_geom)
            area = float(inter.area) if not inter.is_empty else 0.0
            if area <= 0:
                continue
            district_num = district_by_geom_id[id(district_geom)]
            overlaps.append((district_num, area))

        if not overlaps:
            no_overlap_precincts += 1
            continue

        if len(overlaps) > 1:
            split_precincts += 1

        denom = sum(area for _, area in overlaps)
        for district_num, area in sorted(overlaps, key=lambda item: (int(item[0]) if item[0].isdigit() else item[0])):
            weight = area / denom if denom > 0 else 0.0
            if weight <= MIN_AREA_WEIGHT or area <= 0:
                continue
            rows.append(
                {
                    "precinct": precinct_key,
                    "precinct_key": precinct_key,
                    "district_num": district_num,
                    "district_code": district_num,
                    "area_weight": f"{weight:.10f}".rstrip("0").rstrip("."),
                    "vote_weight": f"{weight:.10f}".rstrip("0").rstrip("."),
                    "source_votes": f"{area:.10f}".rstrip("0").rstrip("."),
                }
            )

    return rows, {
        "geometry_matched_precinct_count": matched_precincts,
        "geometry_split_precinct_count": split_precincts,
        "geometry_no_overlap_precinct_count": no_overlap_precincts,
    }


def merge_rows(
    precinct_keys: set[str],
    geometry_rows: list[dict[str, str]],
    fallback_rows: dict[str, list[dict[str, str]]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    geometry_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in geometry_rows:
        geometry_by_key[row["precinct_key"]].append(row)

    merged: list[dict[str, str]] = []
    geometry_precinct_count = 0
    fallback_precinct_count = 0
    missing_precinct_count = 0

    for precinct_key in sorted(precinct_keys):
        if geometry_by_key.get(precinct_key):
            merged.extend(geometry_by_key[precinct_key])
            geometry_precinct_count += 1
            continue
        if fallback_rows.get(precinct_key):
            merged.extend(fallback_rows[precinct_key])
            fallback_precinct_count += 1
            continue
        missing_precinct_count += 1

    return merged, {
        "geometry_precinct_count": geometry_precinct_count,
        "fallback_precinct_count": fallback_precinct_count,
        "missing_precinct_count": missing_precinct_count,
    }


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "precinct",
        "precinct_key",
        "district_num",
        "district_code",
        "area_weight",
        "vote_weight",
        "source_votes",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def update_manifest(summary: dict) -> None:
    manifest = {}
    if OUTPUT_MANIFEST.exists():
        manifest = json.load(OUTPUT_MANIFEST.open("r", encoding="utf-8"))
    manifest["congressional_2026"] = summary
    with OUTPUT_MANIFEST.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)


def main() -> int:
    precinct_keys = load_target_precinct_keys()
    county_by_fips = load_county_fips_lookup()
    district_geometries, district_by_geom_id = load_district_geometries()
    precinct_geometries = load_vtd20_geometries(county_by_fips)
    geometry_source = "vtd20"
    if not precinct_geometries:
        precinct_geometries = load_vtd10_geometries(county_by_fips)
        geometry_source = "vtd10"
    fallback_rows = load_fallback_rows()

    geometry_rows, geometry_summary = build_geometry_rows(
        precinct_keys,
        precinct_geometries,
        district_geometries,
        district_by_geom_id,
    )
    merged_rows, merge_summary = merge_rows(precinct_keys, geometry_rows, fallback_rows)
    write_rows(OUTPUT_CSV, merged_rows)

    summary = {
        "sources": [
            str(INPUT_PRECINCT_CSV),
            str(VTD20_SHP if geometry_source == "vtd20" else VTD10_DIR),
            str(DISTRICT_GEOJSON),
        ],
        "method": "geometry_overlap_with_fallback",
        "geometry_source": geometry_source,
        "offices": ["U.S. House"],
        "target_precinct_count": len(precinct_keys),
        "vtd_geometry_precinct_count": len(precinct_geometries),
        "crosswalk_row_count": len(merged_rows),
        "output": str(OUTPUT_CSV),
        **geometry_summary,
        **merge_summary,
    }
    update_manifest(summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
