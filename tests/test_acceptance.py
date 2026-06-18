#!/usr/bin/env python3
"""Step-2 acceptance test (deterministic, offline).

The spec's bar: ingest twice; the second run reports 0 false-new and correctly flags any
price change. Runs against an in-memory DB with fixtures so it's fast and repeatable.

Run:  python tests/test_acceptance.py     (no pytest needed)
"""
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pragueflats import db                       # noqa: E402
from pragueflats.ingest import ingest, set_status  # noqa: E402
from pragueflats.normalize import RawListing      # noqa: E402


def _fixture(source_id, price, *, street, area, disp="1+kk", district="Praha 7"):
    return RawListing(
        source="sreality", source_id=source_id,
        url=f"https://www.sreality.cz/detail/.../{source_id}",
        disposition=disp, area_m2=area, price_czk=price, price_per_m2=round(price / area),
        district=district, city_part="Holešovice", street=street,
        address=f"{street}, {district}", latitude=50.1, longitude=14.43,
        geo_precision="street", is_agency=True, premise_name="acme",
        images=["https://img/1.jpg"], raw={"id": source_id, "priceCzk": price},
    )


FIXTURES = [
    _fixture("1001", 17500, street="Dělnická", area=30),
    _fixture("1002", 22000, street="Kamenická", area=45, disp="2+kk"),
    _fixture("1003", 15900, street="Veletržní", area=28),
]


def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise AssertionError(label)


def main():
    conn = db.connect(":memory:")
    db.init(conn)
    print("Step-2 acceptance test")

    # Run 1 — everything is new, no price changes, one price-history point each.
    r1 = ingest(conn, FIXTURES, now="2026-06-18T08:00:00+00:00")
    check("run1: all 3 are new", r1.new_sources == 3 and r1.new_listings == 3)
    check("run1: no price changes", len(r1.price_changes) == 0)
    check("run1: 3 price-history points",
          conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 3)

    # Run 2 — identical data. The whole point: zero false-new, zero phantom changes.
    r2 = ingest(conn, FIXTURES, now="2026-06-18T10:00:00+00:00")
    check("run2: 0 false-new", r2.new_sources == 0 and r2.new_listings == 0)
    check("run2: 0 price changes", len(r2.price_changes) == 0)
    check("run2: still 3 flats (no duplication)",
          conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 3)

    # Run 3 — one flat drops 17500 -> 16000. Must be flagged, identity preserved.
    dropped = [replace(FIXTURES[0], price_czk=16000, price_per_m2=533)] + FIXTURES[1:]
    r3 = ingest(conn, dropped, now="2026-06-19T08:00:00+00:00")
    check("run3: 0 new (a price drop is not a new flat)", r3.new_sources == 0)
    check("run3: exactly 1 price change", len(r3.price_changes) == 1)
    pc = r3.price_changes[0]
    check("run3: change is 17500 -> 16000 (a drop)",
          pc.old_price == 17500 and pc.new_price == 16000)
    check("run3: that flat now has 2 price-history points",
          conn.execute(
              """SELECT COUNT(*) FROM price_history ph
                 JOIN sources s ON s.id = ph.source_row_id
                 WHERE s.source_id = '1001'""").fetchone()[0] == 2)

    # Run 4 — re-run the dropped data: must be idempotent again (no re-flag).
    r4 = ingest(conn, dropped, now="2026-06-19T10:00:00+00:00")
    check("run4: idempotent after a change (0 new, 0 changes)",
          r4.new_sources == 0 and len(r4.price_changes) == 0)

    # Lifecycle: dismiss persists and validates.
    lid = conn.execute("SELECT id FROM listings LIMIT 1").fetchone()["id"]
    set_status(conn, lid, "dismissed", note="too far")
    st = conn.execute("SELECT status FROM status_tracker WHERE listing_id = ?", (lid,)).fetchone()
    check("status: dismiss persisted", st["status"] == "dismissed")
    try:
        set_status(conn, lid, "bogus")
        check("status: invalid rejected", False)
    except ValueError:
        check("status: invalid rejected", True)

    print("\nALL ACCEPTANCE CHECKS PASSED")


if __name__ == "__main__":
    main()
