import csv
import json
from pathlib import Path

from build_county_aggregates import include_office, normalize_office, parse_votes
from build_county_aggregates_json import (
    EXCLUDED_COUNTY_OFFICES,
    clean_text,
    color_for_margin,
    contest_key_for,
    infer_party,
    normalize_ticket_candidate_name,
)
from build_district_aggregates import PRECINCT_GENERAL_FILES


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "precinct_contests"


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


def precinct_key_from_row(row: dict[str, str]) -> str:
    county = clean_text(row.get("county", "")).upper()
    precinct_code = clean_text(
        row.get("precinct code", "")
        or row.get("precinct_code", "")
        or row.get("precinct", "")
    ).upper()
    if not county or not precinct_code:
        return ""
    return f"{county} - {precinct_code}"


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

            precinct_key = precinct_key_from_row(row)
            district = clean_text(row.get("district", ""))
            party_raw = clean_text(row.get("party", ""))
            candidate = clean_text(row.get("candidate", ""))
            votes = parse_votes(row.get("votes", "0"))
            if not precinct_key or not candidate or votes <= 0:
                continue

            contest_type = normalize_contest_type(contest_key_for(office, district))
            candidate = normalize_ticket_candidate_name(candidate, contest_type)
            precinct_bucket = contests.setdefault(contest_type, {}).setdefault(precinct_key, empty_result())
            party = infer_party(office, candidate, party_raw)
            if party == "DEM":
                precinct_bucket["dem_votes"] += votes
                if not precinct_bucket["dem_candidate"]:
                    precinct_bucket["dem_candidate"] = candidate
            elif party == "REP":
                precinct_bucket["rep_votes"] += votes
                if not precinct_bucket["rep_candidate"]:
                    precinct_bucket["rep_candidate"] = candidate
            else:
                precinct_bucket["other_votes"] += votes
            precinct_bucket["total_votes"] += votes

    for contest_type, results in contests.items():
        for precinct_key, entry in list(results.items()):
            results[precinct_key] = finalize_result(entry)
    return contests


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
    for year, path in sorted(PRECINCT_GENERAL_FILES.items()):
        if not path.exists():
            continue

        contests = build_year_contests(path)
        for contest_type, results in sorted(contests.items()):
            rows = [
                {"precinct": precinct_key, **payload}
                for precinct_key, payload in sorted(results.items(), key=lambda item: item[0])
            ]
            filename = f"{contest_type}_{year}.json"
            write_json(
                OUTPUT_DIR / filename,
                {
                    "scope": "precinct",
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
                "scope": "precinct",
                "generated_from": "Ohio precinct general-election CSVs in this workspace",
            },
        },
    )
    print(f"Wrote {OUTPUT_DIR / 'manifest.json'} with {len(manifest_entries)} entries")


if __name__ == "__main__":
    main()
