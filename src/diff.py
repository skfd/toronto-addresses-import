"""Diff two snapshots to find added, removed, and modified addresses."""

import re
import sqlite3
import os
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "addresses.db")

# Columns compared for modifications (exclude address_point_id which is the key)
COMPARE_COLUMNS = [
    "address_full",
    "address_number",
    "lo_num",
    "lo_num_suf",
    "hi_num",
    "hi_num_suf",
    "linear_name_full",
    "linear_name",
    "linear_name_type",
    "linear_name_dir",
    "municipality_name",
    "ward_name",
    "longitude",
    "latitude",
]


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def compute_diff(old_snapshot_id, new_snapshot_id):
    """Compare two snapshots using validity ranges. Returns a dict with added, removed, modified lists."""
    conn = _connect()

    # Added: Valid in new, but NO record valid in old for this address_point_id
    added = conn.execute("""
        SELECT n.* FROM addresses n
        WHERE n.min_snapshot_id <= ? AND n.max_snapshot_id >= ?
        AND NOT EXISTS (
            SELECT 1 FROM addresses o
            WHERE o.address_point_id = n.address_point_id
            AND o.min_snapshot_id <= ? AND o.max_snapshot_id >= ?
        )
    """, (new_snapshot_id, new_snapshot_id, old_snapshot_id, old_snapshot_id)).fetchall()

    # Removed: Valid in old, but NO record valid in new for this address_point_id
    removed = conn.execute("""
        SELECT o.* FROM addresses o
        WHERE o.min_snapshot_id <= ? AND o.max_snapshot_id >= ?
        AND NOT EXISTS (
            SELECT 1 FROM addresses n
            WHERE n.address_point_id = o.address_point_id
            AND n.min_snapshot_id <= ? AND n.max_snapshot_id >= ?
        )
    """, (old_snapshot_id, old_snapshot_id, new_snapshot_id, new_snapshot_id)).fetchall()

    # Modified: Address exists in both, but represented by DIFFERENT rows (meaning change occurred)
    modified_rows = conn.execute(f"""
        SELECT o.address_point_id,
               {', '.join(f'o.{c} AS old_{c}' for c in COMPARE_COLUMNS)},
               {', '.join(f'n.{c} AS new_{c}' for c in COMPARE_COLUMNS)}
        FROM addresses o
        JOIN addresses n ON n.address_point_id = o.address_point_id
        WHERE o.min_snapshot_id <= ? AND o.max_snapshot_id >= ?
          AND n.min_snapshot_id <= ? AND n.max_snapshot_id >= ?
          AND o.min_snapshot_id != n.min_snapshot_id
    """, (old_snapshot_id, old_snapshot_id, new_snapshot_id, new_snapshot_id)).fetchall()

    # Attach history events to each added/removed row
    added_rows = [dict(r) for r in added]
    removed_rows = [dict(r) for r in removed]

    histories = compute_histories(
        conn,
        {r["address_point_id"] for r in added_rows}
        | {r["address_point_id"] for r in removed_rows},
    )
    for r in added_rows:
        r["history"] = _mark_current(
            histories.get(r["address_point_id"], []),
            new_snapshot_id,
            "added",
        )
    for r in removed_rows:
        r["history"] = _mark_current(
            histories.get(r["address_point_id"], []),
            new_snapshot_id,
            "removed",
        )

    conn.close()

    # Build structured modifications
    modified = []
    for row in modified_rows:
        # Skip entries with incomparable projected coordinates
        old_lat, old_lon = row["old_latitude"], row["old_longitude"]
        new_lat, new_lon = row["new_latitude"], row["new_longitude"]
        if (_is_projected(old_lat) or _is_projected(old_lon)
                or _is_projected(new_lat) or _is_projected(new_lon)):
            continue

        changes = []
        for col in COMPARE_COLUMNS:
            old_val = row[f"old_{col}"]
            new_val = row[f"new_{col}"]
            if _values_differ(old_val, new_val):
                changes.append({
                    "field": col,
                    "old": old_val,
                    "new": new_val,
                })
        if changes:
            modified.append({
                "address_point_id": row["address_point_id"],
                "address_full": row["new_address_full"] or row["old_address_full"] or "",
                "municipality_name": row["new_municipality_name"] or row["old_municipality_name"] or "",
                "latitude": row["new_latitude"],
                "longitude": row["new_longitude"],
                "changes": changes,
            })

    return {
        "old_snapshot_id": old_snapshot_id,
        "new_snapshot_id": new_snapshot_id,
        "added": added_rows,
        "removed": removed_rows,
        "modified": modified,
    }


