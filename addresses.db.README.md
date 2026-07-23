# addresses.db — frozen source-of-record backup

`addresses.db` (~2.9 GB, gitignored, lives only on this machine) is the complete
SCD-2 history database built by this tool before it was archived in July 2026:

- 71 snapshots of Toronto's Address Points dataset, feeds 2025-04-01 through 2026-07-21
- ~3.77 million history rows covering ~525k addresses, in the original 19-column schema

**Keep this file in place. Do not move or delete it.** It was deliberately left
here rather than moved to the snapshot vault. It cannot be regenerated: some of
the source GeoJSON files that fed it no longer exist, so `python run.py rebuild`
would produce an incomplete history. This file is the only complete record in
the old schema.

Successor: `ontario-address-changes/data/toronto/toronto.db` (generic schema,
different columns; active rows backfilled with kept fields on 2026-07-22). The
OSM import tooling in `toronto-2-address-import` reads that database now.

Frozen at snapshot 71 (feed date 2026-07-21), the final run of this tracker.
