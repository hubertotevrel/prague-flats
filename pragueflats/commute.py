"""Door-to-door public-transport time to work via Google Routes API (computeRoutes,
travelMode=TRANSIT). Mapy can't do transit; Google can, and for Prague PID it's accurate.

Results are cached per ~100 m GPS bucket in commute_cache, so a deep crawl costs a
handful of API calls, not one per listing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config
from .http import make_session

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
_PRAGUE = ZoneInfo("Europe/Prague")


def _geo_key(lat: float, lon: float) -> str:
    return f"{lat:.3f},{lon:.3f}"


def next_morning_peak_utc(hour: int = 8) -> str:
    """Next weekday at `hour` Prague local time, as RFC3339 UTC. Transit routing needs a
    future departure with a real timetable, so we anchor on the next working-day morning."""
    now = datetime.now(_PRAGUE)
    cand = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if cand <= now:
        cand += timedelta(days=1)
    while cand.weekday() >= 5:  # 5,6 = Sat,Sun
        cand += timedelta(days=1)
    return cand.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _google_transit_minutes(lat, lon, *, api_key, departure, session) -> int | None:
    body = {
        "origin": {"location": {"latLng": {"latitude": lat, "longitude": lon}}},
        "destination": {"location": {"latLng": {
            "latitude": config.WORK_LAT, "longitude": config.WORK_LON}}},
        "travelMode": "TRANSIT",
        "departureTime": departure,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration",
    }
    r = session.post(ROUTES_URL, json=body, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Google Routes HTTP {r.status_code}: {r.text[:200]}")
    routes = r.json().get("routes", [])
    if not routes:
        return None
    seconds = int(str(routes[0]["duration"]).rstrip("s"))
    return round(seconds / 60)


def transit_minutes(conn, lat, lon, *, api_key, session=None, departure=None,
                    now_iso=None) -> int | None:
    """Cached transit minutes from (lat, lon) to work. Returns None if no route / no coords."""
    if lat is None or lon is None:
        return None
    key = _geo_key(lat, lon)
    row = conn.execute("SELECT minutes FROM commute_cache WHERE geo_key = ?", (key,)).fetchone()
    if row is not None:
        return row["minutes"]
    session = session or make_session()
    departure = departure or next_morning_peak_utc()
    minutes = _google_transit_minutes(lat, lon, api_key=api_key, departure=departure, session=session)
    stamp = now_iso or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn.execute("INSERT OR REPLACE INTO commute_cache (geo_key, minutes, computed_at) VALUES (?,?,?)",
                 (key, minutes, stamp))
    return minutes
