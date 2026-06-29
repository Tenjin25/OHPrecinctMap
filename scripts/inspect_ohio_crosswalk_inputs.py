from __future__ import annotations

import csv
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
CENSUS_DIR = DATA_ROOT / "census"
VENDOR_PYSHP_DIR = PROJECT_ROOT / ".vendor" / "pyshp"


NHGIS_FILES = {
    "blk2000_blk2010": DATA_ROOT / "nhgis_blk2000_blk2010_39.zip",
    "blk2010_blk2020": DATA_ROOT / "nhgis_blk2010_blk2020_39.zip",
    "blk2020_blk2010": DATA_ROOT / "nhgis_blk2020_blk2010_39.zip",
}


BLOCK_SHAPEFILES = {
    "tabblock10": CENSUS_DIR / "tl_2010_39_tabblock10" / "tl_2010_39_tabblock10.shp",
    "tabblock20": CENSUS_DIR / "tl_2020_39_tabblock20" / "tl_2020_39_tabblock20.shp",
}


VTD10_DIR = CENSUS_DIR / "tl_2010_39_vtd10"
VTD10_GEOJSON = VTD10_DIR / "tl_2010_39_vtd10.geojson"


def ensure_pyshp() -> None:
    if VENDOR_PYSHP_DIR.exists():
        sys.path.insert(0, str(VENDOR_PYSHP_DIR))
    try:
        import shapefile  # noqa: F401
    except ImportError as exc:  # pragma: no cover - runtime guard
        raise SystemExit(
            "Missing dependency 'pyshp'. Install it with: pip install pyshp or "
            "pip install pyshp -t .vendor/pyshp"
        ) from exc


def inspect_nhgis_zip(path: Path) -> dict:
    if not path.exists():
        return {"path": str(path), "present": False}

    with zipfile.ZipFile(path) as zf:
        csv_name = next((name for name in zf.namelist() if name.lower().endswith(".csv")), None)
        readme_name = next((name for name in zf.namelist() if "readme" in name.lower()), None)
        if csv_name is None:
            return {
                "path": str(path),
                "present": True,
                "csv_name": None,
                "readme_name": readme_name,
                "error": "No CSV found in archive",
            }

        with zf.open(csv_name) as fh:
            text = (line.decode("utf-8", errors="replace") for line in fh)
            reader = csv.DictReader(text)
            source_col = reader.fieldnames[0]
            target_col = reader.fieldnames[2]
            row_count = 0
            source_weights = defaultdict(float)
            unique_sources = set()
            unique_targets = set()

            for row in reader:
                row_count += 1
                source = row[source_col]
                target = row[target_col]
                weight = float(row.get("weight", "0") or 0)
                source_weights[source] += weight
                unique_sources.add(source)
                unique_targets.add(target)

    max_delta = 0.0
    perfect_sources = 0
    zero_weight_sources = 0
    for total in source_weights.values():
        delta = abs(total - 1.0)
        if delta < 1e-9:
            perfect_sources += 1
        if total == 0:
            zero_weight_sources += 1
        if delta > max_delta:
            max_delta = delta

    return {
        "path": str(path),
        "present": True,
        "csv_name": csv_name,
        "readme_name": readme_name,
        "row_count": row_count,
        "source_column": source_col,
        "target_column": target_col,
        "unique_source_blocks": len(unique_sources),
        "unique_target_blocks": len(unique_targets),
        "weight_sums": {
            "source_block_count": len(source_weights),
            "perfect_sum_to_one": perfect_sources,
            "zero_weight_sources": zero_weight_sources,
            "max_abs_delta_from_one": max_delta,
        },
    }


def inspect_shapefile(path: Path, id_fields: list[str]) -> dict:
    result = {
        "path": str(path),
        "present": path.exists(),
    }
    if not path.exists():
        return result

    import shapefile

    reader = shapefile.Reader(str(path))
    fields = [field[0] for field in reader.fields[1:]]
    samples = []
    sample_limit = 3
    for index, record in enumerate(reader.records()):
        if index >= sample_limit:
            break
        row = dict(zip(fields, record))
        samples.append({field: row.get(field) for field in id_fields if field in row})

    result.update(
        {
            "feature_count": len(reader),
            "fields_checked": [field for field in id_fields if field in fields],
            "sample_ids": samples,
        }
    )
    return result


def inspect_vtd10_bundle() -> dict:
    result = {
        "path": str(VTD10_DIR),
        "present": VTD10_DIR.exists(),
    }
    if not VTD10_DIR.exists():
        return result

    shp_files = sorted(VTD10_DIR.glob("*.shp"))
    result["county_shapefile_count"] = len(shp_files)
    result["geojson_present"] = VTD10_GEOJSON.exists()

    if VTD10_GEOJSON.exists():
        with VTD10_GEOJSON.open("r", encoding="utf-8") as fh:
            geojson = json.load(fh)
        result["merged_feature_count"] = len(geojson.get("features", []))

    if shp_files:
        result["sample_county_shapefiles"] = [path.name for path in shp_files[:3]]

    return result


def build_summary() -> dict:
    ensure_pyshp()
    return {
        "nhgis_crosswalks": {
            key: inspect_nhgis_zip(path) for key, path in NHGIS_FILES.items()
        },
        "census_blocks": {
            "tabblock10": inspect_shapefile(BLOCK_SHAPEFILES["tabblock10"], ["GEOID10", "BLOCKCE10", "COUNTYFP10"]),
            "tabblock20": inspect_shapefile(BLOCK_SHAPEFILES["tabblock20"], ["GEOID20", "BLOCKCE20", "COUNTYFP20"]),
        },
        "optional_geometries": {
            "vtd10": inspect_vtd10_bundle(),
        },
    }


def main() -> int:
    summary = build_summary()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
