#!/usr/bin/env python3
"""CLI for the pipeline.

  python run.py ingest            # pull Sreality, store, report new + price changes
  python run.py ingest --pages 5  # shallower crawl
  python run.py stats             # what's in the DB
"""
import argparse
import json
import os

from pragueflats import commute, config, db, geo, notify, scoring
from pragueflats.http import make_session
from pragueflats.ingest import ingest
from pragueflats.portals import bezrealitky, idnes, sreality

SOURCES = [
    ("sreality", sreality.fetch),
    ("bezrealitky", bezrealitky.fetch),
    ("idnes", idnes.fetch),
]


def _load_dotenv(path=".env"):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


def cmd_ingest(args):
    conn = db.connect()
    db.init(conn)
    print(f"Crawling sources (up to {args.pages} pages each)…")
    all_raws, down = [], []
    for name, fetch in SOURCES:
        try:
            raws = list(fetch(max_pages=args.pages))
            all_raws.extend(raws)
            print(f"  {name:<12} {len(raws)} listings")
        except Exception as e:  # one source failing must never sink the whole run
            down.append(name)
            print(f"  {name:<12} DOWN — {type(e).__name__}: {e}")
    report = ingest(conn, all_raws)
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    print(f"\nIngest — {report.summary()}")
    print(f"  total canonical flats in DB: {total}")
    if down:
        print(f"  sources down today: {', '.join(down)}")
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


def cmd_score(args):
    from datetime import datetime, timezone
    _load_dotenv()
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("GOOGLE_MAPS_API_KEY not set — add it to .env (see README step 3).")
        return

    mapy_key = os.environ.get("MAPY_API_KEY")
    conn = db.connect()
    db.init(conn)
    session = make_session()
    departure = commute.next_morning_peak_utc()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # One candidate per canonical flat, from its cheapest active source by all-in cost
    # (base + real charges when the source provides them).
    rows = conn.execute(
        """SELECT l.id, l.disposition, l.area_m2, l.district, l.latitude, l.longitude,
                  l.address, s.price_czk AS base_price, s.charges_czk AS charges
           FROM listings l
           JOIN sources s ON s.id = (
               SELECT s2.id FROM sources s2
               WHERE s2.listing_id = l.id AND s2.is_active = 1 AND s2.price_czk IS NOT NULL
               ORDER BY (s2.price_czk + COALESCE(s2.charges_czk, 0)) ASC LIMIT 1)
        """).fetchall()

    n_pass = n_scored = n_geo = 0
    cache_before = conn.execute("SELECT COUNT(*) FROM commute_cache").fetchone()[0]
    for r in rows:
        base, area, charges = r["base_price"], r["area_m2"], r["charges"]
        all_in, est = scoring.all_in_cost(base, area, charges)
        if not scoring.passes_hard_filters(r["disposition"], base, all_in, est):
            conn.execute(
                "UPDATE listings SET passes_filters=0, all_in_czk=?, all_in_estimated=?, "
                "score=NULL, scored_at=? WHERE id=?", (all_in, int(est), now, r["id"]))
            continue
        n_pass += 1
        lat, lon = r["latitude"], r["longitude"]
        if (lat is None or lon is None) and r["address"] and mapy_key:
            lat, lon = geo.geocode(conn, r["address"], api_key=mapy_key, session=session)
            if lat is not None:
                conn.execute("UPDATE listings SET latitude=?, longitude=? WHERE id=?",
                             (lat, lon, r["id"]))
                n_geo += 1
        minutes = commute.transit_minutes(conn, lat, lon, api_key=api_key,
                                          session=session, departure=departure)
        ppm = base / area if base and area else None
        sc, breakdown = scoring.score(minutes, ppm, r["district"])
        conn.execute(
            "UPDATE listings SET passes_filters=1, all_in_czk=?, all_in_estimated=?, "
            "commute_min=?, score=?, score_json=?, scored_at=? WHERE id=?",
            (all_in, int(est), minutes, sc, json.dumps(breakdown), now, r["id"]))
        n_scored += 1
    conn.commit()
    api_calls = conn.execute("SELECT COUNT(*) FROM commute_cache").fetchone()[0] - cache_before
    notify = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE score >= ?", (config.NOTIFY_THRESHOLD,)).fetchone()[0]
    print(f"Scored {n_scored} flats ({n_pass} passed of {len(rows)}); {n_geo} geocoded, "
          f"{api_calls} new commute lookups; {notify} above notify threshold "
          f"({config.NOTIFY_THRESHOLD}).")
    conn.close()


