# Migration & Archive Plan

## Context

`toronto-addresses-import` is being retired. Its change-tracking role has moved to
[`ontario-address-changes`](https://github.com/skfd/ontario-address-changes) (Toronto is one of 42
datasets there), and its data-acquisition role to `address-vault`. The only remaining active
consumer is `toronto-2-address-import` (t2), which reads this project's `addresses.db` directly to
build OSM import candidates.

The goal is to retire this repo without regressing the OSM import. That is not a config change:
`ontario-address-changes` strips `ignore_fields` from `props` **at ingest**
(`src/normalize.py:130-132`), so fields t2 depends on were never stored in `toronto.db`. They must
be preserved first, the history rebuilt, and only then can t2 be repointed.

Archiving is last — GitHub archives are read-only, so every doc and redirect change must land
before the switch is flipped.

---

## Field analysis (why this is more than a repoint)

Three tiers of `ignore_fields` in `datasets/toronto.toml`:

**Tier 1 — `ADDRESS_CLASS_DESC`. Essential, unrecoverable.** Toronto models one civic address at
several geometry levels: Land 478,962 / Structure 33,182 / Structure Entrance 12,624 / Land
Entrance 705. t2 uses the class for the Land Entrance ingest skip (`t2/candidates.py:50`),
Land-canonical dedup (`t2/conflate.py:405`), intra-source duplicate grouping
(`t2/conflate.py:426`, Land rows only), and review filters. Without it every `== 'Land'` test is
False, `_build_land_groups` returns empty, and all three safety rules **fail silently open**:
~705 gate points + ~457 duplicates would flow to upload with no error raised. No substitute exists —
`GENERAL_USE`/`ADDRESS_STATUS` are `'Unknown'`/`'None'` for all 525,473 rows.

**Tier 2 — `LO_NUM`/`HI_NUM`(+`_SUF`). Essential, recoverable.** Drive the range safety gate
(`conflate.py:382`, ranges are never uploaded), range coverage (`t2/ranges.py`), reverse-sweep
parity expansion (`reverse_sweep.py:101`), half-numbers (`source_multi.py:172`). Parseable from
`number` (`'2208-2210'`, `'5239A-5243A'`, `'61A'`, `'14 1/2'` all round-trip), but we keep them
rather than write a parser on a path where a bug silently un-skips ranges into the upload queue.

**Tier 3 — the rest.** `CENTRELINE_*`, `CLASS_FAMILY*`, `ADDRESS_ID*`, `LINEAR_NAME_ID`,
`ADDRESS_STRING_ID`: zero t2 references. `LINEAR_NAME`/`_TYPE`/`_DIR`: fallback only in
`_street_from_row` when `linear_name_full` is empty — effectively dead. Correctly dropped.

## Decisions taken

| Decision | Choice |
|---|---|
| Old Pages site | Freeze in place + banner on all 128 reports |
| t2 repoint | Rewrite call sites (no compat view) |
| `addresses.db` (2.9 GB) | Keep here indefinitely + sidecar explaining it |
| Catchup run | After the rebuild (mitigated by Phase 0 freeze) |
| 5 unrecoverable dates | Accept loss; rebuild to 96 dates |
| Migration artifacts | `docs/migration/` in this repo |

---

## Phase 0 — Freeze expectations (read-only, no mutations)

Because the catchup runs *after* the rebuild, there is no known-good number to check against unless
we capture one now from the proven DB.

1. Move the already-captured t2 candidate baseline into `docs/migration/`
   (12,424 candidates / 49 Land-Entrance skips, snapshot 71, config bbox).
2. Capture the **57 expected additions** for window 56→71 (2026-06-05 → 2026-07-21) as
   `expected-catchup-56-71.csv`, keyed by `address_point_id`, from `addresses.db`.
3. Capture snapshot `id → date` mappings for all three stores as `snapshot-id-map.md`.

**Verify:** all three files exist and are committed before anything else changes.

## Phase 1 — Stop the scheduler, commit pending

`kk-toronto-import` still runs `update` daily at noon. An archived repo rejects pushes, so this
fails nightly if left armed.

1. `.\schedule-remove.ps1` (Administrator).
2. Commit the pending `docs/reports/report-2026-07-21.*`, `docs/index.html`, `metadata.json`.

**Verify:** `Get-ScheduledTask kk-toronto-import` returns not-found; `kk-ontario-update` still
`Ready`; working tree clean.

## Phase 2 — `keep_fields` in `ontario-address-changes`

One list, three behaviours: **store in `props`, still ignore for diffs, exclude from
`payload_hash`.** The third is not optional — `_payload_hash` (`src/normalize.py:151-158`) hashes
`props`, so a kept-but-noisy field reopens SCD-2 ranges on every churn, undoing commit `363e435`.
`HI_NUM` is known-noisy (the 2026-06 `0→NULL` recode touched 522k rows).

- `src/registry.py` — parse `keep_fields` onto `Dataset` (default `[]`).
- `src/normalize.py:130` — subtract `keep_fields` from the props strip set; hash `props` minus
  `keep_fields` in `_payload_hash`.
