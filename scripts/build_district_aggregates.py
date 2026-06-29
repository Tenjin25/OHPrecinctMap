from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from build_county_aggregates import normalize_office, parse_votes
from build_county_aggregates_json import PARTY_MAP, color_for_margin


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


PRECINCT_GENERAL_FILES = {
    2006: DATA_DIR / "2006" / "20061107__OH__general__precinct.csv",
    2010: DATA_DIR / "2010" / "20101102__oh__general__precinct.csv",
    2014: DATA_DIR / "2014" / "20141104__oh__general__precinct.csv",
    2016: DATA_DIR / "2016" / "20161108__oh__general__precinct.csv",
    2018: DATA_DIR / "2018" / "20181106__oh__general__precinct.csv",
    2020: DATA_DIR / "2020" / "20201103__oh__general__precinct.csv",
    2022: DATA_DIR / "2022" / "20221108__oh__general__precinct.csv",
    2024: DATA_DIR / "2024" / "20241105__oh__general__precinct.csv",
}


LINES_SPECS = {
    2022: {
        "dir": DATA_DIR / "district_contests",
        "legacy_json": DATA_DIR / "oh_district_results_2022_lines.json",
        "crosswalks": {
            "congressional": DATA_DIR / "crosswalks" / "precinct_to_cd118.csv",
            "state_house": DATA_DIR / "crosswalks" / "precinct_to_2022_state_house.csv",
            "state_senate": DATA_DIR / "crosswalks" / "precinct_to_2022_state_senate.csv",
        },
    },
    2024: {
        "dir": DATA_DIR / "district_contests_2024_lines",
        "crosswalks": {
            "congressional": DATA_DIR / "crosswalks" / "precinct_to_cd119.csv",
            "state_house": DATA_DIR / "crosswalks" / "precinct_to_2024_state_house.csv",
            "state_senate": DATA_DIR / "crosswalks" / "precinct_to_2024_state_senate.csv",
        },
    },
    2026: {
        "dir": DATA_DIR / "district_contests_2026_lines",
        "crosswalks": {
            "congressional": DATA_DIR / "crosswalks" / "precinct_to_cd2026_sl2025_95.csv",
        },
    },
}

STATEWIDE_CONTEST_TYPES = {
    "president",
    "us_senate",
    "governor",
    "attorney_general",
    "auditor",
    "secretary_of_state",
    "treasurer",
}
DISTRICT_SPECIFIC_CONTEST_TYPES = {"us_house", "state_house", "state_senate"}


def clean_text(value: str) -> str:
    return " ".join((value or "").split())


def slugify(value: str) -> str:
    value = clean_text(value).lower()
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def normalize_district_number(value: str) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    if re.fullmatch(r"\d+(\.0+)?", raw):
        return str(int(float(raw)))
    return raw


def contest_type_for_row(office: str, district: str) -> str:
    office = normalize_office(office)
    if office == "President/Vice President":
        return "president"
    if office == "U.S. Senate":
        return "us_senate"
    if office == "Governor/Lieutenant Governor":
        return "governor"
    if office == "Attorney General":
        return "attorney_general"
    if office == "Auditor of State":
        return "auditor"
    if office == "Secretary of State":
        return "secretary_of_state"
    if office == "Treasurer of State":
        return "treasurer"
    if office == "U.S. House":
        return "us_house"
    if office == "State House" or office == "State Representative":
        return "state_house"
    if office.startswith("State Senate") or office == "State Senator":
        return "state_senate"
    if office.startswith("Chief Justice of the Supreme Court"):
        return slugify(office)
    if office.startswith("Justice of the Supreme Court"):
        return slugify(office)
    return ""


def precinct_key_from_row(row: dict[str, str]) -> str:
    county = clean_text(row.get("county", "")).upper()
    code = clean_text(
        row.get("precinct code", "")
        or row.get("precinct_code", "")
        or row.get("precinct", "")
    ).upper()
    if not county or not code:
        return ""
    return f"{county} - {code}"


