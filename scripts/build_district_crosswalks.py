from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import shapefile
from shapely.geometry import shape
from shapely.strtree import STRtree


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
CROSSWALK_DIR = DATA_ROOT / "crosswalks"
COUNTY_GEOJSON = DATA_ROOT / "census" / "tl_2020_39_county20.geojson"
VTD20_SHP = DATA_ROOT / "census" / "tl_2020_39_vtd20" / "tl_2020_39_vtd20.shp"
MIN_AREA_WEIGHT = 1e-9


SPECS = [
    {
        "key": "congressional_2022",
        "source": DATA_ROOT / "2022" / "20221108__oh__general__precinct.csv",
        "offices": {"U.S. House"},
        "output": CROSSWALK_DIR / "precinct_to_cd118.csv",
    },
    {
        "key": "congressional_2024",
        "source": DATA_ROOT / "2024" / "20241105__oh__general__precinct.csv",
        "offices": {"U.S. House"},
        "output": CROSSWALK_DIR / "precinct_to_cd119.csv",
    },
    {
        "key": "congressional_2026",
        "source": DATA_ROOT / "2024" / "20241105__oh__general__precinct.csv",
        "offices": {"U.S. House"},
        "output": CROSSWALK_DIR / "precinct_to_cd2026_sl2025_95.csv",
        "geometry_geojson": DATA_ROOT / "tileset" / "oh_cd2026.geojson",
        "geometry_field": "DISTRICT",
    },
    {
        "key": "state_house_2022",
        "source": DATA_ROOT / "2022" / "20221108__oh__general__precinct.csv",
        "offices": {"State House"},
        "output": CROSSWALK_DIR / "precinct_to_2022_state_house.csv",
        "geometry_geojson": DATA_ROOT / "tileset" / "oh_state_house_2022.geojson",
        "geometry_field": "SLDLST",
    },
    {
        "key": "state_house_2024",
        "source": DATA_ROOT / "2024" / "20241105__oh__general__precinct.csv",
        "offices": {"State House"},
        "output": CROSSWALK_DIR / "precinct_to_2024_state_house.csv",
        "geometry_geojson": DATA_ROOT / "tileset" / "oh_state_house_2024.geojson",
        "geometry_field": "SLDLST",
    },
    {
        "key": "state_senate_2022",
        "source": DATA_ROOT / "2022" / "20221108__oh__general__precinct.csv",
        "fallback_sources": [
            DATA_ROOT / "2024" / "20241105__oh__general__precinct.csv",
        ],
        "offices": {"State Senate"},
        "output": CROSSWALK_DIR / "precinct_to_2022_state_senate.csv",
        "geometry_geojson": DATA_ROOT / "tileset" / "oh_state_senate_2022.geojson",
        "geometry_field": "SLDUST",
    },
    {
        "key": "state_senate_2024",
        "source": DATA_ROOT / "2024" / "20241105__oh__general__precinct.csv",
        "fallback_sources": [
            DATA_ROOT / "2022" / "20221108__oh__general__precinct.csv",
        ],
        "offices": {"State Senate", "State Senate (Unexpired Term Ending 12/31/2026)"},
        "output": CROSSWALK_DIR / "precinct_to_2024_state_senate.csv",
        "geometry_geojson": DATA_ROOT / "tileset" / "oh_state_senate_2024.geojson",
        "geometry_field": "SLDUST",
    },
]


def normalize_whitespace(value: str) -> str:
    return " ".join((value or "").strip().split())


def normalize_precinct_key(row: dict[str, str]) -> str:
    county = normalize_whitespace(row.get("county", "")).upper()
    precinct_code = normalize_whitespace(row.get("precinct code", "") or row.get("precinct_code", "")).upper()
    if not county or not precinct_code:
        return ""
    return f"{county} - {precinct_code}"


def parse_votes(raw: str) -> float:
    raw = (raw or "").strip().replace(",", "")
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def normalize_district_number(value: str) -> str:
    raw = normalize_whitespace(value)
    if not raw:
        return ""
    if raw.isdigit():
        return str(int(raw))
    return raw


