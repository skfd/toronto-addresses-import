"""Generate static HTML change reports."""

import os
import re
import json
import math
from collections import Counter
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")

# Human-friendly field name mapping for display
FIELD_DISPLAY_NAMES = {
    "address_full": "Full Address",
    "address_number": "Address Number",
    "lo_num": "Low Number",
    "lo_num_suf": "Low Number Suffix",
    "hi_num": "High Number",
    "hi_num_suf": "High Number Suffix",
    "linear_name_full": "Street Name",
    "linear_name": "Street",
    "linear_name_type": "Street Type",
    "linear_name_dir": "Street Direction",
    "municipality_name": "Municipality",
    "ward_name": "Ward",
    "longitude": "Location (longitude)",
    "latitude": "Location (latitude)",
}


def _friendly_date(date_str):
    """Convert YYYY-MM-DD to a human-friendly date like 'Thursday, Feb 13, 2026'."""
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return dt.strftime("%A, %b %d, %Y")
    except (ValueError, TypeError):
        return date_str


def _get_bearing_arrow(dx, dy):
    """Return an arrow emoji based on the vector (dx, dy)."""
    if dx == 0 and dy == 0:
        return ""
    
    # atan2 returns angle in radians, -pi to +pi
    # 0 is East (positive x), pi/2 is North (positive y)
    angle = math.degrees(math.atan2(dy, dx))
    
    # Normalize to 0-360
    angle = (angle + 360) % 360
    
    # Map to 8 directions (45 degrees each)
    # East (0) is [337.5, 22.5]
    idx = int((angle + 22.5) // 45) % 8
    arrows = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]
    return arrows[idx]


def generate_report(diff_result, old_snapshot, new_snapshot):
    """Generate an HTML report from a diff result. Returns the output file path."""
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # Compute summary stats
    stats = _compute_stats(diff_result)

    # Humanize field names in the changes
    for mod in diff_result["modified"]:
        # Check for coordinate changes to combine
        changes = mod["changes"]
        lat_change = next((c for c in changes if c["field"] == "latitude"), None)
        lon_change = next((c for c in changes if c["field"] == "longitude"), None)

        if lat_change or lon_change:
            # Get current values (from diff.py's augmented modified dict) or fallbacks
            new_lat = mod.get("latitude")
            new_lon = mod.get("longitude")
            
            # For old values, we need to subtract the delta if we have a change record
            # If no change record for one component, it means it didn't change (delta=0)
            
            old_lat = lat_change["old"] if lat_change else new_lat
            # new_lat is already the 'new' value. 
            # If lat didn't change, old_lat == new_lat.
            
            old_lon = lon_change["old"] if lon_change else new_lon
            
            # Calculate bearing if we have both coordinates
            arrow = ""
            if old_lat is not None and old_lon is not None and new_lat is not None and new_lon is not None:
                dy = new_lat - old_lat
                dx = (new_lon - old_lon) * 0.723  # Correct for Toronto latitude (~43.7N)
                if abs(dy) > 1e-6 or abs(dx) > 1e-6:
                    arrow = " " + _get_bearing_arrow(dx, dy)
            
            # Create formatted strings
            # If a value is None (unlikely for lat/lon but possible), handle gracefully
            def fmt(lat, lon):
                if lat is None or lon is None:
                    return "—"
                return f"{lat:.6f}, {lon:.6f}"

            old_str = fmt(old_lat, old_lon)
            new_str = fmt(new_lat, new_lon) + arrow
            
            # Remove individual lat/lon changes
            changes = [c for c in changes if c["field"] not in ("latitude", "longitude")]
            
            # Add combined change
            changes.append({
                "field": "location",
                "old": old_str,
                "new": new_str,
                "display_field": "Location"
            })
            mod["changes"] = changes

        for ch in mod["changes"]:
            if "display_field" not in ch:
                ch["display_field"] = FIELD_DISPLAY_NAMES.get(ch["field"], ch["field"])

    # Humanize field names in stats
    if stats.get("field_changes"):
        stats["field_changes"] = {
            FIELD_DISPLAY_NAMES.get(k, k): v
            for k, v in stats["field_changes"].items()
        }

    # Format dates
    old_date_raw = old_snapshot["downloaded"][:10]
    new_date_raw = new_snapshot["downloaded"][:10]

    # Name by new snapshot date
    # Try to extract date from filename first, else use downloaded time
    match = re.search(r"(\d{4}-\d{2}-\d{2})", new_snapshot["filename"])
    if match:
        date_part = match.group(1)
    else:
        date_part = new_snapshot["downloaded"][:10]

    # Save template context as data file (for re-rendering without DB)
    context = {
        "generated": datetime.now().strftime("%b %d, %Y at %I:%M %p"),
        "old_snapshot": dict(old_snapshot),
        "new_snapshot": dict(new_snapshot),
        "old_date_friendly": _friendly_date(old_date_raw),
        "new_date_friendly": _friendly_date(new_date_raw),
        "added": diff_result["added"],
        "removed": diff_result["removed"],
        "modified": diff_result["modified"],
        "stats": stats,
        "added_count": len(diff_result["added"]),
        "removed_count": len(diff_result["removed"]),
        "modified_count": len(diff_result["modified"]),
    }

    data_path = os.path.join(REPORTS_DIR, f"report-{date_part}-data.js")
    with open(data_path, "w", encoding="utf-8") as f:
        f.write("window.REPORT_DATA = ")
        json.dump(context, f, indent=2, default=str)

    # Render HTML from context
    html = _render_report_html(context)

    filename = f"report-{date_part}.html"
    outpath = os.path.join(REPORTS_DIR, filename)
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report written to {outpath}")

    # Update index
    # Use ID to ensure uniqueness
    _update_report_metadata(new_snapshot["id"], date_part, filename, stats, diff_result)
    update_index()

    return outpath


