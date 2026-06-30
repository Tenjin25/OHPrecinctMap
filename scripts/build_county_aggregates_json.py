import csv
import json
import re
from pathlib import Path

from build_county_aggregates import DATA_DIR, include_office, normalize_office, parse_votes


OUTPUT_PATH = DATA_DIR / "county_aggregates_nested.json"

EXCLUDED_COUNTY_OFFICES = {
    "U.S. House",
    "State House",
    "State Representative",
    "State Senate",
    "State Senator",
}

YEAR_FILES = [
    ("2000", DATA_DIR / "2000" / "20001107__oh__general__county.csv"),
    ("2002", DATA_DIR / "2002" / "20021105__oh__general.csv"),
    ("2004", DATA_DIR / "2004" / "20041102__oh__general__county.csv"),
    ("2006", DATA_DIR / "2006" / "20061107__oh__general__county.csv"),
    ("2008", DATA_DIR / "2008" / "20081104__oh__general__county.csv"),
    ("2010", DATA_DIR / "2010" / "20101102__oh__general__county.csv"),
    ("2012", DATA_DIR / "2012" / "20121106__oh__general__county.csv"),
    ("2014", DATA_DIR / "2014" / "20141104__oh__general.csv"),
    ("2016", DATA_DIR / "2016" / "20161108__oh__general.csv"),
    ("2018", DATA_DIR / "2018" / "20181106__oh__general__county.csv"),
    ("2020", DATA_DIR / "2020" / "20201103__oh__general__county.csv"),
    ("2022", DATA_DIR / "2022" / "20221108__oh__general__county.csv"),
    ("2024", DATA_DIR / "2024" / "20241105__oh__general__county.csv"),
]

UNAVAILABLE_YEARS = {}

PARTY_MAP = {
    "D": "DEM",
    "DEMOCRATIC": "DEM",
    "R": "REP",
    "REPUBLICAN": "REP",
}

JUDICIAL_CANDIDATE_PARTY_MAP = {
    ("Chief Justice of the Supreme Court (Term Commencing 01/01)", "C. Ellen Connally"): "DEM",
    ("Chief Justice of the Supreme Court (Term Commencing 01/01)", "Thomas J. Moyer"): "REP",
    ("Justice of the Supreme Court (Term Commencing 01/02)", "Paul E. Pfeifer"): "REP",
    ("Justice of the Supreme Court (Unexpired Term Ending 12/31)", "Terrence O'Donnell"): "REP",
    ("Chief Justice of the Supreme Court - Term Commencing 01/01/2011", "Eric Brown"): "DEM",
    ("Chief Justice of the Supreme Court - Term Commencing 01/01/2011", "Maureen O'Connor"): "REP",
    ("Justice of the Supreme Court - Term Commencing 01/01/2011", "Mary Jane Trapp"): "DEM",
    ("Justice of the Supreme Court - Term Commencing 01/01/2011", "Judith Lanzinger"): "REP",
    ("Justice of the Ohio Supreme Court - Term Commencing 01/01/2011", "Mary Jane Trapp"): "DEM",
    ("Justice of the Ohio Supreme Court - Term Commencing 01/01/2011", "Judith Lanzinger"): "REP",
    ("Justice of the Supreme Court - Term Commencing 01/02/2011", "Paul Pfeifer"): "REP",
    ("Justice of the Ohio Supreme Court - Term Commencing 01/02/2011", "Paul Pfeifer"): "REP",
}


def clean_text(value: str) -> str:
    return " ".join((value or "").split())


