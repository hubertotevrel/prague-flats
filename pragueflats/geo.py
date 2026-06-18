"""Address -> GPS via Mapy.com geocoding, cached. Used for sources that don't ship
coordinates (iDnes). Sreality and Bezrealitky already include GPS."""
from __future__ import annotations

from datetime import datetime, timezone

from .http import make_session

GEOCODE_URL = "https://api.mapy.com/v1/geocode"


def _key(query: str) -> str:
    return " ".join(query.split()).lower()


def geocode(conn, query, *, api_key, session=None, now_iso=None):
    """Return (lat, lon) for a free-text address, cached. (None, None) if not resolvable."""
    if not query or not api_key:
        return (None, None)
    k = _key(query)
    row = conn.execute(
        "SELECT latitude, longitude FROM geocode_cache WHERE query_key = ?", (k,)).fetchone()
    if row is not None:
        return (row["latitude"], row["longitude"])

    session = session or make_session()
    r = session.get(GEOCODE_URL, timeout=30,
                    params={"query": query, "apikey": api_key, "limit": 1, "lang": "cs"})
    r.raise_for_status()
    items = r.json().get("items", [])
    if items:
        pos = items[0].get("position", {})
        lat, lon = pos.get("lat"), pos.get("lon")
    else:
        lat, lon = None, None
    stamp = now_iso or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO geocode_cache (query_key, latitude, longitude, computed_at) "
        "VALUES (?,?,?,?)", (k, lat, lon, stamp))
    return (lat, lon)
