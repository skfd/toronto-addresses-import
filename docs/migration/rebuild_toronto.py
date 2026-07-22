"""One-off: rebuild Toronto's SCD-2 history so keep_fields lands in props.

Phase 3 of toronto-addresses-import/docs/migration/MIGRATION_PLAN.md.

Snapshots come from address-vault, except two dates whose raw GeoJSON only
survives on disk in the tracker's data dir. Each cold day is thawed just before
its import; nothing holds all 94 days hot at once.

Builds to a side path so the live toronto.db is untouched until it verifies.

  python rebuild_toronto.py --target <dir> [--limit N] [--dry-run]
"""

import argparse
import json
import os
import sys
import time

ONTARIO = r"C:\Users\kk\Code\ontario-address-changes"
VAULTLIB = r"C:\Users\kk\Code\address-vault"
sys.path.insert(0, ONTARIO)
sys.path.insert(0, VAULTLIB)

from src import registry, db  # noqa: E402

# Dates absent from the vault but present as raw GeoJSON on disk. The other five
# vault-missing dates (2026-06-13/14/15/20/21) have no raw file anywhere and are
# accepted as lost -- addresses.db never had them either.
LOCAL_ONLY = {
    "2026-06-10": os.path.join(ONTARIO, "data", "toronto", "toronto-2026-06-10.geojson"),
    "2026-06-24": os.path.join(ONTARIO, "data", "toronto", "toronto-2026-06-24.geojson"),
}


def _resolve(vault, slug, date, thaw=True):
    """Hot path for a day, thawing it from the cold tier if needed.

    thaw=False reports what a day would cost without paying for it -- a dry run
    that thawed would restore all 94 days (~54 GB) to print a listing.
    """
    if date in LOCAL_ONLY:
        return LOCAL_ONLY[date], "local"
    from addressvault import Archived
    try:
        return vault.path(slug, date), "hot"
    except Archived:
        if not thaw:
            return None, "cold"
        vault.thaw(slug, date, ttl_hours=2, wait=True)
        return vault.path(slug, date), "thawed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="directory to build the new DB in")
    ap.add_argument("--limit", type=int, help="only import the first N dates")
    ap.add_argument("--dry-run", action="store_true", help="resolve paths only, no import")
    args = ap.parse_args()

    from addressvault import Vault
    vault = Vault()

    ds = registry.load("toronto")
    dates = sorted({s.date for s in vault.snapshots("toronto")} | set(LOCAL_ONLY))
    if args.limit:
        dates = dates[: args.limit]

    target = os.path.abspath(args.target)
    os.makedirs(target, exist_ok=True)
    # Point the dataset at the side-path DB; _connect() reads only these two.
    registry.Dataset.data_dir = property(lambda self: target)
    registry.Dataset.db_path = property(lambda self: os.path.join(target, "toronto.db"))

    print(f"rebuilding {len(dates)} snapshots -> {ds.db_path}")
    print(f"keep_fields = {ds.keep_fields}\n")

    t0 = time.time()
    for i, date in enumerate(dates, 1):
        ts = time.time()
        path, origin = _resolve(vault, "toronto", date, thaw=not args.dry_run)
        if args.dry_run:
            print(f"[{i:>3}/{len(dates)}] {date}  {origin:<7} {path or ''}")
            continue
        with open(path, encoding="utf-8") as f:
            features = json.load(f).get("features", [])
        db.import_snapshot(ds, path, features)
        el = time.time() - ts
        done = time.time() - t0
        eta = done / i * (len(dates) - i)
        print(f"[{i:>3}/{len(dates)}] {date}  {origin:<7} {len(features):>7,} feat  "
              f"{el:>6.1f}s  elapsed {done/60:>5.1f}m  eta {eta/60:>5.1f}m", flush=True)

    print(f"\ndone in {(time.time()-t0)/60:.1f} min -> {ds.db_path}")


if __name__ == "__main__":
    main()
