#!/usr/bin/env python3
"""CLI for the pipeline.

  python run.py ingest            # pull Sreality, store, report new + price changes
  python run.py ingest --pages 5  # shallower crawl
  python run.py stats             # what's in the DB
"""
import argparse

from pragueflats import config, db
from pragueflats.ingest import ingest
from pragueflats.portals import sreality


def cmd_ingest(args):
    conn = db.connect()
    db.init(conn)
    print(f"Crawling Sreality (up to {args.pages} pages)…")
    listings = list(sreality.fetch(max_pages=args.pages))
    report = ingest(conn, listings)
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    print(f"\nSreality ingest — {report.summary()}")
    print(f"  total flats in DB: {total}")
    for c in report.price_changes[:10]:
        arrow = "↓" if (c.old_price or 0) > (c.new_price or 0) else "↑"
        print(f"  price {arrow} {c.old_price}→{c.new_price}  {c.url}")
    conn.close()


def cmd_stats(args):
    conn = db.connect()
    db.init(conn)
    n_listings = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    n_sources = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    n_prices = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
    print(f"DB: {config.DB_PATH}")
    print(f"  canonical flats : {n_listings}")
    print(f"  source listings : {n_sources}")
    print(f"  price points    : {n_prices}")
    print("  by district:")
    for row in conn.execute(
        """SELECT COALESCE(district,'(unknown)') d, COUNT(*) n
           FROM listings GROUP BY d ORDER BY n DESC LIMIT 12"""):
        print(f"    {row['d']:<16} {row['n']}")
    print("  by status:")
    for row in conn.execute(
        "SELECT status, COUNT(*) n FROM status_tracker GROUP BY status ORDER BY n DESC"):
        print(f"    {row['status']:<16} {row['n']}")
    conn.close()


def main():
    p = argparse.ArgumentParser(description="Prague flat-hunt pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="crawl Sreality and store new/changed listings")
    pi.add_argument("--pages", type=int, default=config.SREALITY_MAX_PAGES)
    pi.set_defaults(func=cmd_ingest)

    ps = sub.add_parser("stats", help="show what's in the DB")
    ps.set_defaults(func=cmd_stats)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
