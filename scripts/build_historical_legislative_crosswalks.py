from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from shapely.geometry import shape
from shapely.strtree import STRtree


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
CROSSWALK_DIR = DATA_ROOT / "crosswalks"
COUNTY_GEOJSON = DATA_ROOT / "census" / "tl_2020_39_county20.geojson"
VTD10_GEOJSON = DATA_ROOT / "census" / "tl_2010_39_vtd10" / "tl_2010_39_vtd10.geojson"
MIN_AREA_WEIGHT = 1e-9

SPECS = [
    {
        "key": "state_house_2022",
        "district_geojson": DATA_ROOT / "tileset" / "oh_state_house_2022.geojson",
        "district_field": "SLDLST",
        "fallback_crosswalk": CROSSWALK_DIR / "precinct_to_2022_state_house.csv",
        "outputs": {
            2010: CROSSWALK_DIR / "precinct_to_2022_state_house_2010_vtd10.csv",
            2012: CROSSWALK_DIR / "precinct_to_2022_state_house_2012_vtd10.csv",
            2014: CROSSWALK_DIR / "precinct_to_2022_state_house_2014_vtd10.csv",
            2016: CROSSWALK_DIR / "precinct_to_2022_state_house_2016_vtd10.csv",
            2018: CROSSWALK_DIR / "precinct_to_2022_state_house_2018_vtd10.csv",
            2020: CROSSWALK_DIR / "precinct_to_2022_state_house_2020_vtd10.csv",
        },
    },
    {
        "key": "state_house_2024",
        "district_geojson": DATA_ROOT / "tileset" / "oh_state_house_2024.geojson",
        "district_field": "SLDLST",
        "fallback_crosswalk": CROSSWALK_DIR / "precinct_to_2024_state_house.csv",
        "outputs": {
            2010: CROSSWALK_DIR / "precinct_to_2024_state_house_2010_vtd10.csv",
            2012: CROSSWALK_DIR / "precinct_to_2024_state_house_2012_vtd10.csv",
            2014: CROSSWALK_DIR / "precinct_to_2024_state_house_2014_vtd10.csv",
            2016: CROSSWALK_DIR / "precinct_to_2024_state_house_2016_vtd10.csv",
            2018: CROSSWALK_DIR / "precinct_to_2024_state_house_2018_vtd10.csv",
            2020: CROSSWALK_DIR / "precinct_to_2024_state_house_2020_vtd10.csv",
        },
    },
    {
        "key": "state_senate_2022",
        "district_geojson": DATA_ROOT / "tileset" / "oh_state_senate_2022.geojson",
        "district_field": "SLDUST",
        "fallback_crosswalk": CROSSWALK_DIR / "precinct_to_2022_state_senate.csv",
        "outputs": {
            2010: CROSSWALK_DIR / "precinct_to_2022_state_senate_2010_vtd10.csv",
            2012: CROSSWALK_DIR / "precinct_to_2022_state_senate_2012_vtd10.csv",
            2014: CROSSWALK_DIR / "precinct_to_2022_state_senate_2014_vtd10.csv",
            2016: CROSSWALK_DIR / "precinct_to_2022_state_senate_2016_vtd10.csv",
            2018: CROSSWALK_DIR / "precinct_to_2022_state_senate_2018_vtd10.csv",
            2020: CROSSWALK_DIR / "precinct_to_2022_state_senate_2020_vtd10.csv",
        },
    },
    {
        "key": "state_senate_2024",
        "district_geojson": DATA_ROOT / "tileset" / "oh_state_senate_2024.geojson",
        "district_field": "SLDUST",
        "fallback_crosswalk": CROSSWALK_DIR / "precinct_to_2024_state_senate.csv",
        "outputs": {
            2010: CROSSWALK_DIR / "precinct_to_2024_state_senate_2010_vtd10.csv",
            2012: CROSSWALK_DIR / "precinct_to_2024_state_senate_2012_vtd10.csv",
            2014: CROSSWALK_DIR / "precinct_to_2024_state_senate_2014_vtd10.csv",
            2016: CROSSWALK_DIR / "precinct_to_2024_state_senate_2016_vtd10.csv",
            2018: CROSSWALK_DIR / "precinct_to_2024_state_senate_2018_vtd10.csv",
            2020: CROSSWALK_DIR / "precinct_to_2024_state_senate_2020_vtd10.csv",
        },
    },
]

PRECINCT_FILES = {
    2010: DATA_ROOT / "2010" / "20101102__oh__general__precinct.csv",
    2012: DATA_ROOT / "2012" / "20121106__oh__general__precinct.csv",
    2014: DATA_ROOT / "2014" / "20141104__oh__general__precinct.csv",
    2016: DATA_ROOT / "2016" / "20161108__oh__general__precinct.csv",
    2018: DATA_ROOT / "2018" / "20181106__oh__general__precinct.csv",
    2020: DATA_ROOT / "2020" / "20201103__oh__general__precinct.csv",
}


