"""Generate static HTML change reports."""

import os
import re
import json
import math
from collections import Counter
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "reports")

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
            
            # Calculate bearing and distance if we have both coordinates
            suffix = ""
            if old_lat is not None and old_lon is not None and new_lat is not None and new_lon is not None:
                dy = new_lat - old_lat
                dx = (new_lon - old_lon) * 0.723  # Correct for Toronto latitude (~43.7N)
                if abs(dy) > 1e-6 or abs(dx) > 1e-6:
                    arrow = _get_bearing_arrow(dx, dy)
                    # Approximate distance in meters using Haversine-like flat Earth
                    dy_m = (new_lat - old_lat) * 111_320
                    dx_m = (new_lon - old_lon) * 111_320 * math.cos(math.radians((old_lat + new_lat) / 2))
                    dist_m = math.sqrt(dx_m**2 + dy_m**2)
                    suffix = f"{arrow} {dist_m:.1f}m"

            # Create formatted strings
            def fmt(lat, lon):
                if lat is None or lon is None:
                    return "—"
                return f"{lat:.5f}, {lon:.5f}"

            old_str = fmt(old_lat, old_lon)
            new_str = fmt(new_lat, new_lon)

            # Remove individual lat/lon changes
            changes = [c for c in changes if c["field"] not in ("latitude", "longitude")]

            # Add combined change
            changes.append({
                "field": "location",
                "old": old_str,
                "new": new_str,
                "arrow": suffix,
                "display_field": "Location"
            })
            mod["changes"] = changes

        for ch in mod["changes"]:
            if "display_field" not in ch:
                ch["display_field"] = FIELD_DISPLAY_NAMES.get(ch["field"], ch["field"])

    # Split modified into location-only vs significant changes
    # If an address has both location and other changes, it goes into significant
    modified_location = []
    modified_significant = []
    for mod in diff_result["modified"]:
        fields = {c["field"] for c in mod["changes"]}
        if fields == {"location"}:
            modified_location.append(mod)
        else:
            modified_significant.append(mod)

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

    current_counts = {
        "added": len(diff_result["added"]),
        "removed": len(diff_result["removed"]),
        "modified": len(modified_significant),
        "modified_location": len(modified_location),
    }
    sparklines = _compute_sparklines(date_part, current_counts)

    # Save template context as data file (for re-rendering without DB)
    context = {
        "generated": datetime.now().strftime("%b %d, %Y at %I:%M %p"),
        "old_snapshot": dict(old_snapshot),
        "new_snapshot": dict(new_snapshot),
        "old_date_friendly": _friendly_date(old_date_raw),
        "new_date_friendly": _friendly_date(new_date_raw),
        "added": diff_result["added"],
        "removed": diff_result["removed"],
        "modified": modified_significant,
        "modified_location": modified_location,
        "new_streets": diff_result.get("new_streets", []),
        "stats": stats,
        "added_count": len(diff_result["added"]),
        "removed_count": len(diff_result["removed"]),
        "modified_count": len(modified_significant),
        "modified_location_count": len(modified_location),
        "sparklines": sparklines,
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
    _update_report_metadata(new_snapshot["id"], date_part, filename, stats, diff_result, modified_location=len(modified_location))
    update_index()

    # Regenerate past reports whose added/removed rows share an address_point_id
    # with this one. Their histories now gain this new report's event.
    affected_point_ids = {r.get("address_point_id") for r in diff_result["added"] + diff_result["removed"]}
    affected_point_ids.discard(None)
    if affected_point_ids:
        rebuild_histories(affected_point_ids=affected_point_ids)

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

    # Streets with the most adds / removes today.
    # Surfaces subdivisions/developments (adds) and renumberings/demolitions (removes).
    street_added = Counter()
    street_removed = Counter()
    for row in diff_result["added"]:
        s = row.get("linear_name_full")
        if s:
            street_added[s] += 1
    for row in diff_result["removed"]:
        s = row.get("linear_name_full")
        if s:
            street_removed[s] += 1

    MIN_CHURN = 5
    top_streets_added = dict((s, n) for s, n in street_added.most_common(10) if n >= MIN_CHURN)
    top_streets_removed = dict((s, n) for s, n in street_removed.most_common(10) if n >= MIN_CHURN)

    return {
        "muni_added": dict(muni_added.most_common()),
        "muni_removed": dict(muni_removed.most_common()),
        "ward_added": dict(ward_added.most_common()),
        "ward_removed": dict(ward_removed.most_common()),
        "field_changes": dict(field_changes.most_common()),
        "top_streets_added": top_streets_added,
        "top_streets_removed": top_streets_removed,
    }


def _render_report_html(context):
    """Render report HTML from a context dict."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    env.globals["sparkline_svg"] = _sparkline_svg
    template = env.get_template("report.html")
    return template.render(**context)


SPARKLINE_KEYS = ("added", "removed", "modified", "modified_location")


def _compute_sparklines(current_date, current_counts):
    """Return {key: [int, ...]} trailing 7 non-skipped days ending at current_date."""
    meta_path = os.path.join(REPORTS_DIR, "metadata.json")
    entries = []
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
        for entry in data.values():
            if entry.get("filename") == "reports/#":
                continue
            d = entry.get("date")
            if not d or d >= current_date:
                continue
            entries.append(entry)

    entries.sort(key=lambda e: e["date"])
    prev = entries[-6:]

    def val(e, k):
        try:
            return int(e.get(k, 0) or 0)
        except (TypeError, ValueError):
            return 0

    out = {}
    for k in SPARKLINE_KEYS:
        out[k] = [val(e, k) for e in prev] + [int(current_counts.get(k, 0) or 0)]
    return out


def _sparkline_svg(values, color, width=110, height=20, pad=2):
    """Render a tiny inline SVG line sparkline. Last point is emphasized."""
    if not values:
        return ""
    n = len(values)
    vmax = max(values) if max(values) > 0 else 1
    inner_w = width - 2 * pad
    inner_h = height - 2 * pad
    if n == 1:
        xs = [pad + inner_w]
    else:
        xs = [pad + i * inner_w / (n - 1) for i in range(n)]
    ys = [pad + inner_h - (v / vmax) * inner_h for v in values]
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    last_x, last_y = xs[-1], ys[-1]
    return (
        f'<svg class="sparkline" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'preserveAspectRatio="none" aria-hidden="true">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round" points="{points}"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2" fill="{color}"/>'
        f'</svg>'
    )


def _enrich_context(context):
    """Backfill stats.top_streets and sparklines on contexts loaded from data.js."""
    diff_like = {
        "added": context.get("added", []),
        "removed": context.get("removed", []),
        "modified": list(context.get("modified", [])) + list(context.get("modified_location", [])),
    }
    stats = _compute_stats(diff_like)
    if stats.get("field_changes"):
        stats["field_changes"] = {
            FIELD_DISPLAY_NAMES.get(k, k): v
            for k, v in stats["field_changes"].items()
        }
    context["stats"] = stats

    ns = context.get("new_snapshot", {}) or {}
    date_part = None
    if ns.get("filename"):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", ns["filename"])
        if m:
            date_part = m.group(1)
    if not date_part and ns.get("downloaded"):
        date_part = ns["downloaded"][:10]
    if date_part:
        current_counts = {
            "added": context.get("added_count", 0),
            "removed": context.get("removed_count", 0),
            "modified": context.get("modified_count", 0),
            "modified_location": context.get("modified_location_count", 0),
        }
        context["sparklines"] = _compute_sparklines(date_part, current_counts)


_ARROW_SUFFIX_RE = re.compile(r" ([↗↑↖←↙↓↘→] \d+\.\d+m)$")


def _migrate_location_arrow(mods):
    """Move old-format arrow suffix from ch['new'] into ch['arrow'] for location changes."""
    for mod in mods:
        for ch in mod.get("changes", []):
            if ch.get("field") == "location" and "arrow" not in ch and ch.get("new"):
                m = _ARROW_SUFFIX_RE.search(ch["new"])
                if m:
                    ch["arrow"] = m.group(1)
                    ch["new"] = ch["new"][:m.start()]


def rebuild_histories(affected_point_ids=None):
    """Recompute history for every non-skipped report's added/removed rows.

    If affected_point_ids is provided (set of address_point_id ints),
    only reports with at least one added/removed row matching those ids are touched.
    Otherwise, all non-skipped reports are regenerated.
    """
    import glob as globmod
    import sqlite3

    from src.diff import compute_histories, _mark_current
    from src.db import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    data_files = sorted(globmod.glob(os.path.join(REPORTS_DIR, "report-*-data.js")))
    touched = 0
    for data_path in data_files:
        basename = os.path.basename(data_path)
        if "-skipped-data.js" in basename:
            continue
        html_name = basename.replace("-data.js", ".html")

        with open(data_path, "r", encoding="utf-8") as f:
            raw = f.read()
        json_str = raw.split("=", 1)[1].strip().rstrip(";")
        context = json.loads(json_str)

        added = context.get("added", [])
        removed = context.get("removed", [])
        if not added and not removed:
            continue

        pids_here = {r.get("address_point_id") for r in added + removed}
        pids_here.discard(None)
        if affected_point_ids is not None and pids_here.isdisjoint(affected_point_ids):
            continue

        new_snap_id = context["new_snapshot"]["id"]

        histories = compute_histories(conn, pids_here)
        for r in added:
            r["history"] = _mark_current(
                histories.get(r.get("address_point_id"), []),
                new_snap_id, "added",
            )
        for r in removed:
            r["history"] = _mark_current(
                histories.get(r.get("address_point_id"), []),
                new_snap_id, "removed",
            )

        with open(data_path, "w", encoding="utf-8") as f:
            f.write("window.REPORT_DATA = ")
            json.dump(context, f, indent=2, default=str)

        _migrate_location_arrow(context.get("modified", []))
        _migrate_location_arrow(context.get("modified_location", []))
        _enrich_context(context)
        html = _render_report_html(context)
        outpath = os.path.join(REPORTS_DIR, html_name)
        with open(outpath, "w", encoding="utf-8") as f:
            f.write(html)
        touched += 1
        print(f"History updated: {html_name}")

    conn.close()
    print(f"History updated in {touched} report(s).")


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

        # Migrate old location changes: extract arrow suffix from new into arrow key
        _migrate_location_arrow(context.get("modified", []))
        _migrate_location_arrow(context.get("modified_location", []))

        # Split modified into location-only vs significant if not already split
        if "modified_location" not in context and context.get("modified"):
            loc = []
            sig = []
            for mod in context["modified"]:
                fields = {c["field"] for c in mod.get("changes", [])}
                if fields == {"location"}:
                    loc.append(mod)
                else:
                    sig.append(mod)
            context["modified"] = sig
            context["modified_location"] = loc
            context["modified_count"] = len(sig)
            context["modified_location_count"] = len(loc)

        _enrich_context(context)
        html = _render_report_html(context)
        outpath = os.path.join(REPORTS_DIR, html_name)
        with open(outpath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Refreshed {html_name}")

    update_index()
    print("All reports refreshed.")


def update_index():
    """Regenerate index.html based on reports/metadata.json."""
    meta_path = os.path.join(REPORTS_DIR, "metadata.json")
    if not os.path.exists(meta_path):
        return

    with open(meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Backfill fields from data.js for entries that predate them
    metadata_changed = False
    for entry in data.values():
        if entry.get("filename", "reports/#") == "reports/#":
            continue
        needs_mod_loc = "modified_location" not in entry
        needs_streets = "new_streets" not in entry
        if not (needs_mod_loc or needs_streets):
            continue
        basename = os.path.basename(entry["filename"])
        data_js = os.path.join(REPORTS_DIR, basename.replace(".html", "-data.js"))
        if not os.path.exists(data_js):
            continue
        with open(data_js, "r", encoding="utf-8") as f:
            raw = f.read()
        json_str = raw.split("=", 1)[1].strip().rstrip(";")
        rd = json.loads(json_str)
        if needs_mod_loc:
            entry["modified_location"] = rd.get("modified_location_count", 0)
            metadata_changed = True
        if needs_streets:
            entry["new_streets"] = [
                {"street": s.get("street"), "count": s.get("count", 0)}
                for s in (rd.get("new_streets") or [])
            ]
            metadata_changed = True
    if metadata_changed:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # Deduplicate by date: keep the entry with the most total changes;
    # if tied, keep the one with the highest key (latest run).
    by_date = {}
    for key, entry in data.items():
        date = entry["date"]
        total = entry["added"] + entry["removed"] + entry["modified"]
        if date not in by_date:
            by_date[date] = (key, entry, total)
        else:
            prev_key, _, prev_total = by_date[date]
            if total > prev_total or (total == prev_total and int(key) > int(prev_key)):
                by_date[date] = (key, entry, total)

    # Sort by date desc
    reports = sorted((entry for _, entry, _ in by_date.values()), key=lambda x: x["date"], reverse=True)

    # Suppress zero-change (skipped) entries unless they are the most recent entry.
    # Between real-data entries they are just noise; the date gap implies no updates.
    if reports:
        most_recent = reports[0]
        reports = [
            r for r in reports
            if r["added"] + r["removed"] + r["modified"] > 0 or r is most_recent
        ]

    # Add friendly dates and determine the latest report with changes
    found_latest = False
    for report in reports:
        report["friendly_date"] = _friendly_date(report["date"])
        report["total_changes"] = report["added"] + report["removed"] + report["modified"]
        report["new_streets_count"] = sum(
            s.get("count", 0) for s in (report.get("new_streets") or [])
        )
        if not found_latest and report["total_changes"] > 0:
            report["is_latest"] = True
            found_latest = True
        else:
            report["is_latest"] = False

    # Flatten all new-street appearances across reports, newest first, cap at 15
    recent_new_streets = []
    for report in reports:
        for s in (report.get("new_streets") or []):
            recent_new_streets.append({
                "street": s.get("street"),
                "count": s.get("count", 0),
                "date": report["date"],
                "friendly_date": report["friendly_date"],
                "filename": report["filename"],
            })
    recent_new_streets = recent_new_streets[:15]

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    template = env.get_template("index.html")

    html = template.render(reports=reports, recent_new_streets=recent_new_streets)

    # Write to index.html (which is where GitHub Pages would serve from usually, or just root)
    # The user has index.html so let's overwrite that.
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    outpath = os.path.join(docs_dir, "index.html")

    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Index updated: {outpath}")


def _update_report_metadata(snapshot_id, date_str, filename, stats, diff_result, modified_location=0):
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

    new_streets = [
        {"street": s.get("street"), "count": s.get("count", 0)}
        for s in (diff_result.get("new_streets") or [])
    ]

    data[str(snapshot_id)] = {
        "date": date_str,
        "filename": f"reports/{filename}",  # Relative path from index.html
        "added": len(diff_result["added"]),
        "removed": len(diff_result["removed"]),
        "modified": len(diff_result["modified"]),
        "modified_location": modified_location,
        "new_streets": new_streets,
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
