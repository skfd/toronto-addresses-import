"""SQLite database: schema, import, and query helpers."""

import json
import os
import re
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "addresses.db")

# Columns stored as real DB columns (tracked for changes)
TRACKED_COLUMNS = [
    "ADDRESS_POINT_ID",
    "ADDRESS_FULL",
    "ADDRESS_NUMBER",
    "LO_NUM",
    "LO_NUM_SUF",
    "HI_NUM",
    "HI_NUM_SUF",
    "LINEAR_NAME_FULL",
    "LINEAR_NAME",
    "LINEAR_NAME_TYPE",
    "LINEAR_NAME_DIR",
    "MUNICIPALITY_NAME",
    "WARD_NAME",
]
# Extracted from geometry coordinates
GEO_COLUMNS = ["LONGITUDE", "LATITUDE"]

ALL_DB_COLUMNS = TRACKED_COLUMNS + GEO_COLUMNS

# Map property name -> db column (lowercase)
_DB_COL_MAP = {c: c.lower() for c in ALL_DB_COLUMNS}


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            downloaded  TEXT NOT NULL,
            row_count   INTEGER NOT NULL,
            filename    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS addresses (
            min_snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id),
            max_snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id),
            address_point_id    INTEGER NOT NULL,
            address_full        TEXT,
            address_number      TEXT,
            lo_num              INTEGER,
            lo_num_suf          TEXT,
            hi_num              INTEGER,
            hi_num_suf          TEXT,
            linear_name_full    TEXT,
            linear_name         TEXT,
            linear_name_type    TEXT,
            linear_name_dir     TEXT,
            municipality_name   TEXT,
            ward_name           TEXT,
            longitude           REAL,
            latitude            REAL,
            extra               TEXT,
            PRIMARY KEY (address_point_id, min_snapshot_id)
        );

        CREATE INDEX IF NOT EXISTS idx_addr_validity
            ON addresses(min_snapshot_id, max_snapshot_id);
            
        CREATE INDEX IF NOT EXISTS idx_addr_active
            ON addresses(max_snapshot_id);
    """)
    conn.commit()
    conn.close()


def _parse_int(val):
    if val is None or val == "" or val == "None":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


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


def import_geojson(filepath):
    """Import a GeoJSON file as a new snapshot using delta logic."""
    init_db()
    conn = _connect()

    filename = os.path.basename(filepath)

    # Check if already imported
    existing = conn.execute(
        "SELECT id FROM snapshots WHERE filename = ?", (filename,)
    ).fetchone()
    if existing:
        print(f"Already imported: {filename} (snapshot {existing['id']})")
        conn.close()
        return existing["id"]

    # Get previous snapshot ID
    prev = conn.execute("SELECT MAX(id) FROM snapshots").fetchone()[0]

    print(f"Importing {filename} (prev_snapshot={prev}) ...")

    # Insert snapshot record
    cur = conn.execute(
        "INSERT INTO snapshots (downloaded, row_count, filename) VALUES (?, 0, ?)",
        (datetime.now().isoformat(), filename),
    )
    curr_id = cur.lastrowid

    # Create temporary staging table
    conn.execute("DROP TABLE IF EXISTS staging_addresses")
    # Copy schema structure from addresses but without min/max/pk constraints
    conn.execute("""
        CREATE TEMPORARY TABLE staging_addresses (
            address_point_id    INTEGER,
            address_full        TEXT,
            address_number      TEXT,
            lo_num              INTEGER,
            lo_num_suf          TEXT,
            hi_num              INTEGER,
            hi_num_suf          TEXT,
            linear_name_full    TEXT,
            linear_name         TEXT,
            linear_name_type    TEXT,
            linear_name_dir     TEXT,
            municipality_name   TEXT,
            ward_name           TEXT,
            longitude           REAL,
            latitude            REAL,
            extra               TEXT
        )
    """)

    # 1. Load data into staging
    row_count = 0
    batch = []
    batch_size = 5000

    col_names = [k.lower() for k in TRACKED_COLUMNS] + ["longitude", "latitude", "extra"]

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if '"type": "Feature"' not in line:
                continue
            line = re.sub(r",\s*]", "]", line)
            line = re.sub(r",\s*}", "}", line)
            try:
                feat = json.loads(line)
            except json.JSONDecodeError:
                continue

            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [])
            if coords and isinstance(coords[0], list):
                coords = coords[0]
            
            lon_raw = _parse_float(coords[0]) if len(coords) > 0 else None
            lat_raw = _parse_float(coords[1]) if len(coords) > 1 else None
            lon = round(lon_raw, 5) if lon_raw is not None else None
            lat = round(lat_raw, 5) if lat_raw is not None else None

            vals = [
                _parse_int(props.get("ADDRESS_POINT_ID")),
                _clean_str(props.get("ADDRESS_FULL")),
                _clean_str(props.get("ADDRESS_NUMBER")),
                _parse_int(props.get("LO_NUM")),
                _clean_str(props.get("LO_NUM_SUF")),
                _parse_int(props.get("HI_NUM")),
                _clean_str(props.get("HI_NUM_SUF")),
                _clean_str(props.get("LINEAR_NAME_FULL")),
                _clean_str(props.get("LINEAR_NAME")),
                _clean_str(props.get("LINEAR_NAME_TYPE")),
                _clean_str(props.get("LINEAR_NAME_DIR")),
                _clean_str(props.get("MUNICIPALITY_NAME")),
                _clean_str(props.get("WARD_NAME")),
                lon,
                lat
            ]

            # Extra
            extra_keys = set(props.keys()) - set(TRACKED_COLUMNS) - {"_id"}
            extra = {k: props[k] for k in sorted(extra_keys) if props.get(k) is not None}
            vals.append(json.dumps(extra) if extra else None)

            if vals[0] is None: continue # address_point_id is first

            batch.append(tuple(vals))
            row_count += 1

            if len(batch) >= batch_size:
                _insert_staging(conn, batch, col_names)
                batch = []
                if row_count % 50000 == 0:
                    print(f"  Buffered {row_count:,} rows ...")

    if batch:
        _insert_staging(conn, batch, col_names)

    conn.execute("CREATE INDEX idx_staging_id ON staging_addresses(address_point_id)")

    if prev is None:
        # First import ever: everything is new
        print("  First import: Bulk inserting all rows...")
        cols_str = ", ".join(col_names)
        conn.execute(f"""
            INSERT INTO addresses (min_snapshot_id, max_snapshot_id, {cols_str})
            SELECT ?, ?, {cols_str} FROM staging_addresses
        """, (curr_id, curr_id))
    else:
        # Delta logic
        print("  Detecting changes...")
        
        # Build comparison clause
        # tracked cols + geo cols + extra
        compare_cols = col_names[1:] # skip address_point_id
        
        conditions = []
        for c in compare_cols:
            conditions.append(f"(addresses.{c} IS s.{c})")
        match_condition = " AND ".join(conditions)

        # 2. Update existing unchanged records: extend max_snapshot_id
        # We find records active at 'prev' that match 'staging'
        conn.execute(f"""
            UPDATE addresses SET max_snapshot_id = ?
            WHERE max_snapshot_id = ?
            AND EXISTS (
                SELECT 1 FROM staging_addresses s
                WHERE s.address_point_id = addresses.address_point_id
                AND {match_condition}
            )
        """, (curr_id, prev))
        
        updated_count = conn.total_changes
        print(f"  Unchanged: {updated_count:,} (extended validity)")

        # 3. Insert New or Modified records
        # These are records in staging that DO NOT exist in addresses with max_snapshot_id = curr_id
        # (Because if they matched, we just updated them to curr_id)
        cols_str = ", ".join(col_names)
        conn.execute(f"""
            INSERT INTO addresses (min_snapshot_id, max_snapshot_id, {cols_str})
            SELECT ?, ?, {cols_str} FROM staging_addresses s
            WHERE s.address_point_id NOT IN (
                SELECT address_point_id FROM addresses
                WHERE max_snapshot_id = ?
            )
        """, (curr_id, curr_id, curr_id))
        
        inserted_count = conn.total_changes
        print(f"  New/Modified: {inserted_count:,}")

    # Update summary
    conn.execute(
        "UPDATE snapshots SET row_count = ? WHERE id = ?", (row_count, curr_id)
    )
    conn.execute("DROP TABLE staging_addresses")
    conn.commit()
    conn.close()
    
    print(f"Imported {row_count:,} rows as snapshot {curr_id}")
    return curr_id


def _insert_staging(conn, batch, cols):
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO staging_addresses ({', '.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, batch)


def get_snapshots():
    """Return all snapshots ordered by date."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM snapshots ORDER BY downloaded"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_snapshots(n=2):
    """Return the last n snapshots."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM snapshots ORDER BY downloaded DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_active_addresses():
    """Return all addresses valid in the most recent snapshot."""
    conn = _connect()
    
    # Get latest snapshot ID
    cur = conn.execute("SELECT MAX(id) FROM snapshots")
    latest_id = cur.fetchone()[0]
    
    if latest_id is None:
        conn.close()
        return []

    print(f"Fetching addresses for snapshot {latest_id}...")
    
    # Query for addresses where max_snapshot_id matches the latest snapshot
    # This implies they were present/verified in the most recent import
    rows = conn.execute(f"""
        SELECT * FROM addresses 
        WHERE max_snapshot_id = ?
    """, (latest_id,)).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]
