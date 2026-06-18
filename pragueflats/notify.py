"""Telegram notifications.

Two channels:
  * instant — a new flat scoring >= the notify threshold pings you immediately. Each flat
    fires at most once (notified_at), a dismissed flat never pings, and the very first run
    sends a single baseline summary instead of flooding you with every existing match.
  * digest  — a twice-daily snapshot of the current top matches.

Each instant alert carries a ready-to-send Czech inquiry line. The Telegram send is passed
in (a `send(text) -> bool` callable) so the logic is testable without the network.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def inquiry_draft(disposition: str | None, street: str | None) -> str:
    where = f" na ulici {street}" if street else ""
    disp = f" {disposition}" if disposition else ""
    return (f"Dobrý den, máte ještě volný tento byt{disp}{where}? "
            f"Měl(a) bych zájem o prohlídku. Děkuji.")


def _fmt_flat(row, rank: int | None = None) -> str:
    est = "~" if row["all_in_estimated"] else ""
    allin = f"{row['all_in_czk']:,}{est} Kč all-in" if row["all_in_czk"] else "price ?"
    commute = f"{row['commute_min']} min to work" if row["commute_min"] is not None else "commute ?"
    head = f"{rank}. " if rank else ""
    return (f"{head}{row['score']:.2f} · {row['disposition'] or '?'} · "
            f"{row['district'] or '?'} · {allin} · {commute}\n"
            f"{row['address'] or ''}\n{row['url']}")


def _candidates(conn, extra=""):
    """Filter-passing, scored, non-dismissed flats with their cheapest source URL."""
    return conn.execute(
        f"""SELECT l.id, l.score, l.disposition, l.district, l.all_in_czk,
                   l.all_in_estimated, l.commute_min, l.address, l.street,
                   l.first_seen_at, l.notified_at, COALESCE(st.status,'new') AS status,
                   (SELECT url FROM sources s WHERE s.listing_id = l.id AND s.is_active = 1
                    ORDER BY (s.price_czk + COALESCE(s.charges_czk, 0)) LIMIT 1) AS url
            FROM listings l
            LEFT JOIN status_tracker st ON st.listing_id = l.id
            WHERE l.passes_filters = 1 AND l.score IS NOT NULL
              AND COALESCE(st.status,'new') != 'dismissed' {extra}
            ORDER BY l.score DESC""").fetchall()


def run_instant(conn, *, send, threshold: float | None = None, cap: int = 10) -> int:
    """Ping new high-score flats. Returns how many flats were covered."""
    threshold = config.NOTIFY_THRESHOLD if threshold is None else threshold
    pending = _candidates(conn, f"AND l.score >= {threshold} AND l.notified_at IS NULL")
    if not pending:
        return 0

    ever = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE notified_at IS NOT NULL").fetchone()[0]
    now = _now_iso()

    if ever == 0:
        # First run: one baseline message, then mark all current matches notified so they
        # don't flood later. From now on only genuinely new matches ping.
        lines = ["📋 Prague flat-hunt is live.",
                 f"{len(pending)} flats currently match your filters at score ≥ {threshold}. "
                 f"Top picks:"]
        lines += [_fmt_flat(r, i) for i, r in enumerate(pending[:5], 1)]
        lines.append("You'll get an instant ping whenever a new top flat appears.")
        send("\n\n".join(lines))
        conn.execute(
            """UPDATE listings SET notified_at = ? WHERE score >= ? AND notified_at IS NULL
               AND id NOT IN (SELECT listing_id FROM status_tracker WHERE status = 'dismissed')""",
            (now, threshold))
        conn.commit()
        return len(pending)

    sent = 0
    for r in pending[:cap]:
        text = ("🏠 New match for you\n" + _fmt_flat(r) +
                "\n\nDotaz k odeslání: " + inquiry_draft(r["disposition"], r["street"]))
        if send(text):
            sent += 1
        conn.execute("UPDATE listings SET notified_at = ? WHERE id = ?", (now, r["id"]))
    if len(pending) > cap:
        send(f"…and {len(pending) - cap} more new matches — see the digest.")
        conn.executemany("UPDATE listings SET notified_at = ? WHERE id = ?",
                         [(now, r["id"]) for r in pending[cap:]])
    conn.commit()
    return sent


def run_digest(conn, *, send, top_n: int = 8) -> bool:
    rows = _candidates(conn)
    above = [r for r in rows if r["score"] >= config.NOTIFY_THRESHOLD]
    day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).replace(microsecond=0).isoformat()
    new_24h = sum(1 for r in rows if (r["first_seen_at"] or "") >= day_ago)

    lines = ["📋 Prague flat-hunt — digest",
             f"{len(rows)} flats match your filters · {len(above)} above "
             f"{config.NOTIFY_THRESHOLD} · {new_24h} new in 24h.", ""]
    if rows:
        lines += [_fmt_flat(r, i) for i, r in enumerate(rows[:top_n], 1)]
    else:
        lines.append("No matches right now — widen the ceiling or districts in config.")
    return send("\n\n".join(lines))