def slugify(value: str) -> str:
    value = clean_text(value).lower()
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def normalize_ticket_candidate_name(candidate: str, contest_key: str) -> str:
    candidate = clean_text(candidate)
    if contest_key not in {"presidential", "president"}:
        return candidate
    return re.split(r"\s+(?:and|/|&)\s+", candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip()


def infer_party(office: str, candidate: str, party_raw: str) -> str:
    explicit_party = PARTY_MAP.get(clean_text(party_raw).upper(), "")
    if explicit_party:
        return explicit_party
    return JUDICIAL_CANDIDATE_PARTY_MAP.get((normalize_office(office), clean_text(candidate)), "")


def contest_key_for(office: str, district: str) -> str:
    office = normalize_office(office)
    district = clean_text(district)

    office_key_map = {
        "President/Vice President": "presidential",
        "U.S. Senate": "us_senate",
        "Governor": "governor",
        "Governor/Lieutenant Governor": "governor",
        "Attorney General": "attorney_general",
        "Auditor of State": "auditor",
        "Secretary of State": "secretary_of_state",
        "Treasurer of State": "treasurer",
    }
    if office in office_key_map:
        return office_key_map[office]
    if office == "U.S. House":
        return f"us_house_{district or 'statewide'}"
    if office.startswith("Chief Justice of the Supreme Court"):
        return slugify(office)
    if office.startswith("Justice of the Supreme Court"):
        return slugify(office)
    if office.startswith("Judge of the Court of Appeals"):
        suffix = f"_{district}" if district else ""
        return f"{slugify(office)}{suffix}"
    return slugify(office if not district else f"{office} {district}")


def color_for_margin(margin_pct: float, winner: str) -> str:
    abs_margin = abs(margin_pct)
    if winner == "DEM":
        if abs_margin >= 15:
            return "#2171b5"
        if abs_margin >= 5:
            return "#6baed6"
        return "#c6dbef"
    if winner == "REP":
        if abs_margin >= 15:
            return "#cb181d"
        if abs_margin >= 5:
            return "#fb6a4a"
        return "#fcbba1"
    return "#d9d9d9"


def empty_county_result() -> dict:
    return {
        "dem_votes": 0,
        "rep_votes": 0,
        "other_votes": 0,
        "total_votes": 0,
        "dem_candidate": "",
        "rep_candidate": "",
    }


def finalize_county_result(entry: dict) -> dict:
    dem_votes = int(entry.get("dem_votes", 0))
    rep_votes = int(entry.get("rep_votes", 0))
    other_votes = int(entry.get("other_votes", 0))
    total_votes = int(entry.get("total_votes", 0))
    margin = rep_votes - dem_votes
    margin_pct = (margin / total_votes * 100) if total_votes else 0.0
    winner = "REP" if margin > 0 else "DEM" if margin < 0 else "TIE"
    entry["margin"] = margin
    entry["margin_pct"] = margin_pct
    entry["winner"] = winner
    entry["competitiveness"] = {"color": color_for_margin(margin_pct, winner)}
    return entry


def load_results_by_year() -> tuple[dict[str, dict], list[str]]:
    results_by_year: dict[str, dict] = {}
    missing_years: list[str] = []

    for year, path in YEAR_FILES:
        if not path.exists():
            missing_years.append(year)
            continue

        contests: dict[str, dict] = {}
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                office = normalize_office(row.get("office", ""))
                if not include_office(office):
                    continue
                if office in EXCLUDED_COUNTY_OFFICES:
                    continue

                county = clean_text(row.get("county", ""))
                district = clean_text(row.get("district", ""))
                party_raw = clean_text(row.get("party", ""))
                candidate = clean_text(row.get("candidate", ""))
                votes = parse_votes(row.get("votes", "0"))
                if not county or not candidate or votes <= 0:
                    continue

                contest_key = contest_key_for(office, district)
                candidate = normalize_ticket_candidate_name(candidate, contest_key)
                contest_bucket = contests.setdefault(contest_key, {"general": {"results": {}}})
                county_bucket = contest_bucket["general"]["results"].setdefault(county, empty_county_result())

                party = infer_party(office, candidate, party_raw)
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

        for contest_bucket in contests.values():
            results = contest_bucket["general"]["results"]
            for county, entry in list(results.items()):
                results[county] = finalize_county_result(entry)

        results_by_year[year] = contests

    return results_by_year, missing_years


def main() -> None:
    results_by_year, missing_years = load_results_by_year()
    payload = {
        "generated_from": "Ohio county-level general-election CSVs already in this workspace",
        "metadata": {
            "state": "Ohio",
            "scope": "county",
            "included_contests": ["federal", "statewide", "judicial"],
            "years": sorted(results_by_year.keys()),
            "missing_years": sorted(missing_years + list(UNAVAILABLE_YEARS.keys())),
            "unavailable_year_notes": UNAVAILABLE_YEARS,
        },
        "results_by_year": results_by_year,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