- `datasets/toronto.toml` —
  `keep_fields = ["ADDRESS_CLASS_DESC", "LO_NUM", "LO_NUM_SUF", "HI_NUM", "HI_NUM_SUF"]`

**Verify:** unit test that a kept field appears in `props`, is absent from the diff, and does not
change `payload_hash`. Confirm a dataset with no `keep_fields` produces byte-identical
`payload_hash` to before (the other 41 must not re-ingest).

## Phase 3 — Rebuild Toronto history

Rebuild source is the vault's 94 dates plus the 2 GeoJSON still on disk = **96**. Today's
`toronto.db` has 89. Net +12, −5: `2026-06-13/14/15/20/21` are lost, as their raw GeoJSON exists
nowhere. Acceptable — the old `addresses.db` never had those dates either, so t2 sees no regression.

1. Seed the vault with `data/toronto/toronto-2026-06-10.geojson` and `…06-24.geojson`.
2. Rebuild Toronto from the vault.

**Verify:** 96 snapshots; `ADDRESS_CLASS_DESC` present with the 4-class distribution above;
`LO_NUM`/`HI_NUM` present; a known range (`2208-2210 Kingston Rd`) and a half-number
(`14 1/2 Kenwood Ave`) both round-trip; additions since 2026-06-05 == **57**.

## Phase 4 — Repoint t2

Largest phase. ~238 references across 14 files.

- `config.toml:2` → `…/ontario-address-changes/data/toronto/toronto.db`
- `t2/source_db.py` — `_ADDRESS_COLS` maps to the new schema; kept fields via `json_extract(props, …)`

| old | new |
|---|---|
| `address_point_id` | `identity_key` |
| `address_full` / `address_number` | `full` / `number` |
| `linear_name_full` | `street` |
| `municipality_name`, `ward_name`, `place_name` | `json_extract(props,'$.…')` |
| `lo_num`/`hi_num`(+`_suf`) | `json_extract(props,'$.LO_NUM')` etc. |
| `extra` → `ADDRESS_CLASS_DESC` | `json_extract(props,'$.ADDRESS_CLASS_DESC')` |

Heaviest files: `t2/ranges.py`, `candidates.py`, `conflate.py`, `streets.py`, `osm_export.py`,
`reverse_sweep.py`, `source_multi.py`, `web/app.py`.

**Watermark, separately:** it is a bare integer (`kv['maintenance.watermark_snapshot'] = '56'`) and
IDs are per-database — `56` means 2026-06-05 here but 2026-06-02 in `toronto.db`. Translate **by
date**, and store `maintenance.watermark_date` alongside so this cannot recur. Reuse
`scripts/publish_db.py:34 _watermark_date()`.

**Verify:** re-run the Phase 0 baseline capture against the new DB — must reproduce **12,424
candidates / 49 skips exactly**. Full test suite green.

## Phase 5 — Catchup run

1. Recompute the delta; compare against the frozen `expected-catchup-56-71.csv` (57 additions).
   Investigate any difference before proceeding.
2. Run `maint-catchup-snap<from>-<to>` with date-translated bounds.
3. Advance the watermark on operator confirmation; write `maintenance.watermark_date` too.

**Verify:** delta matches the frozen expectation; watermark advanced to 2026-07-21's new ID.

## Phase 6 — Freeze this repo

1. Banner into `docs/index.html` + all 128 `docs/reports/report-*.html`, linking to
   `https://skfd.github.io/ontario-address-changes/toronto/`. State that the successor applies
   `ignore_fields`, so its diffs intentionally differ — these are **not** 1:1 replacements.
2. README header pointing at the successor.
3. Sidecar next to `addresses.db` explaining what it is, why it's retained, and that it is
   superseded by `toronto.db`.
4. External inbound links: OSM wiki `Toronto/Import/AddressPoints`, the
   [forum thread](https://community.openstreetmap.org/t/address-import-for-toronto/119368), and
   t2's README (which still describes reading "the sibling `toronto-addresses-import` project's
   SQLite DB" — false after Phase 4).
5. Check nothing consumes `docs/reports/*.json` before declaring them inert.

**Verify:** site renders with banner; no reference anywhere claims this repo is live.

## Phase 7 — Archive

GitHub → Settings → Archive. Pages keeps serving. Do this **last**; pushes stop working after.

---

## Risk register

| Risk | Mitigation |
|---|---|
| `address_class` loss fails silently open | Phase 2 restores it; Phase 4 baseline diff must match 12,424/49 exactly |
| `keep_fields` reintroduces SCD-2 bloat | Exclude kept fields from `payload_hash`; assert store size after rebuild |
| Watermark integer drift (57 vs 59 additions) | Translate by date; persist `watermark_date` |
| Other 41 datasets forced to re-ingest | Assert `payload_hash` unchanged when `keep_fields` absent |
| Catchup runs against unproven DB | Phase 0 frozen expectation of 57 additions |
| Archive before docs land | Phase 7 strictly last |
