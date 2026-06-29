import csv
import re
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

YEAR_CONFIGS = {
    "2022": {
        "date": "20221108",
        "raw_dir": "raw",
        "inputs": [
            "2022 Statewide Offices.csv",
            "2022 U.S. Congress.csv",
            "2022 General Assembly.csv",
            "2022 Supreme Court.csv",
            "2022 Judicial.csv",
        ],
        "county_inputs": [
            "2022 Statewide Offices.csv",
            "2022 U.S. Congress.csv",
            "2022 Supreme Court.csv",
            "2022 Judicial.csv",
        ],
    },
    "2024": {
        "date": "20241105",
        "raw_dir": "raw",
        "inputs": [
            "2024 President and Vice President.csv",
            "2024 U.S. Congress.csv",
            "2024 General Assembly.csv",
            "2024 Justice of the Supreme Court.csv",
            "2024 Judge of Court of Appeals.csv",
        ],
        "county_inputs": [
            "2024 President and Vice President.csv",
            "2024 U.S. Congress.csv",
            "2024 Justice of the Supreme Court.csv",
            "2024 Judge of Court of Appeals.csv",
        ],
    },
}

OUTPUT_HEADER = [
    "county",
    "precinct code",
    "precinct name",
    "office",
    "district",
    "party",
    "candidate",
    "votes",
]

COUNTY_OUTPUT_HEADER = [
    "county",
    "office",
    "district",
    "party",
    "candidate",
    "votes",
]

OFFICE_NAME_MAP = {
    "Governor and Lieutenant Governor": "Governor/Lieutenant Governor",
    "President and Vice President": "President/Vice President",
    "Representative to Congress": "U.S. House",
    "U.S. Senator": "U.S. Senate",
    "State Senator": "State Senate",
    "State Representative": "State House",
}


def clean_whitespace(value: str) -> str:
    return " ".join((value or "").split())


def parse_votes(value: str) -> int:
    cleaned = clean_whitespace(value).replace(",", "")
    if not cleaned:
        return 0
    return int(float(cleaned))


def find_header_row(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows):
        if row[:3] == ["County Name", "Precinct Name", "Precinct Code"]:
            return index
    raise ValueError("Could not find header row")


def build_contest_labels(rows: list[list[str]], header_index: int, header: list[str]) -> list[str]:
    filled_rows: list[list[str]] = []
    for row in rows[:header_index]:
        current = ""
        filled = []
        for cell in row:
            cleaned = clean_whitespace(cell)
            if cleaned:
                current = cleaned
            filled.append(current)
        filled_rows.append(filled)

    contest_labels: list[str] = []
    for column_index in range(8, len(header)):
        parts: list[str] = []
        for filled in filled_rows:
            value = filled[column_index] if column_index < len(filled) else ""
            if value and (not parts or parts[-1] != value):
                parts.append(value)
        contest_labels.append(" ".join(parts))
    return contest_labels


def normalize_contest(label: str) -> tuple[str, str]:
    label = clean_whitespace(label)

    term_match = re.search(r"\s+(Term Commencing .*|Unexpired Term Ending .*)$", label)
    term = ""
    if term_match:
        term = term_match.group(1)
        label = label[: term_match.start()].strip()

    district_match = re.match(r"^(.*?)(?: - District (\d+))?$", label)
    if not district_match:
        return label, ""

    office = district_match.group(1)
    district = district_match.group(2) or ""
    office = OFFICE_NAME_MAP.get(office, office)

    if district:
        district = str(int(district))
    if term:
        office = f"{office} ({term})"

    return office, district


def normalize_candidate(value: str) -> tuple[str, str]:
    value = clean_whitespace(value)
    match = re.search(r"\(([A-Z]+)\)\*?$", value)
    party = ""
    if match:
        party = match.group(1)
        value = clean_whitespace(value[: match.start()])
    if party == "WI":
        party = ""
    return value, party


def iter_clean_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))

    header_index = find_header_row(rows)
    header = rows[header_index]
    contests = build_contest_labels(rows, header_index, header)

    for row in rows[header_index + 1 :]:
        if not row:
            continue

        county = clean_whitespace(row[0]) if len(row) > 0 else ""
        if county in {"", "Total", "Percentage"}:
            continue

        precinct_name = clean_whitespace(row[1]) if len(row) > 1 else ""
        precinct_code = clean_whitespace(row[2]) if len(row) > 2 else ""

        for offset, candidate_header in enumerate(header[8:]):
            column_index = offset + 8
            if column_index >= len(row):
                continue

            votes_value = clean_whitespace(row[column_index])
            if not votes_value:
                continue

            office, district = normalize_contest(contests[offset])
            candidate, party = normalize_candidate(candidate_header)

            yield [
                county,
                precinct_code,
                precinct_name,
                office,
                district,
                party,
                candidate,
                str(parse_votes(votes_value)),
            ]


def iter_input_rows(year_dir: Path, config: dict[str, object], input_names: list[str]):
    raw_dir = year_dir / str(config.get("raw_dir", ""))
    for input_name in input_names:
        input_path = raw_dir / input_name if str(config.get("raw_dir", "")) else year_dir / input_name
        yield from iter_clean_rows(input_path)


def build_precinct_output(year_dir: Path, config: dict[str, object]) -> Path:
    output_path = year_dir / f"{config['date']}__oh__general__precinct.csv"

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(OUTPUT_HEADER)

        for cleaned_row in iter_input_rows(year_dir, config, list(config["inputs"])):
            writer.writerow(cleaned_row)

    return output_path


def build_county_output(year_dir: Path, config: dict[str, object]) -> Path:
    output_path = year_dir / f"{config['date']}__oh__general__county.csv"
    totals: defaultdict[tuple[str, str, str, str, str], int] = defaultdict(int)

    for row in iter_input_rows(year_dir, config, list(config["county_inputs"])):
        county, _, _, office, district, party, candidate, votes = row
        totals[(county, office, district, party, candidate)] += int(votes)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COUNTY_OUTPUT_HEADER)
        for county, office, district, party, candidate in sorted(totals):
            total_votes = totals[(county, office, district, party, candidate)]
            if total_votes <= 0:
                continue
            writer.writerow([county, office, district, party, candidate, str(total_votes)])

    return output_path


def build_year(year: str, config: dict[str, object]) -> tuple[Path, Path]:
    year_dir = BASE_DIR / "data" / year
    precinct_output_path = build_precinct_output(year_dir, config)
    county_output_path = build_county_output(year_dir, config)
    return precinct_output_path, county_output_path


def main():
    for year, config in YEAR_CONFIGS.items():
        precinct_output_path, county_output_path = build_year(year, config)
        print(f"Wrote {precinct_output_path}")
        print(f"Wrote {county_output_path}")


if __name__ == "__main__":
    main()
