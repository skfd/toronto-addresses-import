"""CLI entry point for the Toronto address change tracker."""

import argparse
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from src.download import download
from src.db import import_geojson, get_latest_snapshots, init_db
from src.diff import compute_diff
from src.report import generate_report


def cmd_download(args):
    filepath = download(force=args.force)
    print(f"GeoJSON ready: {filepath}")


def cmd_import(args):
    if args.file:
        import_geojson(args.file)
    else:
        # Import the most recent file in data/
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        if not os.path.isdir(data_dir):
            print("No data/ directory. Run 'download' first.")
            return
        files = sorted(f for f in os.listdir(data_dir) if f.endswith(".geojson"))
        if not files:
            print("No GeoJSON files in data/. Run 'download' first.")
            return
        filepath = os.path.join(data_dir, files[-1])
        import_geojson(filepath)


def cmd_diff(args):
    init_db()
    snapshots = get_latest_snapshots(2)
    if len(snapshots) < 2:
        print("Need at least 2 snapshots to diff. Import more data first.")
        return
    old, new = snapshots[0], snapshots[1]
    print(f"Diffing snapshot {old['id']} → {new['id']} ...")
    result = compute_diff(old["id"], new["id"])
    print(f"  Added:    {len(result['added']):,}")
    print(f"  Removed:  {len(result['removed']):,}")
    print(f"  Modified: {len(result['modified']):,}")
    return result, old, new


def cmd_report(args):
    diff_data = cmd_diff(args)
    if diff_data is None:
        return
    result, old, new = diff_data
    outpath = generate_report(result, old, new)
    print(f"Open in browser: {outpath}")


def cmd_update(args):
    """Download, import, diff, and generate a report in one go."""
    print("=== Download ===")
    filepath = download(force=args.force)
    print()
    print("=== Import ===")
    import_geojson(filepath)
    print()
    print("=== Diff & Report ===")
    cmd_report(args)


def main():
    parser = argparse.ArgumentParser(
        description="Toronto Address Change Tracker",
    )
    sub = parser.add_subparsers(dest="command")

    dl = sub.add_parser("download", help="Download today's address GeoJSON")
    dl.add_argument("--force", action="store_true", help="Re-download even if file exists")

    imp = sub.add_parser("import", help="Import a GeoJSON into the database")
    imp.add_argument("--file", help="Path to GeoJSON file (default: latest in data/)")

    sub.add_parser("diff", help="Show diff between latest two snapshots")

    sub.add_parser("report", help="Generate HTML report for latest diff")

    up = sub.add_parser("update", help="Download + import + diff + report")
    up.add_argument("--force", action="store_true", help="Force re-download")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "download": cmd_download,
        "import": cmd_import,
        "diff": cmd_diff,
        "report": cmd_report,
        "update": cmd_update,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
