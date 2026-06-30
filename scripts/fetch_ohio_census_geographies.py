from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
CENSUS_DIR = DATA_ROOT / "census"
TMP_DIR = DATA_ROOT / "_tmp_census_downloads"
VENDOR_PYSHP_DIR = PROJECT_ROOT / ".vendor" / "pyshp"


DATASETS = {
    "county10": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2010/COUNTY/2010/tl_2010_39_county10.zip",
        "zip_name": "tl_2010_39_county10.zip",
        "out_dir": CENSUS_DIR / "tl_2010_39_county10",
        "geojson": CENSUS_DIR / "tl_2010_39_county10.geojson",
        "keep_shapefile_dir": False,
    },
    "county20": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip",
        "zip_name": "tl_2020_us_county.zip",
        "out_dir": CENSUS_DIR / "tl_2020_39_county20",
        "geojson": CENSUS_DIR / "tl_2020_39_county20.geojson",
        "keep_shapefile_dir": False,
        "property_filter": {"STATEFP": "39"},
    },
    "tabblock10": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2010/TABBLOCK/2010/tl_2010_39_tabblock10.zip",
        "zip_name": "tl_2010_39_tabblock10.zip",
        "out_dir": CENSUS_DIR / "tl_2010_39_tabblock10",
        "geojson": CENSUS_DIR / "tl_2010_39_tabblock10" / "tl_2010_39_tabblock10.geojson",
        "keep_shapefile_dir": True,
    },
    "tabblock20": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_39_tabblock20.zip",
        "zip_name": "tl_2020_39_tabblock20.zip",
        "out_dir": CENSUS_DIR / "tl_2020_39_tabblock20",
        "geojson": CENSUS_DIR / "tl_2020_39_tabblock20" / "tl_2020_39_tabblock20.geojson",
        "keep_shapefile_dir": True,
    },
    "vtd10": {
        "index_url": "https://www2.census.gov/geo/tiger/TIGER2010/VTD/2010/",
        "filename_regex": r"^tl_2010_39\d{3}_vtd10\.zip$",
        "tmp_dir": TMP_DIR / "vtd10",
        "out_dir": CENSUS_DIR / "tl_2010_39_vtd10",
        "geojson": CENSUS_DIR / "tl_2010_39_vtd10" / "tl_2010_39_vtd10.geojson",
        "keep_shapefile_dir": True,
    },
    "vtd20": {
        "index_url": "https://www2.census.gov/geo/tiger/TIGER2020/VTD/",
        "filename_regex": r"^tl_2020_39\d{3}_vtd20\.zip$",
        "tmp_dir": TMP_DIR / "vtd20",
        "out_dir": CENSUS_DIR / "tl_2020_39_vtd20",
        "geojson": CENSUS_DIR / "tl_2020_39_vtd20" / "tl_2020_39_vtd20.geojson",
        "keep_shapefile_dir": True,
    },
    "cd118_2020": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2020/CD/CD118/tl_2020_39_cd118.zip",
        "zip_name": "tl_2020_39_cd118.zip",
        "out_dir": DATA_ROOT / "tileset" / "tl_2020_39_cd118",
        "geojson": DATA_ROOT / "tileset" / "oh_cd118_2020.geojson",
        "keep_shapefile_dir": True,
    },
    "cd118": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2022/CD/tl_2022_39_cd118.zip",
        "zip_name": "tl_2022_39_cd118.zip",
        "out_dir": DATA_ROOT / "tileset" / "tl_2022_39_cd118",
        "geojson": DATA_ROOT / "tileset" / "oh_cd118.geojson",
        "keep_shapefile_dir": True,
    },
    "cd119": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2024/CD/tl_2024_39_cd119.zip",
        "zip_name": "tl_2024_39_cd119.zip",
        "out_dir": DATA_ROOT / "tileset" / "tl_2024_39_cd119",
        "geojson": DATA_ROOT / "tileset" / "oh_cd119.geojson",
        "keep_shapefile_dir": True,
    },
    "sldl20": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2020/SLDL/tl_2020_39_sldl.zip",
        "zip_name": "tl_2020_39_sldl.zip",
        "out_dir": DATA_ROOT / "tileset" / "tl_2020_39_sldl",
        "geojson": DATA_ROOT / "tileset" / "oh_state_house_2020.geojson",
        "keep_shapefile_dir": True,
    },
    "sldu20": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2020/SLDU/tl_2020_39_sldu.zip",
        "zip_name": "tl_2020_39_sldu.zip",
        "out_dir": DATA_ROOT / "tileset" / "tl_2020_39_sldu",
        "geojson": DATA_ROOT / "tileset" / "oh_state_senate_2020.geojson",
        "keep_shapefile_dir": True,
    },
    "sldl22": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2022/SLDL/tl_2022_39_sldl.zip",
        "zip_name": "tl_2022_39_sldl.zip",
        "out_dir": DATA_ROOT / "tileset" / "tl_2022_39_sldl",
        "geojson": DATA_ROOT / "tileset" / "oh_state_house_2022.geojson",
        "keep_shapefile_dir": True,
    },
    "sldu22": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2022/SLDU/tl_2022_39_sldu.zip",
        "zip_name": "tl_2022_39_sldu.zip",
        "out_dir": DATA_ROOT / "tileset" / "tl_2022_39_sldu",
        "geojson": DATA_ROOT / "tileset" / "oh_state_senate_2022.geojson",
        "keep_shapefile_dir": True,
    },
    "sldl24": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2024/SLDL/tl_2024_39_sldl.zip",
        "zip_name": "tl_2024_39_sldl.zip",
        "out_dir": DATA_ROOT / "tileset" / "tl_2024_39_sldl",
        "geojson": DATA_ROOT / "tileset" / "oh_state_house_2024.geojson",
        "keep_shapefile_dir": True,
    },
    "sldu24": {
        "url": "https://www2.census.gov/geo/tiger/TIGER2024/SLDU/tl_2024_39_sldu.zip",
        "zip_name": "tl_2024_39_sldu.zip",
        "out_dir": DATA_ROOT / "tileset" / "tl_2024_39_sldu",
        "geojson": DATA_ROOT / "tileset" / "oh_state_senate_2024.geojson",
        "keep_shapefile_dir": True,
    },
}


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


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url) as response, dest.open("wb") as fh:
        shutil.copyfileobj(response, fh)


