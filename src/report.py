"""Generate static HTML change reports."""

import os
from collections import Counter
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")


def generate_report(diff_result, old_snapshot, new_snapshot):
    """Generate an HTML report from a diff result. Returns the output file path."""
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # Compute summary stats
    stats = _compute_stats(diff_result)

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    template = env.get_template("report.html")

    html = template.render(
        generated=datetime.now().isoformat(timespec="seconds"),
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        added=diff_result["added"],
        removed=diff_result["removed"],
        modified=diff_result["modified"],
        stats=stats,
        added_count=len(diff_result["added"]),
        removed_count=len(diff_result["removed"]),
        modified_count=len(diff_result["modified"]),
    )

    # Name by new snapshot date
    date_part = new_snapshot["downloaded"][:10]
    outpath = os.path.join(REPORTS_DIR, f"report-{date_part}.html")
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report written to {outpath}")
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
