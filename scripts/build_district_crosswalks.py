from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
CROSSWALK_DIR = DATA_ROOT / "crosswalks"


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
    },
    {
        "key": "state_house_2022",
        "source": DATA_ROOT / "2022" / "20221108__oh__general__precinct.csv",
        "offices": {"State House"},
        "output": CROSSWALK_DIR / "precinct_to_2022_state_house.csv",
    },
    {
        "key": "state_house_2024",
        "source": DATA_ROOT / "2024" / "20241105__oh__general__precinct.csv",
        "offices": {"State House"},
        "output": CROSSWALK_DIR / "precinct_to_2024_state_house.csv",
    },
    {
        "key": "state_senate_2022",
        "source": DATA_ROOT / "2022" / "20221108__oh__general__precinct.csv",
        "fallback_sources": [
            DATA_ROOT / "2024" / "20241105__oh__general__precinct.csv",
        ],
        "offices": {"State Senate"},
        "output": CROSSWALK_DIR / "precinct_to_2022_state_senate.csv",
    },
    {
        "key": "state_senate_2024",
        "source": DATA_ROOT / "2024" / "20241105__oh__general__precinct.csv",
        "fallback_sources": [
            DATA_ROOT / "2022" / "20221108__oh__general__precinct.csv",
        ],
        "offices": {"State Senate", "State Senate (Unexpired Term Ending 12/31/2026)"},
        "output": CROSSWALK_DIR / "precinct_to_2024_state_senate.csv",
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
        for district_num, total_votes in sorted(positive.items(), key=lambda item: (int(item[0]) if item[0].isdigit() else item[0])):
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
        primary_sources = [spec["source"]]
        fallback_sources = spec.get("fallback_sources", [])
        rows, summary = load_crosswalk_rows(primary_sources, fallback_sources, spec["offices"])
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
