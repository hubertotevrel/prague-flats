#!/usr/bin/env python3
"""Map generator smoke test (offline)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime  # noqa: E402

from pragueflats import db, mapgen  # noqa: E402

T = "2026-06-18T08:00:00+00:00"
NOW = datetime(2026, 6, 18, 12, 0)   # fake clock so the fixtures count as fresh


def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise AssertionError(label)


def main():
    print("Map generator test")
    conn = db.connect(":memory:")
    db.init(conn)
    conn.execute(
        """INSERT INTO listings (id, dedup_key, disposition, district, city_part, street,
               area_m2, all_in_czk, all_in_estimated, commute_min, score, passes_filters,
               first_seen_at, last_seen_at, address, latitude, longitude)
           VALUES (1,'k1','2+1','Praha 5','Košíře','Plzeňská',42,17150,0,11,0.83,1,?,?,
                   'Plzeňská, Praha 5',50.07,14.36)""", (T, T))
    conn.execute(
        """INSERT INTO sources (listing_id, source, source_id, url, is_agency, price_czk,
               charges_czk, images_json, first_seen_at, last_seen_at, is_active)
           VALUES (1,'bezrealitky','b1','http://example/flat1',0,16000,1150,
                   '["//img/1.jpg"]',?,?,1)""", (T, T))
    # a listing without coordinates must be skipped (can't be plotted)
    conn.execute(
        """INSERT INTO listings (id, dedup_key, disposition, district, score, passes_filters,
               first_seen_at, last_seen_at) VALUES (2,'k2','2+1','Praha 7',0.9,1,?,?)""", (T, T))
    # a stale listing (not re-seen for > STALE_DAYS) must be skipped too
    conn.execute(
        """INSERT INTO listings (id, dedup_key, disposition, district, score, passes_filters,
               first_seen_at, last_seen_at, latitude, longitude)
           VALUES (3,'k3','3+kk','Praha 6',0.95,1,?,'2026-06-10T08:00:00+00:00',50.09,14.39)""",
        (T,))
    conn.commit()

    html, n = mapgen.build_html(conn, now=NOW)
    check("only the fresh geocoded flat is plotted (not the coord-less or stale one)", n == 1)
    check("no template placeholders remain", "__FLATS__" not in html and "__WORK__" not in html)
    check("listing url embedded", "http://example/flat1" in html)
    check("work coords embedded", '"label"' in html and str(50.0744)[:6] in html)
    check("leaflet + inquiry present", "leaflet" in html.lower() and "Dobrý den" in html)

    print("\nALL MAP CHECKS PASSED")


if __name__ == "__main__":
    main()