def district_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def load_source_totals(source: Path, offices: set[str]) -> tuple[dict[str, dict[str, float]], dict[tuple[str, str], dict[str, str]], dict]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    labels: dict[tuple[str, str], dict[str, str]] = {}
    row_count = 0
    matched_row_count = 0

    with source.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            row_count += 1
            office = normalize_whitespace(row.get("office", ""))
            if office not in offices:
                continue

            matched_row_count += 1
            precinct_key = normalize_precinct_key(row)
            district_num = normalize_whitespace(row.get("district", ""))
            if not precinct_key or not district_num:
                continue

            votes = parse_votes(row.get("votes", ""))
            totals[precinct_key][district_num] += votes
            labels[(precinct_key, district_num)] = {
                "precinct": precinct_key,
                "precinct_key": precinct_key,
                "district_num": district_num,
                "district_code": district_num,
            }

    summary = {
        "source": str(source),
        "input_row_count": row_count,
        "matched_office_row_count": matched_row_count,
        "precinct_count_with_any_district_rows": len(totals),
    }
    return totals, labels, summary


def pick_positive_totals(
    primary_totals: dict[str, dict[str, float]],
    fallback_totals_list: list[dict[str, dict[str, float]]],
) -> tuple[dict[str, dict[str, float]], int]:
    final: dict[str, dict[str, float]] = {}
    supplemented = 0
    all_precincts = set(primary_totals.keys())
    for fallback_totals in fallback_totals_list:
        all_precincts.update(fallback_totals.keys())

    for precinct_key in sorted(all_precincts):
        primary_positive = {district: total for district, total in primary_totals.get(precinct_key, {}).items() if total > 0}
        if primary_positive:
            final[precinct_key] = primary_positive
            continue

        selected = None
        for fallback_totals in fallback_totals_list:
            fallback_positive = {district: total for district, total in fallback_totals.get(precinct_key, {}).items() if total > 0}
            if fallback_positive:
                selected = fallback_positive
                supplemented += 1
                break
        if selected:
            final[precinct_key] = selected

    return final, supplemented


def load_crosswalk_rows(primary_sources: list[Path], fallback_sources: list[Path], offices: set[str]) -> tuple[list[dict[str, str]], dict]:
    row_count = 0
    matched_row_count = 0
    source_summaries = []
    primary_totals_merged: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    primary_labels: dict[tuple[str, str], dict[str, str]] = {}
    fallback_totals_list: list[dict[str, dict[str, float]]] = []
    fallback_labels_list: list[dict[tuple[str, str], dict[str, str]]] = []

    for source in primary_sources:
        source_totals, source_labels, source_summary = load_source_totals(source, offices)
        row_count += source_summary["input_row_count"]
        matched_row_count += source_summary["matched_office_row_count"]
        source_summaries.append(source_summary)
        for precinct_key, district_totals in source_totals.items():
            for district_num, votes in district_totals.items():
                primary_totals_merged[precinct_key][district_num] += votes
        primary_labels.update(source_labels)

    for source in fallback_sources:
        source_totals, source_labels, source_summary = load_source_totals(source, offices)
        row_count += source_summary["input_row_count"]
        matched_row_count += source_summary["matched_office_row_count"]
        source_summaries.append(source_summary)
        fallback_totals_list.append(source_totals)
        fallback_labels_list.append(source_labels)

    positive_totals, supplemented_precincts = pick_positive_totals(primary_totals_merged, fallback_totals_list)
    labels = dict(primary_labels)
    for fallback_labels in fallback_labels_list:
        labels.update(fallback_labels)

    output_rows: list[dict[str, str]] = []
    split_precincts = 0
    zero_total_precincts = 0

    all_precincts = set(primary_totals_merged.keys())
    for fallback_totals in fallback_totals_list:
        all_precincts.update(fallback_totals.keys())

    for precinct_key in sorted(all_precincts):
        positive = positive_totals.get(precinct_key, {})
        if not positive:
            zero_total_precincts += 1
            continue

        if len(positive) > 1:
            split_precincts += 1

        denom = sum(positive.values())
        for district_num, total_votes in sorted(positive.items(), key=lambda item: district_sort_key(item[0])):
            base = dict(labels[(precinct_key, district_num)])
            base["area_weight"] = f"{(total_votes / denom):.10f}".rstrip("0").rstrip(".")
            base["vote_weight"] = base["area_weight"]
            base["source_votes"] = f"{total_votes:.10f}".rstrip("0").rstrip(".")
            output_rows.append(base)

    summary = {
        "sources": [str(source) for source in [*primary_sources, *fallback_sources]],
        "offices": sorted(offices),
        "input_row_count": row_count,
        "matched_office_row_count": matched_row_count,
        "precinct_count_with_any_district_rows": len(all_precincts),
        "crosswalk_row_count": len(output_rows),
        "split_precinct_count": split_precincts,
        "zero_total_precinct_count": zero_total_precincts,
        "supplemented_precinct_count": supplemented_precincts,
        "source_summaries": source_summaries,
    }
    return output_rows, summary


