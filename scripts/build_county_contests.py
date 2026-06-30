import csv
import json
from pathlib import Path

from build_county_aggregates import include_office, normalize_office, parse_votes
from build_county_aggregates_json import (
    EXCLUDED_COUNTY_OFFICES,
    PARTY_MAP,
    YEAR_FILES,
    clean_text,
    color_for_margin,
    contest_key_for,
    normalize_ticket_candidate_name,
)
from build_district_aggregates import PRECINCT_GENERAL_FILES


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "contests"


def empty_result() -> dict:
    return {
        "dem_votes": 0,
        "rep_votes": 0,
        "other_votes": 0,
        "total_votes": 0,
        "dem_candidate": "",
        "rep_candidate": "",
    }


def normalize_contest_type(contest_type: str) -> str:
    if contest_type == "presidential":
        return "president"
    return contest_type


def finalize_result(entry: dict) -> dict:
    dem_votes = int(entry.get("dem_votes", 0))
    rep_votes = int(entry.get("rep_votes", 0))
    other_votes = int(entry.get("other_votes", 0))
    total_votes = int(entry.get("total_votes", 0))
    margin = rep_votes - dem_votes
    margin_pct = (margin / total_votes * 100) if total_votes else 0.0
    winner = "REP" if margin > 0 else "DEM" if margin < 0 else "TIE"
    return {
        "dem_votes": dem_votes,
        "rep_votes": rep_votes,
        "other_votes": other_votes,
        "total_votes": total_votes,
        "dem_candidate": entry.get("dem_candidate", ""),
        "rep_candidate": entry.get("rep_candidate", ""),
        "margin": margin,
        "margin_pct": margin_pct,
        "winner": winner,
        "color": color_for_margin(margin_pct, winner),
    }


def build_year_contests(path: Path) -> dict[str, dict[str, dict]]:
    contests: dict[str, dict[str, dict]] = {}
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            office = normalize_office(row.get("office", ""))
            if not include_office(office):
                continue
            if office in EXCLUDED_COUNTY_OFFICES:
                continue
            if office.startswith("Judge of the Court of Appeals"):
                continue

            county = clean_text(row.get("county", ""))
            district = clean_text(row.get("district", ""))
            party_raw = clean_text(row.get("party", ""))
            candidate = clean_text(row.get("candidate", ""))
            votes = parse_votes(row.get("votes", "0"))
            if not county or not candidate or votes <= 0:
                continue

            contest_type = normalize_contest_type(contest_key_for(office, district))
            candidate = normalize_ticket_candidate_name(candidate, contest_type)
            county_bucket = contests.setdefault(contest_type, {}).setdefault(county, empty_result())
            party = PARTY_MAP.get(party_raw.upper(), "")
            if party == "DEM":
                county_bucket["dem_votes"] += votes
                if not county_bucket["dem_candidate"]:
                    county_bucket["dem_candidate"] = candidate
            elif party == "REP":
                county_bucket["rep_votes"] += votes
                if not county_bucket["rep_candidate"]:
                    county_bucket["rep_candidate"] = candidate
            else:
                county_bucket["other_votes"] += votes
            county_bucket["total_votes"] += votes

    for contest_type, results in contests.items():
        for county, entry in list(results.items()):
            results[county] = finalize_result(entry)
    return contests


def merge_missing_contests(primary: dict[str, dict[str, dict]], fallback: dict[str, dict[str, dict]]) -> dict[str, dict[str, dict]]:
    merged = dict(primary)
    for contest_type, results in fallback.items():
        if contest_type not in merged:
            merged[contest_type] = results
    return merged


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for existing in OUTPUT_DIR.glob("*.json"):
        existing.unlink()
    manifest_entries: list[dict] = []

    for year, path in YEAR_FILES:
        if not path.exists():
            continue
        contests = build_year_contests(path)
        precinct_path = PRECINCT_GENERAL_FILES.get(int(year))
        if precinct_path and precinct_path.exists():
            precinct_contests = build_year_contests(precinct_path)
            contests = merge_missing_contests(contests, precinct_contests)
        for contest_type, results in sorted(contests.items()):
            rows = [
                {"county": county, **payload}
                for county, payload in sorted(results.items(), key=lambda item: item[0])
            ]
            filename = f"{contest_type}_{year}.json"
            write_json(
                OUTPUT_DIR / filename,
                {
                    "scope": "county",
                    "contest_type": contest_type,
                    "year": int(year),
                    "rows": rows,
                },
            )
            manifest_entries.append(
                {
                    "contest_type": contest_type,
                    "year": int(year),
                    "file": filename,
                    "rows": len(rows),
                }
            )

    manifest_entries.sort(key=lambda entry: (entry["contest_type"], entry["year"]))
    write_json(
        OUTPUT_DIR / "manifest.json",
        {
            "files": manifest_entries,
            "metadata": {
                "scope": "county",
                "generated_from": "Ohio county general-election CSVs in this workspace",
            },
        },
    )
    print(f"Wrote {OUTPUT_DIR / 'manifest.json'} with {len(manifest_entries)} entries")


if __name__ == "__main__":
    main()