def cmd_top(args):
    conn = db.connect()
    db.init(conn)
    rows = conn.execute(
        """SELECT l.*, st.status,
                  (SELECT url FROM sources s WHERE s.listing_id = l.id AND s.is_active = 1
                   ORDER BY s.price_czk LIMIT 1) AS url,
                  (SELECT MIN(price_czk) FROM sources s WHERE s.listing_id = l.id
                   AND s.is_active = 1) AS base_price
           FROM listings l
           LEFT JOIN status_tracker st ON st.listing_id = l.id
           WHERE l.passes_filters = 1 AND l.score IS NOT NULL
           ORDER BY l.score DESC LIMIT ?""", (args.n,)).fetchall()
    if not rows:
        print("No scored listings yet. Run:  python run.py score")
        return
    print(f"{'score':>5}  {'commute':>7}  {'all-in':>8}  {'disp':<6} {'district':<9} address")
    for r in rows:
        commute_s = f"{r['commute_min']}m" if r["commute_min"] is not None else "  ?"
        allin = f"{r['all_in_czk']:,}{'~' if r['all_in_estimated'] else ''}" if r["all_in_czk"] else "?"
        print(f"{r['score']:>5.3f}  {commute_s:>7}  {allin:>8}  {r['disposition'] or '?':<6} "
              f"{(r['district'] or '?'):<9} {r['address'] or ''}")
        print(f"       {r['url']}")
    conn.close()


def _telegram_sender(token, chat_id, session):
    def send(text, reply_markup=None):
        data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        r = session.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=30, data=data)
        return bool(r.json().get("ok"))
    return send


def _telegram_or_none():
    _load_dotenv()
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set (see .env / GitHub secrets).")
        return None
    return _telegram_sender(token, chat, make_session())


def cmd_notify(args):
    send = _telegram_or_none()
    if not send:
        return
    conn = db.connect()
    db.init(conn)
    n = notify.run_instant(conn, send=send)
    print(f"Instant alerts: {n} flat(s) covered.")
    conn.close()


def cmd_digest(args):
    send = _telegram_or_none()
    if not send:
        return
    conn = db.connect()
    db.init(conn)
    ok = notify.run_digest(conn, send=send)
    print(f"Digest sent: {ok}")
    conn.close()


def cmd_map(args):
    from pragueflats import mapgen
    conn = db.connect()
    db.init(conn)
    html, n = mapgen.build_html(conn)
    out = config.ROOT / "docs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Map written to {out} ({n} flats plotted).")
    conn.close()


def cmd_status(args):
    from pragueflats.ingest import set_status
    conn = db.connect()
    db.init(conn)
    set_status(conn, args.id, args.state, note=args.note)
    conn.commit()
    print(f"listing {args.id} -> {args.state}")
    conn.close()


def main():
    p = argparse.ArgumentParser(description="Prague flat-hunt pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="crawl Sreality and store new/changed listings")
    pi.add_argument("--pages", type=int, default=config.SREALITY_MAX_PAGES)
    pi.set_defaults(func=cmd_ingest)

    ps = sub.add_parser("stats", help="show what's in the DB")
    ps.set_defaults(func=cmd_stats)

    pc = sub.add_parser("score", help="apply hard filters + commute + 0–1 score")
    pc.set_defaults(func=cmd_score)

    pt = sub.add_parser("top", help="show the top-ranked flats")
    pt.add_argument("-n", type=int, default=15)
    pt.set_defaults(func=cmd_top)

    pn = sub.add_parser("notify", help="Telegram: instant alerts for new high-score flats")
    pn.set_defaults(func=cmd_notify)

    pd = sub.add_parser("digest", help="Telegram: twice-daily digest of top matches")
    pd.set_defaults(func=cmd_digest)

    pm = sub.add_parser("map", help="generate the Leaflet dashboard (docs/index.html)")
    pm.set_defaults(func=cmd_map)

    pst = sub.add_parser("status", help="set a flat's lifecycle status (affects alerts)")
    pst.add_argument("id", type=int)
    pst.add_argument("state", choices=db.VALID_STATUSES)
    pst.add_argument("--note", default=None)
    pst.set_defaults(func=cmd_status)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
