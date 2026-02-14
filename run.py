"""CLI entry point for the Toronto address change tracker."""

import argparse
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from src.download import download
from src.db import import_geojson, get_latest_snapshots, init_db, record_skipped_snapshot
from src.diff import compute_diff
from src.report import generate_report


def cmd_download(args):
    status, data, _ = download(force=args.force)
    if status == "SKIPPED":
        print(f"Skipped download: {data}")
    else:
        print(f"GeoJSON ready: {data}")


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
    status, data, headers = download(force=args.force)
    
    if status == "SKIPPED":
        print(f"\nSkipped: {data}")
        print("Recording skipped snapshot...")
        record_skipped_snapshot("skipped-download", data)
        
        from src.report import generate_no_changes_report
        outpath = generate_no_changes_report()
        print(f"Report generated: {outpath}")
        return

    print()
    print("=== Import ===")
    import_geojson(data, headers=headers)
    print()
    print("=== Diff & Report ===")
    cmd_report(args)


def cmd_rebuild(args):
    """Delete the database and re-import all GeoJSON files in data/."""
    from src.db import DB_PATH
    
    if os.path.exists(DB_PATH):
        print(f"Deleting existing database: {DB_PATH}")
        os.remove(DB_PATH)
    
    # data_dir logic
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    if not os.path.isdir(data_dir):
        print("No data/ directory found.")
        return

    files = sorted(f for f in os.listdir(data_dir) if f.endswith(".geojson"))
    if not files:
        print("No GeoJSON files found in data/.")
        return

    print(f"Found {len(files)} snapshots to import. Rebuilding...")
    for f in files:
        filepath = os.path.join(data_dir, f)
        import_geojson(filepath)
    
    print("Rebuild complete.")


def cmd_report_all(args):
    """Generate reports for ALL snapshots in the database."""
    snapshots = get_latest_snapshots(9999) # Get all
    if not snapshots:
        print("No snapshots found.")
        return
    
    # Sort old -> new
    snapshots.sort(key=lambda x: x["id"])
    
    import src.report
    from src.report import _update_report_metadata, update_index
    
    print(f"Found {len(snapshots)} snapshots. Generating reports...")

    for i, snap in enumerate(snapshots):
        if i == 0:
            # First snapshot: No diff possible, but we want it in the index
            import re
            match = re.search(r"(\d{4}-\d{2}-\d{2})", snap["filename"])
            date_part = match.group(1) if match else snap["downloaded"][:10]
            
            print(f"[{date_part}] Initial Import (Snapshot {snap['id']})")
            
            # Manually update metadata for the first one
            _update_report_metadata(snap["id"], date_part, "#", 
                                    {"added": snap["row_count"], "removed": 0, "modified": 0},
                                    {"added": range(snap["row_count"]), "removed": [], "modified": []}) # Fake diff result
            
            pass
        else:
            old = snapshots[i-1]
            new = snap
            print(f"[{new['downloaded'][:10]}] Diffing {old['id']} -> {new['id']}...")
            result = compute_diff(old["id"], new["id"])
            generate_report(result, old, new)

    update_index()
    print("All reports generated.")


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

    sub.add_parser("report-all", help="Regenerate reports for entire history")

    up = sub.add_parser("update", help="Download + import + diff + report")
    up.add_argument("--force", action="store_true", help="Force re-download")

    sub.add_parser("rebuild", help="Delete DB and re-import all historical data")

    sub.add_parser("verify", help="Verify logic by comparing raw files")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "download": cmd_download,
        "import": cmd_import,
        "diff": cmd_diff,
        "report": cmd_report,
        "report-all": cmd_report_all,
        "update": cmd_update,
        "rebuild": cmd_rebuild,
        "verify": lambda a: __import__("src.verify_diff").verify_diff.verify_diff(
            *([s["id"] for s in  __import__("src.db").db.get_latest_snapshots(2)] if len(__import__("src.db").db.get_latest_snapshots(2)) >= 2 else [None, None])
        )
    }
    
    if args.command == "verify":
        from src.verify_diff import verify_diff
        from src.db import get_latest_snapshots
        snaps = get_latest_snapshots(2)
        if len(snaps) < 2:
            print("Not enough snapshots.")
            return
        verify_diff(snaps[0]["id"], snaps[1]["id"])
    else:
        commands[args.command](args)


if __name__ == "__main__":
    main()
