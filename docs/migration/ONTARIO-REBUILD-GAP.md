# Open gap: the correct live `toronto.db` is not reproducible from committed code

**Status:** open as of 2026-07-22. Blocks a clean archive of this project because
`toronto-2-address-import` (t2) now depends on a database that no committed code path
can regenerate.

## Summary

A parallel agent session completed Phases 3–4 of [MIGRATION_PLAN.md](MIGRATION_PLAN.md):

- **Rebuilt** the live `ontario-address-changes/data/toronto/toronto.db` (90 snapshots,
  2026-07-22 21:45) with `ADDRESS_CLASS_DESC` and `LO_NUM`/`HI_NUM` in `props`, all **fresh**.
- **Repointed** t2 to read that DB via `json_extract` on `props` (8 files, uncommitted on
  `main`: `config.toml`, `t2/source_db.py`, `ranges.py`, `reverse_sweep.py`, `source_multi.py`,
  `maintenance.py`, `scripts/source_multi_audit.py`, `tests/test_retirement_reissue.py`).

Both acceptance gates pass against this setup:

- t2 reproduces the frozen baseline exactly: **12,424 candidates / 49 Land Entrance skips**
  (see `baseline-candidates-snap71.csv`).
- t2 test suite: **70 passed**.

The work is functionally correct **right now**. The problem is durability: the ontario-side
recipe that produced the fresh DB exists nowhere in the ontario repo.

## The gap

| | committed ontario code (`feat/keep-fields`, `5c0fcd6`) | recipe that built the live DB |
|---|---|---|
| `HI_NUM = 0` (singles) | stored verbatim → **97% stale** | stripped to absent → **fresh** |
| `ADDRESS_CLASS_DESC` | in `props`, excluded from hash | in `props`, stays fresh |
| in `payload_hash`? | excluded (`_payload_hash(rec, hash_props)`) | **not** hashed (no bulk recode event) |
| rebuild result | 0.73% class / 97% `HI_NUM` stale | **0.01% class / 0% `HI_NUM`** |

Proof the recipe is absent: ontario is on `feat/keep-fields` at `5c0fcd6`; no newer commits on
any branch; no worktrees; `git status` shows only untracked `docs/` reports — zero `src/` or
`datasets/` changes. Yet the live DB behaves in a way the committed code cannot produce. The
recipe was a one-off script in the other agent's session (same pattern as
`docs/migration/rebuild_toronto.py`) and left no trace in the repo.

## Mechanism (evidence)

Not hashing. There is **no** 522k-row modify event at the 2026-06 `HI_NUM 0→NULL` recode (largest
non-baseline span-opening is 4,352), so the kept fields are not in the hash. Instead:

- The vault's `2025-04-01` baseline source encodes `HI_NUM = 0` for singles (7,989/8,000 sampled).
- In the live DB, the 516,159 rows unchanged since that baseline store `HI_NUM` **absent**
  (514,585) while `ADDRESS_CLASS_DESC` is **present** for all 516,159.

So the build normalizes `HI_NUM = 0 → absent` (correctly reading "0" as "not a range") and keeps
`ADDRESS_CLASS_DESC`. This sidesteps the 0-vs-null staleness that broke the alternative
`keep_fields`-excluded-from-hash approach, and it makes t2's range gate
(`_is_range`: `hi is not None`) see singles correctly. This project's committed Phase 2 code
stores `HI_NUM = 0` verbatim — which is exactly why a rebuild from it is 97% stale.

## Regression risk

t2 depends on the live `toronto.db`, but nothing committed regenerates it. Two triggers regress it
silently:

1. **A daily `kk-ontario-update` run** on the committed code appends a snapshot storing
   `HI_NUM = 0` for any single that changes — reintroducing the problem incrementally.
   (`kk-ontario-update` remained armed; runs daily at noon.)
2. **Any full rebuild** from committed code reproduces the stale result.

Either way, t2 then reads `HI_NUM = 0` on singles → `_is_range` returns true → **real addresses are
classified as ranges and dropped from the OSM upload, with no error raised.**

## To close it

Commit, to a real branch on `ontario-address-changes`, the normalize logic the one-off script
applied:

- **Strip `HI_NUM = 0` (and zero-equivalent `LO_NUM`/suffixes) to absent** in
  `src/normalize.py` prop cleaning, so "0" never persists as a false range bound.
- **Retain `ADDRESS_CLASS_DESC` in `props`** (it stays fresh because it changes rarely and isn't
  zero-encoded).
- **Abandon** the `keep_fields`-excluded-from-hash mechanism on `feat/keep-fields` (`5c0fcd6`) —
  it is the stale approach and is superseded.
- Tests: `2208-2210` range round-trip, `14 1/2` half-number round-trip, and the
  `HI_NUM = 0 → absent` case.

Until this lands, do not run `kk-ontario-update` or any rebuild against the live `toronto.db`, and
do not archive this project — t2's data source is not yet reproducible.

## Notes

- The other agent's 8-file t2 change is uncommitted on `main` (not a branch) and should be moved
  to a branch and committed once the ontario side is locked.
- A stale artifact from this project's own earlier rebuild attempt sits at
  `ontario-address-changes/data/toronto-rebuild/` (gitignored). It is 0.73%/97% stale — **not** the
  good DB — and should be deleted to avoid confusion.
