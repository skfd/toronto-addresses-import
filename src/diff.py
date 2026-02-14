"""Diff two snapshots to find added, removed, and modified addresses."""

import sqlite3
import os

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

    conn.close()

    # Build structured modifications
    modified = []
    for row in modified_rows:
        changes = []
        for col in COMPARE_COLUMNS:
            old_val = row[f"old_{col}"]
            new_val = row[f"new_{col}"]
            if col in ("latitude", "longitude"):
                # Ignore coordinate changes if either value is out of WGS84 bounds (indicating different projection)
                # EPSG:4326 lat is [-90, 90], lon is [-180, 180]. 
                # We use 180 as a safe upper bound for both.
                if _is_projected(old_val) or _is_projected(new_val):
                    continue
            
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
                "changes": changes,
            })

    return {
        "old_snapshot_id": old_snapshot_id,
        "new_snapshot_id": new_snapshot_id,
        "added": [dict(r) for r in added],
        "removed": [dict(r) for r in removed],
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
