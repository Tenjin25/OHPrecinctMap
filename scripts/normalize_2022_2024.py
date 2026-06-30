import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

YEAR_CONFIGS = {
    "2004": {
        "date": "20041102",
        "raw_dir": "raw",
        "inputs": [
            "precincts.xls",
        ],
        "county_inputs": [
            "precincts.xls",
        ],
        "source_type": "xls_candidate_map",
    },
    "2008": {
        "date": "20081104",
        "raw_dir": "raw",
        "inputs": [
            "2008precincts.xls",
        ],
        "county_inputs": [
            "2008precincts.xls",
        ],
        "source_type": "xls_all_counties",
    },
    "2012": {
        "date": "20121106",
        "raw_dir": "raw",
        "inputs": [
            "2012statewidebyprecinct.xlsx",
        ],
        "county_inputs": [
            "2012statewidebyprecinct.xlsx",
        ],
        "source_type": "xlsx_master",
    },
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
        "source_type": "csv",
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
        "source_type": "csv",
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
    "U.S. Representative": "U.S. House",
    "U.S. House of Representatives": "U.S. House",
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


def column_index_from_ref(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return index - 1


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


def load_xlsx_rows(path: Path, sheet_name: str) -> list[list[str]]:
    with zipfile.ZipFile(path) as workbook_zip:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook_zip.namelist():
            shared_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            for shared_item in shared_root.findall("a:si", NS):
                text = "".join(node.text or "" for node in shared_item.iterfind(".//a:t", NS))
                shared_strings.append(text)

        workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        rel_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rel_root}

        target = None
        for sheet in workbook_root.find("a:sheets", NS):
            if sheet.attrib["name"] == sheet_name:
                rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
                target = rel_map[rel_id]
                break

        if target is None:
            raise ValueError(f"Could not find sheet {sheet_name!r} in {path}")

        sheet_root = ET.fromstring(workbook_zip.read(f"xl/{target}"))
        sheet_data = sheet_root.find("a:sheetData", NS)
        if sheet_data is None:
            return []

        rows: list[list[str]] = []
        for row in sheet_data.findall("a:row", NS):
            parsed_cells: list[tuple[int, str]] = []
            max_index = -1
            for cell in row.findall("a:c", NS):
                cell_ref = cell.attrib.get("r", "")
                column_index = column_index_from_ref(cell_ref) if cell_ref else len(parsed_cells)
                value = ""
                cell_type = cell.attrib.get("t")

                if cell_type == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iterfind(".//a:t", NS))
                else:
                    value_node = cell.find("a:v", NS)
                    if value_node is not None and value_node.text is not None:
                        value = value_node.text
                        if cell_type == "s":
                            value = shared_strings[int(value)]

                parsed_cells.append((column_index, value))
                max_index = max(max_index, column_index)

            row_values = [""] * (max_index + 1 if max_index >= 0 else 0)
            for column_index, value in parsed_cells:
                row_values[column_index] = value
            rows.append(row_values)

        return rows


def load_xls_rows(path: Path, sheet_name: str) -> list[list[str]]:
    try:
        import xlrd  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Reading legacy .xls files requires the 'xlrd' package to be installed."
        ) from exc

    workbook = xlrd.open_workbook(path)
    sheet = workbook.sheet_by_name(sheet_name)
    rows: list[list[str]] = []
    for row_index in range(sheet.nrows):
        row_values = []
        for column_index in range(sheet.ncols):
            value = sheet.cell_value(row_index, column_index)
            if isinstance(value, float) and value.is_integer():
                row_values.append(str(int(value)))
            else:
                row_values.append(str(value))
        rows.append(row_values)
    return rows


def normalize_precinct_code(value: str) -> str:
    cleaned = clean_whitespace(value)
    if "-" in cleaned:
        return cleaned.split("-")[-1]
    return cleaned


def normalize_county_name(value: str) -> str:
    cleaned = clean_whitespace(value)
    return cleaned.title()


def normalize_candidate_name(value: str) -> str:
    cleaned = clean_whitespace(value)
    if "," not in cleaned:
        return cleaned

    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if len(parts) < 2:
        return cleaned

    return clean_whitespace(" ".join(parts[1:] + [parts[0]]))


