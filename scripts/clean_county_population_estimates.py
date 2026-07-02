from __future__ import annotations

import argparse
import csv
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SHEET_YEAR_TO_OUTPUT_COLUMN = {
    "April 1, 2020 Estimates Base": "estimate_base_2020_04_01",
    "2020": "population_2020",
    "2021": "population_2021",
    "2022": "population_2022",
    "2023": "population_2023",
    "2024": "population_2024",
    "2025": "population_2025",
}

OUTPUT_FIELDS = [
    "county_name",
    "county_norm",
    "estimate_base_2020_04_01",
    "population_2020",
    "population_2021",
    "population_2022",
    "population_2023",
    "population_2024",
    "population_2025",
    "change_2020_2025",
    "change_2020_2025_pct",
    "change_2024_2025",
    "change_2024_2025_pct",
]


def normalize_county_token(value: str) -> str:
    cleaned = "".join(ch for ch in (value or "") if ch.isalnum() or ch in {" ", ".", "-"})
    return " ".join(cleaned.split()).strip().upper()


def strip_county_suffix(value: str) -> str:
    return re.sub(r"\s+County$", "", str(value or "").strip(), flags=re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert the Census county population workbook into a county/year summary table the frontend can load directly."
    )
    parser.add_argument("input_workbook", type=Path, help="Census county population workbook (.xlsx)")
    parser.add_argument("output_csv", type=Path, help="Cleaned output CSV")
    parser.add_argument(
        "--source-vintage",
        default="Census Vintage 2025 county population estimates",
        help="Source label stored in the cleaned file",
    )
    return parser.parse_args()


def safe_int(value: str) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return 0


def safe_pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return ""
    value = (numerator / denominator) * 100
    return f"{value:.3f}".rstrip("0").rstrip(".")


def extract_sheet_rows(input_workbook: Path) -> list[list[str]]:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(input_workbook) as workbook_zip:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook_zip.namelist():
            shared_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            for si in shared_root.findall("a:si", ns):
                shared_strings.append("".join(node.text or "" for node in si.findall(".//a:t", ns)))

        sheet_root = ET.fromstring(workbook_zip.read("xl/worksheets/sheet1.xml"))
        parsed_rows: list[list[str]] = []
        for row in sheet_root.findall(".//a:sheetData/a:row", ns):
            values: dict[int, str] = {}
            max_col = 0
            for cell in row.findall("a:c", ns):
                ref = cell.get("r", "")
                col_letters = "".join(ch for ch in ref if ch.isalpha())
                col_idx = column_letters_to_index(col_letters)
                max_col = max(max_col, col_idx)
                value_node = cell.find("a:v", ns)
                value = value_node.text if value_node is not None and value_node.text is not None else ""
                if cell.get("t") == "s" and value != "":
                    value = shared_strings[int(value)]
                values[col_idx] = value
            parsed_rows.append([values.get(idx, "") for idx in range(1, max_col + 1)])
    return parsed_rows


def column_letters_to_index(letters: str) -> int:
    total = 0
    for ch in letters.upper():
        total = (total * 26) + (ord(ch) - 64)
    return total


def clean_geographic_area(value: str) -> str:
    name = str(value or "").strip()
    if name.startswith("."):
        name = name[1:].strip()
    return name


def split_county_and_state(area_name: str) -> tuple[str, str]:
    cleaned = clean_geographic_area(area_name)
    if "," in cleaned:
        county_part, state_part = cleaned.rsplit(",", 1)
        return county_part.strip(), state_part.strip()
    return cleaned, ""


def row_has_population_values(row: list[str], year_columns: dict[int, str]) -> bool:
    for idx in year_columns:
        if idx < len(row) and str(row[idx]).strip():
            return True
    return False


def build_rows(input_workbook: Path, _source_vintage: str) -> list[dict[str, str]]:
    counties: list[dict[str, str]] = []
    state_name = ""

    rows = extract_sheet_rows(input_workbook)
    header_row_top = rows[2]
    header_row_bottom = rows[3]
    year_columns: dict[int, str] = {}
    for idx, header_value in enumerate(header_row_top):
        label = str(header_value or "").strip()
        if label in SHEET_YEAR_TO_OUTPUT_COLUMN:
            year_columns[idx] = SHEET_YEAR_TO_OUTPUT_COLUMN[label]
    for idx, header_value in enumerate(header_row_bottom):
        label = str(header_value or "").strip()
        if label in SHEET_YEAR_TO_OUTPUT_COLUMN:
            year_columns[idx] = SHEET_YEAR_TO_OUTPUT_COLUMN[label]

    statewide_entry: dict[str, str] | None = None
    for row in rows[4:]:
        if not row:
            continue
        raw_area = str(row[0] if len(row) > 0 else "").strip()
        if not raw_area:
            continue
        if not row_has_population_values(row, year_columns):
            continue

        area_name = clean_geographic_area(raw_area)
        county_name, parsed_state_name = split_county_and_state(area_name)
        county_base_name = strip_county_suffix(county_name)
        row_type = "county" if raw_area.startswith(".") else ("statewide" if area_name == "Ohio" else "")
        if not row_type:
            continue
        if row_type == "statewide":
            state_name = area_name
            statewide_entry = {
                "county_name": state_name,
                "county_norm": normalize_county_token(state_name),
            }
            target = statewide_entry
        else:
            state_name = parsed_state_name or state_name
            target = {
                "county_name": county_base_name,
                "county_norm": normalize_county_token(county_base_name),
            }
            counties.append(target)

        for idx, output_key in year_columns.items():
            if idx < len(row):
                target[output_key] = str(safe_int(row[idx]))

    output_rows: list[dict[str, str]] = []
    for entry in counties:
        populate_changes(entry)
        output_rows.append(with_all_fields(entry))

    if statewide_entry is None:
        raise ValueError(f"Could not find statewide row in {input_workbook}")
    populate_changes(statewide_entry)
    output_rows.insert(0, with_all_fields(statewide_entry))

    output_rows[1:] = sorted(output_rows[1:], key=lambda row: row["county_name"])
    return output_rows


def populate_changes(entry: dict[str, str]) -> None:
    pop_2020 = safe_int(entry.get("population_2020", "0"))
    pop_2024 = safe_int(entry.get("population_2024", "0"))
    pop_2025 = safe_int(entry.get("population_2025", "0"))
    entry["change_2020_2025"] = str(pop_2025 - pop_2020)
    entry["change_2020_2025_pct"] = safe_pct(pop_2025 - pop_2020, pop_2020)
    entry["change_2024_2025"] = str(pop_2025 - pop_2024)
    entry["change_2024_2025_pct"] = safe_pct(pop_2025 - pop_2024, pop_2024)


def with_all_fields(entry: dict[str, str]) -> dict[str, str]:
    return {field: entry.get(field, "") for field in OUTPUT_FIELDS}


def main() -> None:
    args = parse_args()
    rows = build_rows(args.input_workbook, args.source_vintage)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
