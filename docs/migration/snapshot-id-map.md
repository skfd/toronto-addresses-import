# Snapshot ID -> date map

Frozen 2026-07-21, before the keep_fields rebuild.

Snapshot IDs are per-database AUTOINCREMENT sequences and are **not portable**. The maintenance
watermark in t2 (`kv["maintenance.watermark_snapshot"]`) is a bare integer, so it MUST be
translated by date, never carried across as a number.

Watermark **56** = **2026-06-05** in addresses.db = id **58** in toronto.db (pre-rebuild).
Carrying 56 across naively would mean 2026-06-02 and silently widen the window (59 additions vs 57).

| store | dated snapshots | notes |
|---|---|---|
| addresses.db (this repo, retired) | 70 | plus id 8 = `skipped-download`, undated, which offsets all later IDs |
| toronto.db (ontario-address-changes, pre-rebuild) | 89 | |
| address-vault | 94 | rebuild source |
| union of all three | 101 distinct dates | |

Dates in toronto.db but absent from the vault (unrecoverable, no raw GeoJSON anywhere):
2026-06-13, 2026-06-14, 2026-06-15, 2026-06-20, 2026-06-21 — none were in addresses.db either,
so losing them is not a regression for t2. 2026-06-10 and 2026-06-24 survive as on-disk GeoJSON
and are seeded into the vault in Phase 3.

| date | addresses.db | toronto.db | vault |
|---|---|---|---|
| 2025-04-01 | 1 | 1 | yes |
| 2025-09-09 | 2 | 2 | yes |
| 2026-02-12 | 3 | 3 | yes |
| 2026-02-13 | 4 | 4 | yes |
| 2026-02-14 | - | 5 | yes |
| 2026-02-20 | 5 | 6 | yes |
| 2026-02-23 | 6 | 7 | yes |
| 2026-02-24 | 7 | 8 | yes |
| 2026-02-27 | 9 | 9 | yes |
| 2026-03-03 | 10 | 10 | yes |
| 2026-03-04 | 11 | 11 | yes |
| 2026-03-06 | 12 | 12 | yes |
| 2026-03-07 | 13 | 13 | yes |
| 2026-03-09 | - | 14 | yes |
| 2026-03-10 | 14 | 15 | yes |
| 2026-03-12 | 15 | 16 | yes |
| 2026-03-17 | 16 | 17 | yes |
| 2026-03-20 | 17 | 18 | yes |
| 2026-03-23 | 18 | 19 | yes |
| 2026-03-24 | 19 | 20 | yes |
| 2026-03-25 | 20 | 21 | yes |
| 2026-03-26 | 21 | 22 | yes |
| 2026-03-27 | 22 | 23 | yes |
| 2026-04-02 | 23 | 24 | yes |
| 2026-04-03 | 24 | 25 | yes |
| 2026-04-08 | 25 | 26 | yes |
| 2026-04-09 | - | 27 | yes |
| 2026-04-10 | 26 | 28 | yes |
| 2026-04-13 | 27 | 29 | yes |
| 2026-04-16 | 28 | 30 | yes |
| 2026-04-21 | 29 | 31 | yes |
| 2026-04-22 | 30 | 32 | yes |
| 2026-04-23 | 31 | 33 | yes |
| 2026-04-24 | 32 | 34 | yes |
| 2026-04-27 | 33 | 35 | yes |
| 2026-04-28 | 34 | 36 | yes |
| 2026-04-29 | 35 | 37 | yes |
| 2026-04-30 | 36 | 38 | yes |
| 2026-05-01 | 37 | 39 | yes |
| 2026-05-04 | 38 | 40 | yes |
| 2026-05-07 | 39 | 41 | yes |
| 2026-05-08 | 40 | 42 | yes |
| 2026-05-11 | 41 | 43 | yes |
| 2026-05-12 | 42 | 44 | yes |
| 2026-05-13 | 43 | 45 | yes |
| 2026-05-14 | 44 | 46 | yes |
| 2026-05-15 | 45 | 47 | yes |
| 2026-05-18 | 46 | 48 | yes |
| 2026-05-20 | 47 | 49 | yes |
| 2026-05-21 | 48 | 50 | yes |
| 2026-05-22 | 49 | 51 | yes |
| 2026-05-26 | 50 | 52 | yes |
| 2026-05-27 | 51 | 53 | yes |
| 2026-05-28 | 52 | 54 | yes |
| 2026-05-29 | 53 | 55 | yes |
| 2026-06-02 | 54 | 56 | yes |
| 2026-06-04 | 55 | 57 | yes |
| 2026-06-05 | 56 | 58 | yes |
| 2026-06-08 | 57 | 59 | yes |
| 2026-06-09 | 58 | 60 | yes |
| 2026-06-10 | - | 61 | - |
| 2026-06-11 | 59 | 62 | yes |
| 2026-06-12 | 60 | 63 | yes |
| 2026-06-13 | - | 64 | - |
| 2026-06-14 | - | 65 | - |
| 2026-06-15 | - | 66 | - |
| 2026-06-16 | 61 | 67 | yes |
| 2026-06-17 | 62 | 68 | yes |
| 2026-06-18 | 63 | 69 | yes |
| 2026-06-19 | 64 | 70 | yes |
| 2026-06-20 | - | 71 | - |
| 2026-06-21 | - | 72 | - |
| 2026-06-22 | 65 | 73 | yes |
| 2026-06-23 | 66 | 74 | yes |
| 2026-06-24 | - | 75 | - |
| 2026-06-25 | - | 76 | yes |
| 2026-06-26 | - | 77 | yes |
| 2026-06-28 | 67 | 78 | yes |
| 2026-06-29 | - | - | yes |
| 2026-06-30 | - | 79 | yes |
| 2026-07-01 | - | - | yes |
| 2026-07-02 | - | 80 | yes |
| 2026-07-03 | - | - | yes |
| 2026-07-04 | - | - | yes |
| 2026-07-05 | - | - | yes |
| 2026-07-06 | - | - | yes |
| 2026-07-07 | - | 81 | yes |
| 2026-07-08 | - | - | yes |
| 2026-07-09 | - | 82 | yes |
| 2026-07-10 | - | 83 | yes |
| 2026-07-11 | - | - | yes |
| 2026-07-12 | - | - | yes |
| 2026-07-13 | - | 84 | yes |
| 2026-07-14 | - | 85 | yes |
| 2026-07-15 | - | - | yes |
| 2026-07-16 | 68 | 86 | yes |
| 2026-07-17 | 69 | 87 | yes |
| 2026-07-18 | 70 | 88 | yes |
| 2026-07-19 | - | - | yes |
| 2026-07-20 | - | - | yes |
| 2026-07-21 | 71 | 89 | yes |
