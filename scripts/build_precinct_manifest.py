import csv
import json
from pathlib import Path

from build_county_aggregates import include_office, normalize_office, parse_votes
from build_county_aggregates_json import clean_text, contest_key_for
from build_district_aggregates import LINES_SPECS, PRECINCT_GENERAL_FILES


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_PATH = DATA_DIR / "precinct_contests" / "manifest.json"


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


def normalize_contest_type(contest_type: str) -> str:
    if contest_type == "presidential":
        return "president"
    return contest_type


def summarize_crosswalks() -> dict[str, dict[str, dict]]:
    summary: dict[str, dict[str, dict]] = {}
    for lines_year, spec in sorted(LINES_SPECS.items()):
        summary[str(lines_year)] = {}
        for scope, path in sorted(spec.get("crosswalks", {}).items()):
            row_count = 0
            if path.exists():
                with path.open("r", newline="", encoding="utf-8-sig") as handle:
                    row_count = max(0, sum(1 for _ in handle) - 1)
            summary[str(lines_year)][scope] = {
                "path": str(path.relative_to(BASE_DIR)).replace("\\", "/"),
                "exists": path.exists(),
                "rows": row_count,
            }
    return summary


def main() -> None:
    files: list[dict] = []
    for year, path in sorted(PRECINCT_GENERAL_FILES.items()):
        if not path.exists():
            continue

        contests: dict[str, dict[str, set[str] | int]] = {}
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                office = normalize_office(row.get("office", ""))
                if not include_office(office):
                    continue
                if office.startswith("Judge of the Court of Appeals"):
                    continue
                candidate = clean_text(row.get("candidate", ""))
                votes = parse_votes(row.get("votes", "0"))
                if not candidate or votes <= 0:
                    continue

                contest_type = normalize_contest_type(contest_key_for(office, clean_text(row.get("district", ""))))
                precinct_key = precinct_key_from_row(row)
                county = clean_text(row.get("county", "")).upper()
                bucket = contests.setdefault(
                    contest_type,
                    {
                        "positive_rows": 0,
                        "precinct_keys": set(),
                        "counties": set(),
                    },
                )
                bucket["positive_rows"] += 1
                if precinct_key:
                    bucket["precinct_keys"].add(precinct_key)
                if county:
                    bucket["counties"].add(county)

        for contest_type, bucket in sorted(contests.items()):
            files.append(
                {
                    "contest_type": contest_type,
                    "year": year,
                    "source_file": str(path.relative_to(BASE_DIR)).replace("\\", "/"),
                    "positive_rows": int(bucket["positive_rows"]),
                    "precincts": len(bucket["precinct_keys"]),
                    "counties": len(bucket["counties"]),
                    "lines_years_available": [
                        lines_year
                        for lines_year, spec in sorted(LINES_SPECS.items())
                        if spec.get("crosswalks")
                    ],
                }
            )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "files": files,
                "metadata": {
                    "scope": "precinct",
                    "generated_from": "Ohio precinct general-election CSVs in this workspace",
                    "crosswalks": summarize_crosswalks(),
                },
            },
            handle,
            indent=2,
        )
        handle.write("\n")
    print(f"Wrote {OUTPUT_PATH} with {len(files)} entries")


if __name__ == "__main__":
    main()