def load_target_precinct_keys(source: Path) -> set[str]:
    out: set[str] = set()
    with source.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            precinct_key = normalize_precinct_key(row)
            if precinct_key:
                out.add(precinct_key)
    return out


def load_county_fips_lookup() -> dict[str, str]:
    data = json.load(COUNTY_GEOJSON.open("r", encoding="utf-8"))
    return {
        str(feature["properties"]["COUNTYFP"]).zfill(3): str(feature["properties"]["NAME"]).strip()
        for feature in data.get("features", [])
    }


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
            precinct_key = f"{county.upper()} - {vtd_code[-3:]}"
            geom = shape(shape_record.shape.__geo_interface__)
            if geom.is_empty:
                continue
            if not geom.is_valid:
                geom = geom.buffer(0)
            out[precinct_key] = geom
    finally:
        reader.close()
    return out


def load_district_geometries(path: Path, district_field: str) -> tuple[list, dict[int, str]]:
    data = json.load(path.open("r", encoding="utf-8"))
    geometries = []
    district_by_geom_id: dict[int, str] = {}
    for feature in data.get("features", []):
        properties = feature.get("properties", {})
        district_num = normalize_district_number(str(properties.get(district_field, "")))
        geom = shape(feature.get("geometry"))
        if not district_num or geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
        geometries.append(geom)
        district_by_geom_id[id(geom)] = district_num
    return geometries, district_by_geom_id


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


def merge_geometry_and_fallback_rows(
    precinct_keys: set[str],
    geometry_rows: list[dict[str, str]],
    fallback_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    geometry_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    fallback_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in geometry_rows:
        geometry_by_key[row["precinct_key"]].append(row)
    for row in fallback_rows:
        fallback_by_key[row["precinct_key"]].append(row)

    merged: list[dict[str, str]] = []
    geometry_precinct_count = 0
    fallback_precinct_count = 0
    missing_precinct_count = 0

    for precinct_key in sorted(precinct_keys):
        if geometry_by_key.get(precinct_key):
            merged.extend(geometry_by_key[precinct_key])
            geometry_precinct_count += 1
        elif fallback_by_key.get(precinct_key):
            merged.extend(fallback_by_key[precinct_key])
            fallback_precinct_count += 1
        else:
            missing_precinct_count += 1

    return merged, {
        "geometry_precinct_count": geometry_precinct_count,
        "fallback_precinct_count": fallback_precinct_count,
        "missing_precinct_count": missing_precinct_count,
    }


def load_crosswalk_rows_for_spec(spec: dict) -> tuple[list[dict[str, str]], dict]:
    primary_sources = [spec["source"]]
    fallback_sources = spec.get("fallback_sources", [])
    vote_rows, vote_summary = load_crosswalk_rows(primary_sources, fallback_sources, spec["offices"])

    geometry_geojson = spec.get("geometry_geojson")
    district_field = spec.get("geometry_field")
    if not geometry_geojson or not district_field:
        return vote_rows, vote_summary

    precinct_keys = load_target_precinct_keys(spec["source"])
    county_by_fips = load_county_fips_lookup()
    precinct_geometries = load_vtd20_geometries(county_by_fips)
    district_geometries, district_by_geom_id = load_district_geometries(geometry_geojson, district_field)
    geometry_rows, geometry_summary = build_geometry_rows(
        precinct_keys,
        precinct_geometries,
        district_geometries,
        district_by_geom_id,
    )
    merged_rows, merge_summary = merge_geometry_and_fallback_rows(precinct_keys, geometry_rows, vote_rows)
    summary = {
        **vote_summary,
        "method": "geometry_overlap_with_vote_fallback",
        "geometry_geojson": str(geometry_geojson),
        "geometry_field": district_field,
        "target_precinct_count": len(precinct_keys),
        "vtd_geometry_precinct_count": len(precinct_geometries),
        "crosswalk_row_count": len(merged_rows),
        **geometry_summary,
        **merge_summary,
        "vote_fallback_summary": vote_summary,
    }
    return merged_rows, summary


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "precinct",
        "precinct_key",
        "district_num",
        "district_code",
        "area_weight",
        "vote_weight",
        "source_votes",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    CROSSWALK_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for spec in SPECS:
        rows, summary = load_crosswalk_rows_for_spec(spec)
        write_csv(spec["output"], rows)
        summary["output"] = str(spec["output"])
        manifest[spec["key"]] = summary

    manifest_path = CROSSWALK_DIR / "district_crosswalk_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
