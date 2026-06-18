#!/usr/bin/env python3
"""Step-6 notifier test (deterministic, offline — a fake sender records messages)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime  # noqa: E402

from pragueflats import db, notify  # noqa: E402

T = "2026-06-18T08:00:00+00:00"
ACTIVE = datetime(2026, 6, 18, 12, 0)   # noon Prague — pings allowed
QUIET = datetime(2026, 6, 18, 22, 0)    # 22:00 Prague — quiet hours


def seed(conn, lid, score, *, status="new"):
    conn.execute(
        """INSERT INTO listings (id, dedup_key, disposition, district, area_m2, all_in_czk,
               all_in_estimated, commute_min, score, passes_filters, first_seen_at,
               last_seen_at, address, street)
           VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?)""",
        (lid, f"k{lid}", "1+kk", "Praha 7", 30, 17000, 0, 12, score, T, T,
         f"Street {lid}", f"Street{lid}"))
    conn.execute(
        """INSERT INTO sources (listing_id, source, source_id, url, is_agency, price_czk,
               charges_czk, first_seen_at, last_seen_at, is_active)
           VALUES (?,?,?,?,?,?,?,?,?,1)""",
        (lid, "sreality", f"s{lid}", f"http://x/{lid}", 0, 17000, None, T, T))
    conn.execute("INSERT INTO status_tracker (listing_id, status, updated_at) VALUES (?,?,?)",
                 (lid, status, T))


def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise AssertionError(label)


def main():
    print("Step-6 notifier test")
    conn = db.connect(":memory:")
    db.init(conn)
    msgs = []
    send = lambda t: (msgs.append(t) or True)  # noqa: E731

    seed(conn, 1, 0.80)
    seed(conn, 2, 0.78)
    seed(conn, 3, 0.50)                 # below threshold
    seed(conn, 4, 0.90, status="dismissed")
    conn.commit()

    # Quiet hours: nothing sends, nothing is marked (matches just wait for morning).
    check("quiet hours boundary: 19:00 quiet, 08:00 active",
          notify.in_quiet_hours(datetime(2026, 6, 18, 19))
          and not notify.in_quiet_hours(datetime(2026, 6, 18, 8)))
    check("quiet hours: run is suppressed, no messages",
          notify.run_instant(conn, send=send, now=QUIET) == 0 and not msgs)
    check("quiet hours: nothing marked notified",
          conn.execute("SELECT COUNT(*) FROM listings WHERE notified_at IS NOT NULL").fetchone()[0] == 0)

    # Cold start (waking hours): one baseline message, covers the 2 eligible high-score flats.
    n = notify.run_instant(conn, send=send, now=ACTIVE)
    check("cold start: single baseline message", len(msgs) == 1)
    check("cold start: covers 2 (not low-score, not dismissed)", n == 2)
    check("cold start: dismissed flat left un-notified",
          conn.execute("SELECT notified_at FROM listings WHERE id=4").fetchone()[0] is None)

    # Idempotent: nothing new -> silence.
    msgs.clear()
    n = notify.run_instant(conn, send=send, now=ACTIVE)
    check("re-run: 0 alerts, no messages", n == 0 and not msgs)

    # A new high-score flat appears -> exactly one ping with an inquiry draft.
    seed(conn, 5, 0.82)
    conn.commit()
    msgs.clear()
    n = notify.run_instant(conn, send=send, now=ACTIVE)
    check("new flat: pinged once", n == 1 and len(msgs) == 1)
    check("alert carries Czech inquiry draft", "Dotaz" in msgs[0] and "Dobrý den" in msgs[0])

    # Digest always sends a snapshot.
    msgs.clear()
    ok = notify.run_digest(conn, send=send)
    check("digest: one message, mentions matches", ok and len(msgs) == 1 and "match" in msgs[0])

    print("\nALL NOTIFIER CHECKS PASSED")


if __name__ == "__main__":
    main()
