import csv
import re
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

COUNTY_HEADER = ["county", "office", "district", "party", "candidate", "votes"]

INCLUDE_OFFICES = {
    "Attorney General",
    "Auditor of State",
    "Chief Justice of the Supreme Court",
    "Governor",
    "Governor/Lieutenant Governor",
    "Governor/LtGovernor",
    "Judge of the Court of Appeals",
    "Justice of the Supreme Court",
    "President",
    "President/Vice President",
    "Secretary of State",
    "State Auditor",
    "Treasurer of State",
    "Treasure of State",
    "U.S. Senate",
    "US Senate",
}

OFFICE_NORMALIZATION = {
    "Governor/LtGovernor": "Governor/Lieutenant Governor",
    "President": "President/Vice President",
    "President/Vice-President": "President/Vice President",
    "State Auditor": "Auditor of State",
    "Treasure of State": "Treasurer of State",
    "US Senate": "U.S. Senate",
}

YEAR_TASKS = [
    {
        "output": DATA_DIR / "2000" / "20001107__oh__general__county.csv",
        "mode": "merge",
        "inputs": [
            DATA_DIR / "2000" / "20001107__oh__general__president.csv",
            DATA_DIR / "2000" / "20001107__oh__general__senate.csv",
            DATA_DIR / "2000" / "20001107__oh__general__house.csv",
        ],
    },
    {
        "output": DATA_DIR / "2006" / "20061107__oh__general__county.csv",
        "mode": "aggregate_precinct",
        "inputs": [DATA_DIR / "2006" / "20061107__OH__general__precinct.csv"],
    },
    {
        "output": DATA_DIR / "2010" / "20101102__oh__general__county.csv",
        "mode": "aggregate_precinct",
        "inputs": [DATA_DIR / "2010" / "20101102__oh__general__precinct.csv"],
    },
    {
        "output": DATA_DIR / "2012" / "20121106__oh__general__county.csv",
        "mode": "merge",
        "inputs": [
            DATA_DIR / "2012" / "20121106__oh__general__president.csv",
            DATA_DIR / "2012" / "20121106__oh__general__senate.csv",
            DATA_DIR / "2012" / "20121106__oh__general__house.csv",
        ],
    },
    {
        "output": DATA_DIR / "2018" / "20181106__oh__general__county.csv",
        "mode": "aggregate_precinct",
        "inputs": [DATA_DIR / "2018" / "20181106__oh__general__precinct.csv"],
    },
]


def clean_text(value: str) -> str:
    return " ".join((value or "").split())


def normalize_office(value: str) -> str:
    office = clean_text(value)
    office = OFFICE_NORMALIZATION.get(office, office)

    judicial_patterns = [
        (r"^Chief Justice Of The Supreme Court\b", "Chief Justice of the Supreme Court"),
        (r"^Chief Justice of the Supreme Court\b", "Chief Justice of the Supreme Court"),
        (r"^Justice Of The Ohio Supreme Court\b", "Justice of the Supreme Court"),
        (r"^Justice Of The Supreme Court\b", "Justice of the Supreme Court"),
        (r"^Justice of the Supreme Court\b", "Justice of the Supreme Court"),
        (r"^Judge Of Court Of Appeals\b", "Judge of the Court of Appeals"),
        (r"^Judge Of The Court Of Appeals\b", "Judge of the Court of Appeals"),
        (r"^Judge of the Court of Appeals\b", "Judge of the Court of Appeals"),
    ]
    for pattern, replacement in judicial_patterns:
        if re.match(pattern, office):
            office = re.sub(pattern, replacement, office)
            return office
    return office


def include_office(value: str) -> bool:
    office = normalize_office(value)
    if office in INCLUDE_OFFICES:
        return True
    return (
        office.startswith("Chief Justice of the Supreme Court")
        or office.startswith("Justice of the Supreme Court")
        or office.startswith("Judge of the Court of Appeals")
    )


def parse_votes(value: str) -> int:
    cleaned = clean_text(value).replace(",", "")
    if not cleaned:
        return 0
    return int(float(cleaned))


def aggregate_rows(paths: list[Path]) -> list[list[str]]:
    totals: defaultdict[tuple[str, str, str, str, str], int] = defaultdict(int)

    for path in paths:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                office = normalize_office(row.get("office", ""))
                if not include_office(office):
                    continue

                county = clean_text(row.get("county", ""))
                district = clean_text(row.get("district", ""))
                party = clean_text(row.get("party", ""))
                candidate = clean_text(row.get("candidate", ""))
                votes = parse_votes(row.get("votes", "0"))
                if not county or not candidate or votes <= 0:
                    continue

                totals[(county, office, district, party, candidate)] += votes

    rows: list[list[str]] = []
    for county, office, district, party, candidate in sorted(totals):
        rows.append([county, office, district, party, candidate, str(totals[(county, office, district, party, candidate)])])
    return rows


def write_rows(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COUNTY_HEADER)
        writer.writerows(rows)


def main() -> None:
    for task in YEAR_TASKS:
        rows = aggregate_rows(task["inputs"])
        write_rows(task["output"], rows)
        print(f"Wrote {task['output']}")


if __name__ == "__main__":
    main()
