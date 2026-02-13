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
            snapshot_id         INTEGER NOT NULL REFERENCES snapshots(id),
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
            PRIMARY KEY (snapshot_id, address_point_id)
        );

        CREATE INDEX IF NOT EXISTS idx_addr_point
            ON addresses(address_point_id);
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
    """Import a GeoJSON file as a new snapshot. Returns the snapshot id.

    Streams the file line-by-line (each Feature is one line in the Toronto dataset).
    """
    init_db()
    conn = _connect()

    filename = os.path.basename(filepath)

    # Check if this file was already imported
    existing = conn.execute(
        "SELECT id FROM snapshots WHERE filename = ?", (filename,)
    ).fetchone()
    if existing:
        print(f"Already imported: {filename} (snapshot {existing['id']})")
        conn.close()
        return existing["id"]

    print(f"Importing {filename} ...")

    # Insert snapshot record
    cur = conn.execute(
        "INSERT INTO snapshots (downloaded, row_count, filename) VALUES (?, 0, ?)",
        (datetime.now().isoformat(), filename),
    )
    snapshot_id = cur.lastrowid

    row_count = 0
    batch = []
    batch_size = 5000

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if '"type": "Feature"' not in line:
                continue
            # Fix trailing commas (invalid JSON in some exports)
            line = re.sub(r",\s*]", "]", line)
            line = re.sub(r",\s*}", "}", line)
            try:
                feat = json.loads(line)
            except json.JSONDecodeError:
                continue

            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [])
            # Handle MultiPoint: [[lon, lat]] or Point: [lon, lat]
            if coords and isinstance(coords[0], list):
                coords = coords[0]

            lon = _parse_float(coords[0]) if len(coords) > 0 else None
            lat = _parse_float(coords[1]) if len(coords) > 1 else None

            vals = {
                "snapshot_id": snapshot_id,
                "address_point_id": _parse_int(props.get("ADDRESS_POINT_ID")),
                "address_full": _clean_str(props.get("ADDRESS_FULL")),
                "address_number": _clean_str(props.get("ADDRESS_NUMBER")),
                "lo_num": _parse_int(props.get("LO_NUM")),
                "lo_num_suf": _clean_str(props.get("LO_NUM_SUF")),
                "hi_num": _parse_int(props.get("HI_NUM")),
                "hi_num_suf": _clean_str(props.get("HI_NUM_SUF")),
                "linear_name_full": _clean_str(props.get("LINEAR_NAME_FULL")),
                "linear_name": _clean_str(props.get("LINEAR_NAME")),
                "linear_name_type": _clean_str(props.get("LINEAR_NAME_TYPE")),
                "linear_name_dir": _clean_str(props.get("LINEAR_NAME_DIR")),
                "municipality_name": _clean_str(props.get("MUNICIPALITY_NAME")),
                "ward_name": _clean_str(props.get("WARD_NAME")),
                "longitude": lon,
                "latitude": lat,
            }

            # Everything else goes into extra
            extra_keys = set(props.keys()) - set(TRACKED_COLUMNS) - {"_id"}
            extra = {k: props[k] for k in sorted(extra_keys) if props.get(k) is not None}
            vals["extra"] = json.dumps(extra) if extra else None

            if vals["address_point_id"] is None:
                continue  # skip features without a valid key

            batch.append(vals)
            row_count += 1

            if len(batch) >= batch_size:
                _insert_batch(conn, batch)
                batch = []
                if row_count % 50000 == 0:
                    print(f"  {row_count:,} rows ...")

    if batch:
        _insert_batch(conn, batch)

    conn.execute(
        "UPDATE snapshots SET row_count = ? WHERE id = ?", (row_count, snapshot_id)
    )
    conn.commit()
    conn.close()
    print(f"Imported {row_count:,} rows as snapshot {snapshot_id}")
    return snapshot_id


def _insert_batch(conn, batch):
    cols = list(batch[0].keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    sql = f"INSERT OR REPLACE INTO addresses ({col_names}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(row[c] for c in cols) for row in batch])
    conn.commit()


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
