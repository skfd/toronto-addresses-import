import json
import os
import sqlite3
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.db import DB_PATH, TRACKED_COLUMNS
from src.diff import compute_diff, COMPARE_COLUMNS


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_latest_snapshots(n=2):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM snapshots ORDER BY downloaded DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def _parse_float(val):
    if val is None or val == "" or val == "None":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def _clean_str(val):
    if val is None or val == "None" or val == "":
        return None
    return str(val)

def _parse_int(val):
    if val is None or val == "" or val == "None":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None

def load_raw_snapshot(filename):
    """Load and normalize a GeoJSON snapshot."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    filepath = os.path.join(data_dir, filename)
    
    print(f"  Loading {filename}...")
    
    records = {}
    
    with open(filepath, "r", encoding="utf-8") as f:
        # We need to handle the line-based parsing similar to import_geojson
        # or just load the whole thing if it's standard GeoJSON.
        # The import script handles line-based to support large files/streaming,
        # but let's try to be robust. 
        # Actually, let's stick to the line-based approach for consistency/memory.
        
        for line in f:
            line = line.strip().rstrip(",")
            if '"type": "Feature"' not in line:
                continue
            
            # Simple hack to make it valid JSON if it's in a list
            if line.endswith("]"): line = line[:-1]
            if line.endswith("}") and line.count("{") < line.count("}"): line = line[:-1] # overly simple?
            # actually import_geojson regex is: re.sub(r",\s*]", "]", line)
            
            try:
                # We might need to handle the trailing comma if simple json.loads fails
                # But let's assume one feature per line mostly works
                feat = json.loads(line)
            except json.JSONDecodeError:
                # Try scrubbing trailing comma
                if line.endswith(","):
                    try:
                        feat = json.loads(line[:-1])
                    except:
                        continue
                else:
                    continue

            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [])
            
            if coords and isinstance(coords[0], list):
                 coords = coords[0] # MultiPoint?
            
            lon_raw = _parse_float(coords[0]) if len(coords) > 0 else None
            lat_raw = _parse_float(coords[1]) if len(coords) > 1 else None
            
            # Rounding to 5 decimal places as per db.py
            lon = round(lon_raw, 5) if lon_raw is not None else None
            lat = round(lat_raw, 5) if lat_raw is not None else None

            # Build record dict using TRACKED_COLUMNS + GEO
            rec = {
                "latitude": lat,
                "longitude": lon
            }
            
            # Helper to map property keys (which might be upper case) to our lower case columns
            # In db.py: _clean_str(props.get("ADDRESS_FULL"))
            # We need to match the COMPARE_COLUMNS keys.
            
            # db.py mapping:
            # ADDRESS_POINT_ID -> address_point_id
            # ADDRESS_FULL -> address_full
            # etc.
            
            aid = _parse_int(props.get("ADDRESS_POINT_ID"))
            if aid is None:
                continue
            
            rec["address_point_id"] = aid
            
            # Map other columns
            # COMPARE_COLUMNS identifiers are lowercase. 
            # We assume props has uppercase versions.
            for col in COMPARE_COLUMNS:
                if col in ["latitude", "longitude"]: continue
                
                # Try direct match or uppercase
                val = props.get(col) or props.get(col.upper())
                
                # Type specific parsing based on known types?
                # In db.py:
                # LO_NUM, HI_NUM -> int
                # Others -> str
                
                if col in ["lo_num", "hi_num"]:
                    rec[col] = _parse_int(val)
                elif col == "address_number":
                     # address_number is text in DB schema
                    rec[col] = _clean_str(val)
                else:
                    rec[col] = _clean_str(val)

            records[aid] = rec

    return records


def verify_diff(old_snap_id, new_snap_id):
    conn = _connect()
    
    old_snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (old_snap_id,)).fetchone()
    new_snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (new_snap_id,)).fetchone()
    conn.close()
    
    if not old_snap or not new_snap:
        print("Snapshots not found.")
        return

    print(f"Verifying Diff: {old_snap['filename']} ({old_snap['id']}) -> {new_snap['filename']} ({new_snap['id']})")

    # 1. Load Raw Data
    print("  Loading raw data (this may take a moment)...")
    raw_old = load_raw_snapshot(old_snap["filename"])
    raw_new = load_raw_snapshot(new_snap["filename"])
    
    print(f"  Raw Counts: Old={len(raw_old)}, New={len(raw_new)}")

    # 2. Compute Raw Diff
    print("  Computing raw diff...")
    raw_added = set(raw_new.keys()) - set(raw_old.keys())
    raw_removed = set(raw_old.keys()) - set(raw_new.keys())
    
    raw_modified = []
    common_ids = set(raw_new.keys()) & set(raw_old.keys())
    
    for aid in common_ids:
        r_old = raw_old[aid]
        r_new = raw_new[aid]
        
        # Check for changes
        # Re-use logic from valid changes (e.g. ignore tiny float diffs? we rounded already)
        # We need to handle the "0 vs None" equivalence logic from diff.py
        
        is_mod = False
        changes = []
        for col in COMPARE_COLUMNS:
            v_old = r_old.get(col)
            v_new = r_new.get(col)
            
            # diff.py specific logic:
            # 1. Coordinate projection check
            if col in ("latitude", "longitude"):
                # _is_projected check
                if (v_old is not None and abs(v_old) > 180) or \
                   (v_new is not None and abs(v_new) > 180):
                    continue
            
            # 2. _values_differ logic
            # Treat 0 and None as equivalent
            if (v_old == 0 and v_new is None) or (v_old is None and v_new == 0):
                pass # Equal
            elif v_old != v_new:
                # String comparison for everything else
                if str(v_old) != str(v_new):
                    is_mod = True
                    changes.append(col)
        
        if is_mod:
            raw_modified.append(aid)

    # 3. Get DB Diff
    print("  Fetching DB diff...")
    db_diff = compute_diff(old_snap_id, new_snap_id)
    
    db_added = {r["address_point_id"] for r in db_diff["added"]}
    db_removed = {r["address_point_id"] for r in db_diff["removed"]}
    db_modified = {r["address_point_id"] for r in db_diff["modified"]}

    # 4. Compare
    print("\n=== RESULTS ===")
    
    # ADDED
    if raw_added == db_added:
        print(f"[OK] Added: {len(db_added)}")
    else:
        print(f"[FAIL] Added mismatch! Raw={len(raw_added)}, DB={len(db_added)}")
        print(f"  In Raw only: {list(raw_added - db_added)[:10]}...")
        print(f"  In DB only:  {list(db_added - raw_added)[:10]}...")

    # REMOVED
    if raw_removed == db_removed:
        print(f"[OK] Removed: {len(db_removed)}")
    else:
        print(f"[FAIL] Removed mismatch! Raw={len(raw_removed)}, DB={len(db_removed)}")
        print(f"  In Raw only: {list(raw_removed - db_removed)[:10]}...")
        print(f"  In DB only:  {list(db_removed - raw_removed)[:10]}...")

    # MODIFIED
    raw_mod_set = set(raw_modified)
    if raw_mod_set == db_modified:
        print(f"[OK] Modified: {len(db_modified)}")
    else:
        print(f"[FAIL] Modified mismatch! Raw={len(raw_mod_set)}, DB={len(db_modified)}")
        print(f"  In Raw only: {list(raw_mod_set - db_modified)[:10]}...")
        print(f"  In DB only:  {list(db_modified - raw_mod_set)[:10]}...")


if __name__ == "__main__":
    snaps = get_latest_snapshots(2)
    if len(snaps) < 2:
        print("Not enough snapshots to verify.")
    else:
        verify_diff(snaps[0]["id"], snaps[1]["id"])
