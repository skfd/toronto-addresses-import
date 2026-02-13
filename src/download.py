"""Download Toronto address points GeoJSON from the Open Data portal."""

import os
from datetime import date

import requests

DATASET_URL = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
    "abedd8bc-e3dd-4d45-8e69-79165a76e4fa/resource/"
    "b1c2ab72-dfe7-4b29-8550-6d1cfaa61733/download/address-points-4326.geojson"
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def download(force=False):
    """Download today's address points GeoJSON. Returns the file path.

    Skips if today's file already exists unless force=True.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"address-points-{date.today().isoformat()}.geojson"
    filepath = os.path.join(DATA_DIR, filename)

    if os.path.exists(filepath) and not force:
        print(f"Already downloaded: {filepath}")
        return filepath

    print(f"Downloading to {filepath} ...")
    resp = requests.get(DATASET_URL, stream=True, timeout=300)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    chunk_size = 1024 * 256  # 256 KB

    with open(filepath, "wb") as f:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded * 100 // total
                print(f"\r  {downloaded // (1024*1024)} / {total // (1024*1024)} MB ({pct}%)", end="", flush=True)

    print(f"\nDone: {filepath} ({downloaded // (1024*1024)} MB)")
    return filepath
