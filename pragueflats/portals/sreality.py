"""Sreality adapter.

The documented JSON API (/api/cs/v2/estates) is dead (nginx 404). The live data is
server-rendered into the search page's __NEXT_DATA__ React Query cache, which is richer
than the old API — it already includes GPS, disposition, price/m², district and an
agency flag. See docs/RECON.md.
"""
from __future__ import annotations

import json
import time
from typing import Iterator

from ..http import make_session
from ..normalize import RawListing

SEARCH_URL = "https://www.sreality.cz/hledani/pronajem/byty/praha"
_MARKER = '<script id="__NEXT_DATA__" type="application/json">'


def _extract_payload(html: str) -> dict:
    """Pull the estatesSearch query payload out of the page's __NEXT_DATA__ blob."""
    if _MARKER not in html:
        raise RuntimeError("Sreality page changed: __NEXT_DATA__ not found")
    blob = html.split(_MARKER, 1)[1].split("</script>", 1)[0]
    data = json.loads(blob)
    queries = data["props"]["pageProps"]["dehydratedState"]["queries"]
    es = next(q for q in queries if q["queryKey"][0] == "estatesSearch")
    return es["state"]["data"]


def _detail_url(r: dict, loc: dict) -> str:
    sub = (r.get("categorySubCb") or {}).get("name") or "byt"
    slug = "-".join(x for x in (loc.get("citySeoName"), loc.get("cityPartSeoName"),
                                loc.get("streetSeoName")) if x) or "praha"
    return f"https://www.sreality.cz/detail/pronajem/byt/{sub}/{slug}/{r['id']}"


def _to_raw(r: dict) -> RawListing:
    loc = r.get("locality") or {}
    price = r.get("priceCzk")
    ppm = r.get("priceCzkPerSqM")
    # m² isn't a field, but base/price-per-m² gives it back exactly.
    area = round(price / ppm, 1) if price and ppm else None

    num = loc.get("houseNumber") or loc.get("streetNumber")
    street_full = " ".join(x for x in (loc.get("street"), str(num) if num else None) if x) or None
    address = ", ".join(x for x in (street_full, loc.get("cityPart"), loc.get("city")) if x) or None

    images = []
    for img in (r.get("images") or []):
        u = img.get("url") or ""
        images.append("https:" + u if u.startswith("//") else u)

    return RawListing(
        source="sreality",
        source_id=str(r["id"]),
        url=_detail_url(r, loc),
        disposition=(r.get("categorySubCb") or {}).get("name"),
        area_m2=area,
        price_czk=price,
        price_per_m2=ppm,
        district=loc.get("district"),
        city_part=loc.get("cityPart"),
        street=loc.get("street"),
        address=address,
        latitude=loc.get("latitude"),
        longitude=loc.get("longitude"),
        geo_precision=loc.get("inaccuracyType"),
        is_agency=bool(r.get("premiseId")),
        premise_name=(r.get("premise") or {}).get("seoName"),
        images=images,
        raw=r,
    )


def fetch(max_pages: int = 25, *, session=None, delay: float = 0.8) -> Iterator[RawListing]:
    """Yield normalized Prague rental listings, newest first.

    Paginates ?strana=N until results run out, a page repeats already-seen ids
    (Sreality's known ~100-page loop / exhaustion), or max_pages is hit.
    """
    session = session or make_session()
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        resp = session.get(SEARCH_URL, params={"strana": page}, timeout=30)
        resp.raise_for_status()
        results = _extract_payload(resp.text).get("results", [])
        if not results:
            break
        page_ids = {str(r["id"]) for r in results}
        if page_ids <= seen:  # whole page already seen -> loop or end
            break
        for r in results:
            sid = str(r["id"])
            if sid in seen:
                continue
            seen.add(sid)
            yield _to_raw(r)
        if delay:
            time.sleep(delay)
