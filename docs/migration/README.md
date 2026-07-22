# Migration artifacts

Frozen evidence captured while retiring this project in favour of
[`ontario-address-changes`](https://github.com/skfd/ontario-address-changes). See
[MIGRATION_PLAN.md](MIGRATION_PLAN.md) for the full plan.

All of these were captured **read-only** against `addresses.db` at snapshot 71 (2026-07-21), the
final state of this tracker, while it was still the live source for `toronto-2-address-import`.
They exist so the migration can be verified against known-good numbers rather than trust.

| file | what it is |
|---|---|
| `MIGRATION_PLAN.md` | The plan: field analysis, phases, risk register |
| `baseline-candidates-snap71.csv` | Every t2 candidate for the configured downtown bbox — **12,424 rows**, after 49 Land Entrance rows were skipped at ingest. Phase 4 acceptance test: repointed t2 must reproduce this exactly. |
| `expected-catchup-56-71.csv` | The **57** additions in the pending catchup window 2026-06-05 → 2026-07-21 (Land 37, Structure 10, Land Entrance 10). Phase 5 acceptance test. |
| `expected-catchup-56-71-retired.csv` | The **7** retirements in the same window. |
| `snapshot-id-map.md` | Snapshot ID → date across all three stores. IDs are per-database and not portable; the t2 watermark must be translated by date. |

## Why the catchup baseline matters

10 of the 57 additions are `Land Entrance` rows — driveway/gate points that t2 drops at ingest
(`t2/candidates.py:50`, out of scope per `IMPORT_PROPOSAL.mediawiki`). That classification lives in
`ADDRESS_CLASS_DESC`, which `ontario-address-changes` stripped at ingest before the `keep_fields`
change. Without it those 10 would have flowed silently into the upload queue — no error raised.
This window is a concrete instance of the regression the migration exists to prevent.
