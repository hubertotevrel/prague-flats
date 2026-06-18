"""SQLite state. Four tables, matching the pinned schema:

  listings        — one canonical row per real flat (dedup'd across sources)
  sources         — one row per portal *appearance* of a flat (FK -> listings);
                    holds the per-source url, price, agency flag, raw payload
  price_history   — a row per distinct price point observed for a source appearance
  status_tracker  — the lifecycle state per canonical flat
                    (new | shortlisted | dismissed | contacted | viewing_booked)
"""
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id            INTEGER PRIMARY KEY,
    dedup_key     TEXT UNIQUE NOT NULL,
    disposition   TEXT,
    area_m2       REAL,
    district      TEXT,
    city_part     TEXT,
    street        TEXT,
    address       TEXT,
    latitude      REAL,
    longitude     REAL,
    geo_precision TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id            INTEGER PRIMARY KEY,
    listing_id    INTEGER NOT NULL REFERENCES listings(id),
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    url           TEXT,
    is_agency     INTEGER,
    premise_name  TEXT,
    price_czk     INTEGER,
    images_json   TEXT,
    raw_json      TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS price_history (
    id            INTEGER PRIMARY KEY,
    source_row_id INTEGER NOT NULL REFERENCES sources(id),
    price_czk     INTEGER,
    observed_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS status_tracker (
    listing_id INTEGER PRIMARY KEY REFERENCES listings(id),
    status     TEXT NOT NULL DEFAULT 'new',
    updated_at TEXT NOT NULL,
    note       TEXT
);

-- Door-to-door transit time to work, keyed by ~100 m GPS bucket so nearby flats reuse
-- one Google Routes call. minutes may be NULL (no route found) and is still cached.
CREATE TABLE IF NOT EXISTS commute_cache (
    geo_key     TEXT PRIMARY KEY,
    minutes     INTEGER,
    computed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sources_listing ON sources(listing_id);
CREATE INDEX IF NOT EXISTS idx_price_history_src ON price_history(source_row_id);
CREATE INDEX IF NOT EXISTS idx_status ON status_tracker(status);
"""

VALID_STATUSES = ("new", "shortlisted", "dismissed", "contacted", "viewing_booked")


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = str(db_path) if db_path is not None else str(config.DB_PATH)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Scoring columns added to `listings` in step 3. Kept as an idempotent migration so an
# existing DB upgrades in place rather than needing a rebuild.
_LISTING_SCORE_COLS = {
    "all_in_czk": "INTEGER",
    "all_in_estimated": "INTEGER",
    "commute_min": "INTEGER",
    "score": "REAL",
    "score_json": "TEXT",
    "passes_filters": "INTEGER",
    "scored_at": "TEXT",
}


def _migrate(conn: sqlite3.Connection) -> None:
    have = {r["name"] for r in conn.execute("PRAGMA table_info(listings)")}
    for name, typ in _LISTING_SCORE_COLS.items():
        if name not in have:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {name} {typ}")


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