def generate_no_changes_report():
    """Generate a report indicating no changes were found."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # Get latest snapshot for row count
    from src.db import get_latest_snapshots
    snapshots = get_latest_snapshots(1)
    row_count = snapshots[0]["row_count"] if snapshots else 0
    
    date_part = datetime.now().strftime("%Y-%m-%d")
    filename = f"report-{date_part}-skipped.html"
    outpath = os.path.join(REPORTS_DIR, filename)

    dummy_snapshot = {
        "downloaded": datetime.now().isoformat(),
        "filename": "No New Data",
        "id": "-",
        "row_count": row_count
    }

    context = {
        "generated": datetime.now().strftime("%b %d, %Y at %I:%M %p"),
        "old_snapshot": dummy_snapshot,
        "new_snapshot": dummy_snapshot,
        "old_date_friendly": _friendly_date(date_part),
        "new_date_friendly": _friendly_date(date_part),
        "added": [],
        "removed": [],
        "modified": [],
        "stats": {},
        "added_count": 0,
        "removed_count": 0,
        "modified_count": 0,
        "is_skipped": True,
    }

    # Save data file for re-rendering
    data_path = os.path.join(REPORTS_DIR, f"report-{date_part}-skipped-data.js")
    with open(data_path, "w", encoding="utf-8") as f:
        f.write("window.REPORT_DATA = ")
        json.dump(context, f, indent=2, default=str)

    html = _render_report_html(context)

    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"No-changes report written to {outpath}")
    
    # Update index
    skipped_id = int(datetime.now().timestamp())
    
    _update_report_metadata(
        skipped_id, 
        date_part, 
        filename, 
        {"muni_added":{}, "muni_removed":{}, "field_changes":{}}, 
        {"added":[], "removed":[], "modified":[]}
    )
    update_index()
    
    return outpath


def _compute_stats(diff_result):
    """Compute per-municipality and per-ward change counts."""
    muni_added = Counter()
    muni_removed = Counter()
    ward_added = Counter()
    ward_removed = Counter()

    for row in diff_result["added"]:
        m = row.get("municipality_name") or "Unknown"
        w = row.get("ward_name") or "Unknown"
        muni_added[m] += 1
        ward_added[w] += 1

    for row in diff_result["removed"]:
        m = row.get("municipality_name") or "Unknown"
        w = row.get("ward_name") or "Unknown"
        muni_removed[m] += 1
        ward_removed[w] += 1

    # Which fields change most often
    field_changes = Counter()
    for mod in diff_result["modified"]:
        for ch in mod["changes"]:
            field_changes[ch["field"]] += 1

    return {
        "muni_added": dict(muni_added.most_common()),
        "muni_removed": dict(muni_removed.most_common()),
        "ward_added": dict(ward_added.most_common()),
        "ward_removed": dict(ward_removed.most_common()),
        "field_changes": dict(field_changes.most_common()),
    }


def _render_report_html(context):
    """Render report HTML from a context dict."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    template = env.get_template("report.html")
    return template.render(**context)


def refresh_reports():
    """Re-render all HTML reports from existing -data.js files (no DB needed)."""
    import glob as globmod
    data_files = sorted(globmod.glob(os.path.join(REPORTS_DIR, "report-*-data.js")))
    if not data_files:
        print("No data files found in reports/.")
        return

    for data_path in data_files:
        basename = os.path.basename(data_path)
        # report-2026-02-13-data.js -> report-2026-02-13.html
        html_name = basename.replace("-data.js", ".html")

        with open(data_path, "r", encoding="utf-8") as f:
            raw = f.read()

        # Strip the "window.REPORT_DATA = " prefix and any trailing semicolon
        json_str = raw.split("=", 1)[1].strip().rstrip(";")
        context = json.loads(json_str)

        html = _render_report_html(context)
        outpath = os.path.join(REPORTS_DIR, html_name)
        with open(outpath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Refreshed {html_name}")

    update_index()
    print("All reports refreshed.")


def update_index():
    """Regenerate docs/index.html based on reports/metadata.json."""
    meta_path = os.path.join(REPORTS_DIR, "metadata.json")
    if not os.path.exists(meta_path):
        return

    with open(meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Sort by date desc
    reports = sorted(data.values(), key=lambda x: x["date"], reverse=True)

    # Add friendly dates and determine the latest report with changes
    found_latest = False
    for report in reports:
        report["friendly_date"] = _friendly_date(report["date"])
        report["total_changes"] = report["added"] + report["removed"] + report["modified"]
        if not found_latest and report["total_changes"] > 0:
            report["is_latest"] = True
            found_latest = True
        else:
            report["is_latest"] = False

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    template = env.get_template("index.html")

    html = template.render(reports=reports)

    # Write to docs/index.html (which is where GitHub Pages would serve from usually, or just root)
    # The user has docs/index.html so let's overwrite that.
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    outpath = os.path.join(docs_dir, "index.html")

    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Index updated: {outpath}")


def _update_report_metadata(snapshot_id, date_str, filename, stats, diff_result):
    """Update the JSON metadata file with stats for this report."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    meta_path = os.path.join(REPORTS_DIR, "metadata.json")

    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    else:
        data = {}

    data[str(snapshot_id)] = {
        "date": date_str,
        "filename": f"../reports/{filename}",  # Relative path from docs/index.html
        "added": len(diff_result["added"]),
        "removed": len(diff_result["removed"]),
        "modified": len(diff_result["modified"]),
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
