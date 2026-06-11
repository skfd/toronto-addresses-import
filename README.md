# Toronto Address Change Tracker

Tracks daily changes to the City of Toronto's [Address Points](https://open.toronto.ca/dataset/address-points-municipal-toronto-one-address-repository/) dataset — over 525,000 addresses across the city.

Every day, the City publishes a fresh snapshot of all address points. This tool downloads each snapshot, stores it, and produces a diff report showing which addresses were added, removed, or modified since the last run.

## Why?

The City of Toronto doesn't publish historical versions of this dataset — each daily update replaces the previous one. Without tracking changes over time, there's no way to know when an address appeared, disappeared, or was corrected.

This project fills that gap.

## Reports

Browse the latest change report on the [project page](https://skfd.github.io/toronto-addresses-import/).

## Architecture

This tool uses a **Slowly Changing Dimension (SCD) Type 2** approach to store address history efficiently.
Instead of storing full snapshots for every day, we track the validity period (`min_snapshot_id` to `max_snapshot_id`) for each address record.
This allows us to:
- Store only the changes (deltas), saving significant space.
- Query the state of the database at any point in history.
- Generate accurate diff reports even for periods with no changes.

## Usage

### 1. Download
Fetch the latest address points from Toronto Open Data:
```bash
python run.py download
```

### 2. Import & Diff
Import a specific GeoJSON file. This will automatically detect changes against the previous snapshot:
```bash
python run.py import --file data/address-points-YYYY-MM-DD.geojson
```

Without `--file`, it picks the alphabetically last `.geojson` in `data/`, which may not be the most recent date if non-date-named files (e.g. `test-*.geojson`) are present. Always pass the file explicitly to be safe.

### 3. Rebuild History
If you need to re-process all data (e.g., after a schema change or to backfill history), use the `rebuild` command.
**Warning:** This deletes the existing database and re-imports all files in `data/` sequentially.
```bash
python run.py rebuild
```

### 4. Generate Reports
Generate HTML reports for all historical snapshots and update the index:
```bash
python run.py report-all
```

### 5. Daily Update (all-in-one)
Download, import, diff, and generate a report in a single command:
```bash
python run.py update
```

## Scheduling (Windows)

Two PowerShell scripts manage the Windows Task Scheduler entry. Run them as Administrator.

**Add** — registers a daily task that runs `update` at noon and appends output to `logs\scheduler.log`:
```powershell
.\schedule-add.ps1
```

**Remove** — unregisters the task:
```powershell
.\schedule-remove.ps1
```

The task is named `kk-toronto-import` and can also be managed via the Task Scheduler GUI (`taskschd.msc`).

> If the task fails with a "python not found" error, replace `python` in `schedule-add.ps1` with the full path (e.g. `C:\Python312\python.exe`). Run `where python` in a terminal to find it.