def load_crosswalk(path: Path) -> dict[str, list[tuple[str, float]]]:
    mapping: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            precinct_key = clean_text(row.get("precinct_key", "")).upper()
            district_num = normalize_district_number(row.get("district_num", "") or row.get("district_code", ""))
            weight_raw = clean_text(row.get("area_weight", "") or row.get("vote_weight", "0"))
            if not precinct_key or not district_num or not weight_raw:
                continue
            weight = float(weight_raw)
            if weight <= 0:
                continue
            mapping[precinct_key].append((district_num, weight))
    return mapping


def empty_result() -> dict[str, float | str]:
    return {
        "dem_votes": 0.0,
        "rep_votes": 0.0,
        "other_votes": 0.0,
        "total_votes": 0.0,
        "dem_candidate": "",
        "rep_candidate": "",
    }


def finalize_result(entry: dict[str, float | str]) -> dict[str, float | str]:
    dem_votes = int(round(float(entry.get("dem_votes", 0) or 0)))
    rep_votes = int(round(float(entry.get("rep_votes", 0) or 0)))
    other_votes = int(round(float(entry.get("other_votes", 0) or 0)))
    total_votes = dem_votes + rep_votes + other_votes
    margin = rep_votes - dem_votes
    margin_pct = (margin / total_votes * 100.0) if total_votes else 0.0
    winner = "REP" if margin > 0 else "DEM" if margin < 0 else "TIE"
    return {
        **entry,
        "dem_votes": dem_votes,
        "rep_votes": rep_votes,
        "other_votes": other_votes,
        "total_votes": total_votes,
        "margin": margin,
        "margin_pct": margin_pct,
        "winner": winner,
        "color": color_for_margin(margin_pct, winner),
    }


