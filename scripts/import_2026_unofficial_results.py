from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from build_county_aggregates_json import color_for_margin


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCE_PATH = DATA_DIR / "2026" / "raw" / "oh_sos_election_night_2026.csv"
COUNTY_PATH = DATA_DIR / "2026" / "20261103__oh__general__county.csv"

COUNTY_OFFICES = {
    "Governor": "Governor/Lieutenant Governor",
    "Attorney General": "Attorney General",
    "Auditor": "Auditor of State",
    "Secretary of State": "Secretary of State",
    "Treasurer": "Treasurer of State",
    "Supreme Court, Hawkins seat": "Justice of the Supreme Court (Term Commencing 01/01/2027)",
    "Supreme Court, Brunner seat": "Justice of the Supreme Court (Term Commencing 01/02/2027)",
    "Senate": "U.S. Senate",
}

DISTRICT_OUTPUTS = {
    "ushouse": (
        "congressional",
        "us_house",
        DATA_DIR / "district_contests_2026_lines",
        "congressional_us_house_2026.json",
        2026,
    ),
    "house": (
        "state_house",
        "state_house",
        DATA_DIR / "district_contests_2024_lines",
        "state_house_state_house_2026.json",
        2024,
    ),
    "senate": (
        "state_senate",
        "state_senate",
        DATA_DIR / "district_contests_2024_lines",
        "state_senate_state_senate_2026.json",
        2024,
    ),
}


def clean(value: str | None) -> str:
    return " ".join((value or "").split())


def parse_votes(value: str | None) -> int:
    raw = clean(value).replace(",", "")
    return int(raw) if raw else 0


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def final_result(candidates: list[dict[str, str]]) -> dict:
    dem_votes = rep_votes = other_votes = 0
    dem_candidate = rep_candidate = ""
    for row in candidates:
        party = clean(row.get("party")).upper()
        candidate = clean(row.get("candidate"))
        votes = parse_votes(row.get("votes"))
        if party == "D":
            dem_votes += votes
            dem_candidate = dem_candidate or candidate
        elif party == "R":
            rep_votes += votes
            rep_candidate = rep_candidate or candidate
        else:
            other_votes += votes
    total_votes = dem_votes + rep_votes + other_votes
    margin = rep_votes - dem_votes
    margin_pct = (margin / total_votes * 100) if total_votes else 0.0
    winner = "REP" if margin > 0 else "DEM" if margin < 0 else "TIE"
    return {
        "dem_votes": dem_votes,
        "rep_votes": rep_votes,
        "other_votes": other_votes,
        "total_votes": total_votes,
        "dem_candidate": dem_candidate,
        "rep_candidate": rep_candidate,
        "margin": margin,
        "margin_pct": margin_pct,
        "winner": winner,
        "color": color_for_margin(margin_pct, winner),
    }


def build_county_csv(rows: list[dict[str, str]]) -> None:
    output_rows: list[list[str | int]] = []
    for row in rows:
        if clean(row.get("level")) != "statewide":
            continue
        office = COUNTY_OFFICES.get(clean(row.get("office")))
        county = clean(row.get("unit_name"))
        candidate = clean(row.get("candidate"))
        if not office or not county or not candidate:
            continue
        party = clean(row.get("party"))
        if party not in {"D", "R"}:
            party = ""
        output_rows.append([county, office, "", party, candidate, parse_votes(row.get("votes"))])

    COUNTY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with COUNTY_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["county", "office", "district", "party", "candidate", "votes"])
        writer.writerows(output_rows)


def update_manifest(directory: Path, entry: dict) -> None:
    manifest_path = directory / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"files": []}
    files = [
        item for item in payload.get("files", [])
        if not (
            item.get("scope") == entry["scope"]
            and item.get("contest_type") == entry["contest_type"]
            and int(item.get("year", 0)) == entry["year"]
        )
    ]
    files.append(entry)
    files.sort(key=lambda item: (item.get("scope", ""), item.get("contest_type", ""), int(item.get("year", 0))))
    payload["files"] = files
    write_json(manifest_path, payload)


def build_direct_district_results(rows: list[dict[str, str]]) -> None:
    for level, (scope, contest_type, directory, filename, lines_year) in DISTRICT_OUTPUTS.items():
        grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            if clean(row.get("level")) == level:
                grouped[clean(row.get("unit"))].append(row)
        results = {district: final_result(candidates) for district, candidates in sorted(grouped.items(), key=lambda item: int(item[0]))}
        payload = {
            "scope": scope,
            "contest_type": contest_type,
            "year": 2026,
            "status": "unofficial",
            "source": "Ohio Secretary of State election-night reporting feed",
            "source_as_of": "2026-11-07",
            "general": {"results": results},
        }
        write_json(directory / filename, payload)
        update_manifest(directory, {
            "scope": scope,
            "contest_type": contest_type,
            "year": 2026,
            "file": filename,
            "rows": len(results),
            "lines_year": lines_year,
            "status": "unofficial",
        })


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Missing source file: {SOURCE_PATH}")
    with SOURCE_PATH.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    build_county_csv(rows)
    build_direct_district_results(rows)
    print(f"Wrote {COUNTY_PATH}")
    print("Wrote 2026 U.S. House, Ohio House, and Ohio Senate district result slices")


if __name__ == "__main__":
    main()