def normalize_whitespace(value: str) -> str:
    return " ".join((value or "").strip().split())


def normalize_precinct_key(county: str, precinct_code: str) -> str:
    county_norm = normalize_whitespace(county).upper()
    code_norm = normalize_whitespace(precinct_code).upper()
    if not county_norm or not code_norm:
        return ""
    return f"{county_norm} - {code_norm}"


def district_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if str(value).isdigit() else (1, str(value))


def load_county_fips_lookup() -> dict[str, str]:
    data = json.load(COUNTY_GEOJSON.open("r", encoding="utf-8"))
    return {
        str(feature["properties"]["COUNTYFP"]).zfill(3): str(feature["properties"]["NAME"]).strip()
        for feature in data.get("features", [])
    }


def load_target_precinct_keys(source: Path) -> set[str]:
    out: set[str] = set()
    with source.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = normalize_precinct_key(
                row.get("county", ""),
                row.get("precinct code", "") or row.get("precinct_code", "") or row.get("precinct", ""),
            )
            if key:
                out.add(key)
    return out


def load_vtd10_geometries(county_by_fips: dict[str, str]) -> dict[str, object]:
    data = json.load(VTD10_GEOJSON.open("r", encoding="utf-8"))
    out: dict[str, object] = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        county = county_by_fips.get(str(props.get("COUNTYFP10")).zfill(3), "").strip()
        vtd_code = str(props.get("VTDST10", "")).strip().upper()
        if not county or not vtd_code or len(vtd_code) < 3:
            continue
        precinct_key = normalize_precinct_key(county, vtd_code[-3:])
        geom = shape(feature.get("geometry"))
        if not precinct_key or geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
        out[precinct_key] = geom
    return out


def load_district_geometries(path: Path, district_field: str) -> tuple[list, dict[int, str]]:
    data = json.load(path.open("r", encoding="utf-8"))
    geometries = []
    district_by_geom_id: dict[int, str] = {}
    for feature in data.get("features", []):
        district_num = str(feature.get("properties", {}).get(district_field, "")).strip()
        geom = shape(feature.get("geometry"))
        if not district_num or geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
        geometries.append(geom)
        district_by_geom_id[id(geom)] = district_num
    return geometries, district_by_geom_id


def load_fallback_rows(path: Path) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
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
        for idx in tree.query(geom):
            district_geom = district_geometries[int(idx)]
            inter = geom.intersection(district_geom)
            area = float(inter.area) if not inter.is_empty else 0.0
            if area <= 0:
                continue
            overlaps.append((district_by_geom_id[id(district_geom)], area))

        if not overlaps:
            no_overlap_precincts += 1
            continue
        if len(overlaps) > 1:
            split_precincts += 1

        denom = sum(area for _, area in overlaps)
        for district_num, area in sorted(overlaps, key=lambda item: district_sort_key(item[0])):
            weight = area / denom if denom > 0 else 0.0
            if weight <= MIN_AREA_WEIGHT:
                continue
            weight_str = f"{weight:.10f}".rstrip("0").rstrip(".")
            rows.append(
                {
                    "precinct": precinct_key,
                    "precinct_key": precinct_key,
                    "district_num": district_num,
                    "district_code": district_num,
                    "area_weight": weight_str,
                    "vote_weight": weight_str,
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


def main() -> None:
    county_by_fips = load_county_fips_lookup()
    precinct_geometries = load_vtd10_geometries(county_by_fips)
    build_summary: dict[str, dict] = {}

    for spec in SPECS:
        district_geometries, district_by_geom_id = load_district_geometries(
            spec["district_geojson"], spec["district_field"]
        )
        fallback_rows = load_fallback_rows(spec["fallback_crosswalk"])

        for year, output_path in spec["outputs"].items():
            source = PRECINCT_FILES[year]
            precinct_keys = load_target_precinct_keys(source)
            geometry_rows, geometry_summary = build_geometry_rows(
                precinct_keys,
                precinct_geometries,
                district_geometries,
                district_by_geom_id,
            )
            merged_rows, merge_summary = merge_rows(precinct_keys, geometry_rows, fallback_rows)
            write_rows(output_path, merged_rows)

            summary_key = f"{spec['key']}_{year}_vtd10"
            build_summary[summary_key] = {
                "key": spec["key"],
                "year": year,
                "source": str(source),
                "district_geojson": str(spec["district_geojson"]),
                "fallback_crosswalk": str(spec["fallback_crosswalk"]),
                "output": str(output_path),
                "target_precinct_count": len(precinct_keys),
                "vtd10_geometry_precinct_count": len(precinct_geometries),
                "crosswalk_row_count": len(merged_rows),
                **geometry_summary,
                **merge_summary,
            }

    manifest_path = CROSSWALK_DIR / "historical_legislative_crosswalk_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(build_summary, fh, indent=2)
        fh.write("\n")
    print(json.dumps(build_summary, indent=2))


if __name__ == "__main__":
    main()