def aggregate_scopes_year(
    year: int,
    precinct_file: Path,
    crosswalks: dict[str, dict[str, list[tuple[str, float]]]],
) -> tuple[dict[str, dict[str, dict]], dict[str, dict]]:
    contests_by_scope: dict[str, dict[str, dict[str, dict]]] = {
        scope: defaultdict(lambda: defaultdict(empty_result))
        for scope in crosswalks.keys()
    }
    unmatched_precincts_by_scope: dict[str, set[str]] = {scope: set() for scope in crosswalks.keys()}
    matched_rows_by_scope: dict[str, int] = {scope: 0 for scope in crosswalks.keys()}
    allocated_rows_by_scope: dict[str, int] = {scope: 0 for scope in crosswalks.keys()}

    with precinct_file.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            office = normalize_office(row.get("office", ""))
            contest_type = contest_type_for_row(office, row.get("district", ""))
            if not contest_type:
                continue
            if contest_type in DISTRICT_SPECIFIC_CONTEST_TYPES:
                if year not in {2022, 2024}:
                    continue
                if contest_type == "us_house":
                    target_scopes = ["congressional"] if "congressional" in crosswalks else []
                elif contest_type == "state_house":
                    target_scopes = ["state_house"] if "state_house" in crosswalks else []
                else:
                    target_scopes = ["state_senate"] if "state_senate" in crosswalks else []
            elif contest_type in STATEWIDE_CONTEST_TYPES or contest_type.startswith("chief_justice_of_the_supreme_court") or contest_type.startswith("justice_of_the_supreme_court"):
                target_scopes = list(crosswalks.keys())
            else:
                continue

            precinct_key = precinct_key_from_row(row)
            if not precinct_key:
                continue

            candidate = clean_text(row.get("candidate", ""))
            if not candidate:
                continue

            votes = parse_votes(row.get("votes", "0"))
            if votes <= 0:
                continue

            party = PARTY_MAP.get(clean_text(row.get("party", "")).upper(), "")
            for scope in target_scopes:
                district_targets = crosswalks[scope].get(precinct_key)
                if not district_targets:
                    unmatched_precincts_by_scope[scope].add(precinct_key)
                    continue

                matched_rows_by_scope[scope] += 1
                for district_num, weight in district_targets:
                    allocated_rows_by_scope[scope] += 1
                    bucket = contests_by_scope[scope][contest_type][district_num]
                    weighted_votes = votes * weight
                    if party == "DEM":
                        bucket["dem_votes"] += weighted_votes
                        if not bucket["dem_candidate"]:
                            bucket["dem_candidate"] = candidate
                    elif party == "REP":
                        bucket["rep_votes"] += weighted_votes
                        if not bucket["rep_candidate"]:
                            bucket["rep_candidate"] = candidate
                    else:
                        bucket["other_votes"] += weighted_votes
                    bucket["total_votes"] += weighted_votes

    payloads_by_scope: dict[str, dict[str, dict]] = {}
    summaries_by_scope: dict[str, dict] = {}
    for scope, contests in contests_by_scope.items():
        payloads: dict[str, dict] = {}
        for contest_type, results in contests.items():
            finalized_results = {}
            for district_num, entry in sorted(results.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]):
                if float(entry.get("total_votes", 0) or 0) <= 0:
                    continue
                finalized_results[str(district_num)] = finalize_result(entry)
            if not finalized_results:
                continue
            payloads[contest_type] = {
                "scope": scope,
                "contest_type": contest_type,
                "year": year,
                "general": {"results": finalized_results},
            }
        payloads_by_scope[scope] = payloads
        summaries_by_scope[scope] = {
            "scope": scope,
            "year": year,
            "contest_count": len(payloads),
            "matched_precinct_rows": matched_rows_by_scope[scope],
            "allocated_district_rows": allocated_rows_by_scope[scope],
            "unmatched_precinct_count": len(unmatched_precincts_by_scope[scope]),
        }

    return payloads_by_scope, summaries_by_scope


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def build_for_lines_year(lines_year: int, spec: dict) -> tuple[list[dict], dict]:
    out_dir = spec["dir"]
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    crosswalks = {scope: load_crosswalk(path) for scope, path in spec["crosswalks"].items()}
    manifest_entries: list[dict] = []
    legacy_results_by_year: dict[str, dict] = {}
    summaries: dict[str, dict] = {}

    for year, precinct_file in PRECINCT_GENERAL_FILES.items():
        if not precinct_file.exists():
            continue
        legacy_year_bucket = legacy_results_by_year.setdefault(str(year), {})
        payloads_by_scope, summaries_by_scope = aggregate_scopes_year(year, precinct_file, crosswalks)
        for scope, crosswalk in crosswalks.items():
            payloads = payloads_by_scope.get(scope, {})
            summary = summaries_by_scope.get(scope, {})
            summaries[f"{scope}_{year}"] = summary
            for contest_type, payload in payloads.items():
                filename = f"{scope}_{contest_type}_{year}.json"
                write_json(out_dir / filename, payload)
                manifest_entries.append(
                    {
                        "scope": scope,
                        "contest_type": contest_type,
                        "year": year,
                        "file": filename,
                        "rows": len(payload["general"]["results"]),
                        "lines_year": lines_year,
                    }
                )
                if lines_year == 2022:
                    legacy_year_bucket.setdefault(scope, {})[contest_type] = payload

    manifest_entries.sort(key=lambda entry: (entry["scope"], entry["contest_type"], entry["year"]))
    write_json(out_dir / "manifest.json", {"files": manifest_entries})

    if lines_year == 2022 and spec.get("legacy_json"):
        legacy_path = spec["legacy_json"]
        if legacy_path.exists():
            legacy_path.unlink()
        write_json(
            legacy_path,
            {
                "metadata": {
                    "state": "Ohio",
                    "scope": "district",
                    "lines_year": 2022,
                    "years": sorted(legacy_results_by_year.keys()),
                },
                "results_by_year": legacy_results_by_year,
            },
        )

    return manifest_entries, summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Ohio district contest slices.")
    parser.add_argument(
        "--lines",
        nargs="*",
        type=int,
        choices=sorted(LINES_SPECS.keys()),
        default=sorted(LINES_SPECS.keys()),
        help="District line vintages to build.",
    )
    args = parser.parse_args()

    build_summary = {}
    for lines_year in args.lines:
        spec = LINES_SPECS[lines_year]
        manifest_entries, summaries = build_for_lines_year(lines_year, spec)
        build_summary[str(lines_year)] = {
            "manifest_entries": len(manifest_entries),
            "dir": str(spec["dir"]),
            "summaries": summaries,
        }

    write_json(DATA_DIR / "district_aggregate_build_summary.json", build_summary)
    print(json.dumps(build_summary, indent=2))


if __name__ == "__main__":
    main()
