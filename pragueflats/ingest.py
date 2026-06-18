"""Idempotent ingest: take normalized listings, upsert into the DB, and report what is
genuinely new and what changed price.

Idempotency guarantees (the backbone everything else sits on):
  * re-running with identical data reports 0 new and 0 price changes
  * a flat seen before is never "new" again (keyed on the portal's own id)
  * price_history only grows when a price actually changes
A crashed mid-run is safe to re-run: every write is an idempotent upsert, committed by
the caller at the end.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from .db import VALID_STATUSES
from .normalize import RawListing, dedup_key


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class PriceChange:
    listing_id: int
    source: str
    source_id: str
    url: str
    old_price: int | None
    new_price: int | None


@dataclass
class IngestReport:
    seen: int = 0                 # listings processed this run
    new_listings: int = 0         # brand-new canonical flats
    new_sources: int = 0          # brand-new portal appearances ("new" for alerts)
    price_changes: list[PriceChange] = field(default_factory=list)
    new_listing_ids: list[int] = field(default_factory=list)

    def summary(self) -> str:
        drops = sum(1 for c in self.price_changes
                    if c.old_price and c.new_price and c.new_price < c.old_price)
        return (f"seen={self.seen}  new={self.new_sources}  "
                f"price_changes={len(self.price_changes)} (drops={drops})")


def _upsert_listing(conn, rl: RawListing, now: str) -> tuple[int, bool]:
    dk = dedup_key(rl)
    row = conn.execute("SELECT id FROM listings WHERE dedup_key = ?", (dk,)).fetchone()
    if row:
        conn.execute("UPDATE listings SET last_seen_at = ? WHERE id = ?", (now, row["id"]))
        return row["id"], False
    cur = conn.execute(
        """INSERT INTO listings (dedup_key, disposition, area_m2, district, city_part,
               street, address, latitude, longitude, geo_precision, first_seen_at, last_seen_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (dk, rl.disposition, rl.area_m2, rl.district, rl.city_part, rl.street, rl.address,
         rl.latitude, rl.longitude, rl.geo_precision, now, now),
    )
    listing_id = cur.lastrowid
    conn.execute(
        "INSERT INTO status_tracker (listing_id, status, updated_at) VALUES (?, 'new', ?)",
        (listing_id, now),
    )
    return listing_id, True


def _upsert_source(conn, listing_id: int, rl: RawListing, now: str, report: IngestReport):
    row = conn.execute(
        "SELECT id, price_czk FROM sources WHERE source = ? AND source_id = ?",
        (rl.source, rl.source_id),
    ).fetchone()
    images_json = json.dumps(rl.images, ensure_ascii=False)
    raw_json = json.dumps(rl.raw, ensure_ascii=False)

    if row is None:
        cur = conn.execute(
            """INSERT INTO sources (listing_id, source, source_id, url, is_agency,
                   premise_name, price_czk, images_json, raw_json,
                   first_seen_at, last_seen_at, is_active)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""",
            (listing_id, rl.source, rl.source_id, rl.url, int(rl.is_agency),
             rl.premise_name, rl.price_czk, images_json, raw_json, now, now),
        )
        src_id = cur.lastrowid
        conn.execute(
            "INSERT INTO price_history (source_row_id, price_czk, observed_at) VALUES (?,?,?)",
            (src_id, rl.price_czk, now),
        )
        report.new_sources += 1
        return

    src_id, old_price = row["id"], row["price_czk"]
    conn.execute(
        """UPDATE sources SET url = ?, is_agency = ?, premise_name = ?, price_czk = ?,
               images_json = ?, raw_json = ?, last_seen_at = ?, is_active = 1
           WHERE id = ?""",
        (rl.url, int(rl.is_agency), rl.premise_name, rl.price_czk, images_json, raw_json,
         now, src_id),
    )
    if rl.price_czk is not None and rl.price_czk != old_price:
        conn.execute(
            "INSERT INTO price_history (source_row_id, price_czk, observed_at) VALUES (?,?,?)",
            (src_id, rl.price_czk, now),
        )
        report.price_changes.append(PriceChange(
            listing_id=listing_id, source=rl.source, source_id=rl.source_id,
            url=rl.url, old_price=old_price, new_price=rl.price_czk,
        ))


def ingest(conn, listings: Iterable[RawListing], now: str | None = None) -> IngestReport:
    now = now or _now()
    report = IngestReport()
    for rl in listings:
        report.seen += 1
        listing_id, is_new_listing = _upsert_listing(conn, rl, now)
        if is_new_listing:
            report.new_listings += 1
            report.new_listing_ids.append(listing_id)
        _upsert_source(conn, listing_id, rl, now, report)
    return report


def set_status(conn, listing_id: int, status: str, note: str | None = None) -> None:
    """Lifecycle transition. A dismissed flat staying dismissed is what stops it
    re-pinging later (notifier logic, step 6)."""
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}; expected one of {VALID_STATUSES}")
    conn.execute(
        """INSERT INTO status_tracker (listing_id, status, updated_at, note)
           VALUES (?,?,?,?)
           ON CONFLICT(listing_id) DO UPDATE SET status = excluded.status,
               updated_at = excluded.updated_at, note = excluded.note""",
        (listing_id, status, _now(), note),
    )