def _values_differ(a, b):
    """Compare two values, treating None/empty as equal."""
    if a is None and b is None:
        return False
        
    # Treat 0 and None as equivalent for integer fields (common in data variations)
    # Must check this BEFORE generic None check below
    if (a == 0 and b is None) or (a is None and b == 0):
        return False

    if a is None or b is None:
        return True
    
    return str(a) != str(b)


def _is_projected(val):
    """Check if a coordinate value looks like a projected value (outside WGS84 bounds)."""
    if isinstance(val, (int, float)):
        return abs(val) > 180
    return False


def get_snapshot_timeline(conn):
    """Return (ordered_snapshot_ids, snapshot_id -> YYYY-MM-DD) for non-skipped snapshots."""
    rows = conn.execute(
        "SELECT id, filename, downloaded FROM snapshots WHERE skipped = 0 ORDER BY id"
    ).fetchall()
    ids = [r["id"] for r in rows]
    dates = {}
    for r in rows:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", r["filename"] or "")
        dates[r["id"]] = m.group(1) if m else (r["downloaded"] or "")[:10]
    return ids, dates


def compute_histories(conn, point_ids):
    """For each address_point_id, return the list of added/removed events
    across the snapshot timeline.

    Event: {"date": "YYYY-MM-DD", "kind": "added"|"removed", "snapshot_id": int}
    """
    if not point_ids:
        return {}

    ids, dates = get_snapshot_timeline(conn)

    ranges_by_pid = defaultdict(list)
    pids_list = list(point_ids)
    BATCH = 400
    for i in range(0, len(pids_list), BATCH):
        batch = pids_list[i:i + BATCH]
        placeholders = ",".join(["?"] * len(batch))
        query = f"""
            SELECT address_point_id, min_snapshot_id, max_snapshot_id
            FROM addresses
            WHERE address_point_id IN ({placeholders})
        """
        for row in conn.execute(query, batch):
            ranges_by_pid[row["address_point_id"]].append(
                (row["min_snapshot_id"], row["max_snapshot_id"])
            )

    histories = {}
    for pid in point_ids:
        ranges = ranges_by_pid.get(pid, [])
        events = []
        prev = False
        for sid in ids:
            present = any(mn <= sid <= mx for mn, mx in ranges)
            if present and not prev:
                events.append({"date": dates[sid], "kind": "added", "snapshot_id": sid})
            elif not present and prev:
                events.append({"date": dates[sid], "kind": "removed", "snapshot_id": sid})
            prev = present
        histories[pid] = events
    return histories


def _mark_current(events, current_snapshot_id, current_kind):
    """Return a copy of events with current=True on the event that matches this report.

    Histories are keyed by address_point_id, so the current row's event is always
    present in the computed timeline.

    For 'added' rows whose only event is the current one, return [] so the
    template renders "First appearance" instead of a lone underlined date.
    """
    out = [dict(e) for e in events]
    for ev in out:
        ev["current"] = (
            ev["snapshot_id"] == current_snapshot_id and ev["kind"] == current_kind
        )
    if (
        current_kind == "added"
        and len(out) == 1
        and out[0]["current"]
    ):
        return []
    return out