def strip_running_mate(candidate: str, office: str) -> str:
    cleaned_candidate = clean_whitespace(candidate)
    cleaned_office = clean_whitespace(office)
    if cleaned_office not in {"President/Vice President", "Governor/Lieutenant Governor"}:
        return cleaned_candidate
    return re.split(r"\s+(?:and|/|&)\s+", cleaned_candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip()


def normalize_2004_precinct_name(value: str) -> str:
    cleaned = clean_whitespace(value)

    words = cleaned.split()
    if len(words) % 2 == 0 and words[: len(words) // 2] == words[len(words) // 2 :]:
        cleaned = " ".join(words[: len(words) // 2])

    if " - " in cleaned:
        cleaned = cleaned.replace(" - ", " ")

    cleaned = re.sub(r"\bPRECINCT ([A-Z0-9]+)$", r"\1", cleaned)
    cleaned = re.sub(r"\bPRECINCT$", "", cleaned).strip()
    cleaned = cleaned.replace(",", " ")
    cleaned = clean_whitespace(cleaned)

    return cleaned


def normalize_2004_office(raw_office: str) -> tuple[str, str]:
    office = clean_whitespace(raw_office).title()
    district = ""

    if office.startswith("Statewide Issue"):
        return office.rsplit(" ", 1)[0], office.rsplit(" ", 1)[1].title()

    term_match = re.match(r"^(.*)\s(\d{2}/\d{2})$", office)
    if term_match:
        office = f"{term_match.group(1)} (Term Commencing {term_match.group(2)})"
    elif office.endswith("12/31 Unexpired Term"):
        office = office.replace("12/31 Unexpired Term", "(Unexpired Term Ending 12/31)")

    office = OFFICE_NAME_MAP.get(office, office)
    return office, district


def iter_clean_rows_from_2008_all_counties(path: Path):
    rows = load_xls_rows(path, "All Counties")
    office_row = rows[0]
    header_row = rows[1]

    for row in rows[2:]:
        if len(row) < 6:
            continue

        county = normalize_county_name(row[1])
        if not county:
            continue

        precinct_code = normalize_precinct_code(row[2])
        precinct_name = clean_whitespace(row[3])

        for column_index in range(6, min(len(header_row), len(row))):
            candidate_header = clean_whitespace(header_row[column_index])
            if not candidate_header:
                continue

            office_label = clean_whitespace(office_row[column_index]) if column_index < len(office_row) else ""
            office, district = normalize_contest(office_label)
            candidate, party = normalize_candidate(candidate_header)
            candidate = strip_running_mate(candidate, office)
            votes = parse_votes(row[column_index])

            yield [
                county,
                precinct_code,
                precinct_name,
                office,
                district,
                party,
                candidate,
                str(votes),
            ]


def iter_clean_rows_from_2004_candidate_map(path: Path):
    workbook = load_xls_rows(path, "Candidate Name List")
    results = load_xls_rows(path, "Election Results")

    candidate_map: dict[str, tuple[str, str, str, str]] = {}
    for row in workbook[1:]:
        if len(row) < 5:
            continue
        office = clean_whitespace(row[0])
        district_value = clean_whitespace(row[1])
        party = clean_whitespace(row[2])
        candidate = normalize_candidate_name(row[3].rstrip())
        data_column = clean_whitespace(row[4]).upper()
        if not data_column:
            continue

        normalized_office, issue_choice = normalize_2004_office(office)
        district = ""
        if issue_choice:
            candidate = issue_choice
            party = ""
        elif district_value:
            try:
                district = str(int(float(district_value)))
            except ValueError:
                district = district_value

        if party == "Other":
            party = ""

        candidate_map[(data_column, district)] = (normalized_office, district, party, candidate)

    header_row = [clean_whitespace(value).upper() for value in results[1]]
    data_column_indexes = {name: index for index, name in enumerate(header_row) if name}

    for row in results[2:]:
        if len(row) < 12:
            continue

        county = normalize_county_name(row[1])
        if not county:
            continue

        precinct_code = normalize_precinct_code(row[2])
        precinct_name = normalize_2004_precinct_name(row[3])
        row_district = clean_whitespace(row[5])

        for (data_column, district), metadata in candidate_map.items():
            column_index = data_column_indexes.get(data_column)
            if column_index is None or column_index >= len(row):
                continue
            if district and row_district and district != row_district:
                continue

            office, normalized_district, party, candidate = metadata
            candidate = strip_running_mate(candidate, office)
            votes = parse_votes(row[column_index])
            yield [
                county,
                precinct_code,
                precinct_name,
                office,
                normalized_district,
                party,
                candidate,
                str(votes),
            ]


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
    return normalize_candidate_name(value), party


def iter_clean_rows_from_rows(rows: list[list[str]]):
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
            candidate = strip_running_mate(candidate, office)

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


def iter_clean_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        yield from iter_clean_rows_from_rows(list(csv.reader(handle)))


def iter_clean_rows_from_xlsx_master(path: Path):
    yield from iter_clean_rows_from_rows(load_xlsx_rows(path, "Master"))


def iter_clean_rows_from_xls_master(path: Path):
    yield from iter_clean_rows_from_rows(load_xls_rows(path, "Master"))


def iter_input_rows(year_dir: Path, config: dict[str, object], input_names: list[str]):
    raw_dir = year_dir / str(config.get("raw_dir", ""))
    source_type = str(config.get("source_type", "csv"))
    for input_name in input_names:
        input_path = raw_dir / input_name if str(config.get("raw_dir", "")) else year_dir / input_name
        if source_type == "xlsx_master":
            yield from iter_clean_rows_from_xlsx_master(input_path)
        elif source_type == "xls_master":
            yield from iter_clean_rows_from_xls_master(input_path)
        elif source_type == "xls_all_counties":
            yield from iter_clean_rows_from_2008_all_counties(input_path)
        elif source_type == "xls_candidate_map":
            yield from iter_clean_rows_from_2004_candidate_map(input_path)
        else:
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