def extract(zip_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)


def find_shapefile(out_dir: Path) -> Path:
    shp_files = sorted(out_dir.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError(f"No .shp file found in {out_dir}")
    return shp_files[0]


def iter_features_from_shapefile(shp_path: Path, property_filter: dict | None = None) -> list[dict]:
    import shapefile

    reader = shapefile.Reader(str(shp_path))
    fields = [field[0] for field in reader.fields[1:]]
    features = []
    for sr in reader.iterShapeRecords():
        properties = dict(zip(fields, sr.record))
        if property_filter:
            matched = True
            for key, expected in property_filter.items():
                if str(properties.get(key, "")).strip() != str(expected):
                    matched = False
                    break
            if not matched:
                continue
        geometry = sr.shape.__geo_interface__
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": geometry,
            }
        )
    return features


def write_geojson(features: list[dict], geojson_path: Path) -> None:
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    with geojson_path.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)


def convert_shapefile_to_geojson(shp_path: Path, geojson_path: Path, property_filter: dict | None = None) -> int:
    features = iter_features_from_shapefile(shp_path, property_filter=property_filter)
    write_geojson(features, geojson_path)
    return len(features)


def list_directory_links(index_url: str, pattern: str) -> list[str]:
    with urlopen(index_url) as response:
        html = response.read().decode("utf-8", errors="ignore")
    matches = sorted(set(re.findall(r'href="([^"]+)"', html)))
    return [name for name in matches if re.fullmatch(pattern, name)]


def extract_all(zip_path: Path, out_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)


def fetch_directory_dataset(key: str, force: bool = False) -> dict:
    spec = DATASETS[key]
    tmp_dir = spec["tmp_dir"]
    out_dir = spec["out_dir"]
    geojson_path = spec["geojson"]

    if force and out_dir.exists():
        shutil.rmtree(out_dir)
    if force and geojson_path.exists():
        geojson_path.unlink()

    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    filenames = list_directory_links(spec["index_url"], spec["filename_regex"])
    if not filenames:
        raise FileNotFoundError(f"No matching files found at {spec['index_url']}")

    all_features: list[dict] = []
    for filename in filenames:
        zip_path = tmp_dir / filename
        if force and zip_path.exists():
            zip_path.unlink()
        if not zip_path.exists():
            download(f"{spec['index_url']}{filename}", zip_path)
        extract_all(zip_path, out_dir)

    for shp_path in sorted(out_dir.glob("*.shp")):
        all_features.extend(iter_features_from_shapefile(shp_path))

    write_geojson(all_features, geojson_path)
    return {
        "dataset": key,
        "url": spec["index_url"],
        "file_count": len(filenames),
        "geojson_path": str(geojson_path),
        "feature_count": len(all_features),
    }


def fetch_dataset(key: str, force: bool = False) -> dict:
    spec = DATASETS[key]
    if "index_url" in spec:
        return fetch_directory_dataset(key, force=force)

    zip_path = TMP_DIR / spec["zip_name"]
    local_zip_path = CENSUS_DIR / spec["zip_name"]
    geojson_path = spec["geojson"]
    out_dir = spec["out_dir"]
    if force:
        if zip_path.exists():
            zip_path.unlink()
        if geojson_path.exists():
            geojson_path.unlink()

    if not zip_path.exists():
        if local_zip_path.exists():
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local_zip_path, zip_path)
        else:
            download(spec["url"], zip_path)
    extract(zip_path, out_dir)
    shp_path = find_shapefile(out_dir)
    feature_count = convert_shapefile_to_geojson(
        shp_path,
        geojson_path,
        property_filter=spec.get("property_filter"),
    )
    return {
        "dataset": key,
        "url": spec["url"],
        "zip_path": str(zip_path),
        "geojson_path": str(geojson_path),
        "feature_count": feature_count,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Ohio Census TIGER/Line files and convert them to GeoJSON."
    )
    parser.add_argument(
        "datasets",
        nargs="*",
        default=["county10", "county20", "tabblock10", "tabblock20", "vtd10"],
        choices=sorted(DATASETS.keys()),
        help="Dataset keys to fetch.",
    )
    parser.add_argument("--force", action="store_true", help="Redownload and rebuild outputs.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    ensure_pyshp()
    args = parse_args(argv)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for key in args.datasets:
        print(f"Fetching {key}...", file=sys.stderr)
        results.append(fetch_dataset(key, force=args.force))
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
