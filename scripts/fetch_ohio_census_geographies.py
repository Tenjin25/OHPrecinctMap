from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
CENSUS_DIR = DATA_ROOT / "census"
TMP_DIR = DATA_ROOT / "_tmp_census_downloads"


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
    try:
        import shapefile  # noqa: F401
    except ImportError as exc:  # pragma: no cover - runtime guard
        raise SystemExit(
            "Missing dependency 'pyshp'. Install it with: pip install pyshp"
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


def convert_shapefile_to_geojson(shp_path: Path, geojson_path: Path, property_filter: dict | None = None) -> int:
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
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    with geojson_path.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)
    return len(features)


def fetch_dataset(key: str, force: bool = False) -> dict:
    spec = DATASETS[key]
    zip_path = TMP_DIR / spec["zip_name"]
    geojson_path = spec["geojson"]
    out_dir = spec["out_dir"]
    if force:
        if zip_path.exists():
            zip_path.unlink()
        if geojson_path.exists():
            geojson_path.unlink()

    if not zip_path.exists():
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
        default=["county10", "county20", "tabblock10", "tabblock20"],
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
