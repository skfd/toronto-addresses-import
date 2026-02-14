"""Download Toronto address points GeoJSON from the Open Data portal."""

import os
from datetime import date, datetime

import requests

from src.db import get_last_snapshot_headers, init_db

DATASET_URL = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
    "abedd8bc-e3dd-4d45-8e69-79165a76e4fa/resource/"
    "b1c2ab72-dfe7-4b29-8550-6d1cfaa61733/download/address-points-4326.geojson"
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def download(force=False):
    """Download today's address points GeoJSON. 
    
    Returns:
        (status, data, extra)
        status: "DOWNLOADED" or "SKIPPED"
        data: filepath (if downloaded) or reason (if skipped)
        extra: headers dict (if downloaded) or None
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 1. Check remote headers
    print("Checking for updates...")
    try:
        head_resp = requests.head(DATASET_URL, timeout=10)
        head_resp.raise_for_status()
        remote_headers = {
            "Last-Modified": head_resp.headers.get("Last-Modified"),
            "Content-Length": _parse_int(head_resp.headers.get("Content-Length")),
        }
    except requests.RequestException as e:
        print(f"Warning: Could not check remote headers: {e}")
        remote_headers = {}

    # 2. Compare with local
    if not force and remote_headers:
        # Ensure DB is ready so we can query snapshots
        init_db()
        last = get_last_snapshot_headers()
        
        if last:
            # Check if remote matches local
            matches = True
            if remote_headers.get("Last-Modified") != last.get("remote_last_modified"):
                matches = False
            elif remote_headers.get("Content-Length") != last.get("remote_content_length"):
                matches = False
                
            if matches:
                return "SKIPPED", "Remote file has not changed since last download.", None

    # 3. Download
    # Use Last-Modified date for filename if available, otherwise today
    file_date = date.today()
    if remote_headers.get("Last-Modified"):
        try:
            # Example: Fri, 13 Feb 2026 11:40:00 GMT
            lm = datetime.strptime(remote_headers["Last-Modified"], "%a, %d %b %Y %H:%M:%S %Z")
            file_date = lm.date()
        except ValueError:
            pass

    filename = f"address-points-{file_date.isoformat()}.geojson"
    filepath = os.path.join(DATA_DIR, filename)

    if os.path.exists(filepath) and not force:
        print(f"Already downloaded: {filepath}")
        # Even if file exists locally, we return it as 'DOWNLOADED' so import proceeds
        # (unless we add logic to check if it's already imported, but db.import_geojson handles that)
        return "DOWNLOADED", filepath, remote_headers

    print(f"Downloading to {filepath} ...")
    resp = requests.get(DATASET_URL, stream=True, timeout=300)
    resp.raise_for_status()

    # Capture actual headers from GET response if HEAD failed or differed
    final_headers = {
        "Last-Modified": resp.headers.get("Last-Modified"),
        "Content-Length": _parse_int(resp.headers.get("Content-Length")),
    }

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
    return "DOWNLOADED", filepath, final_headers


def _parse_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
