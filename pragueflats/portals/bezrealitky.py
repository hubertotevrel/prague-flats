"""Bezrealitky adapter — public GraphQL API (listAdverts).

Direct-from-landlord (no commission), and uniquely it exposes real `charges`, so the
all-in cost is exact rather than estimated. Ships GPS, so no geocoding needed.
See docs/RECON.md.
"""
from __future__ import annotations

import time
from typing import Iterator

from ..http import make_session
from ..normalize import RawListing

GRAPHQL_URL = "https://api.bezrealitky.cz/graphql/"
PRAGUE_REGION_ID = "486"  # listRegions(locale:CS): {"Praha": id 486, osmId 435514}
DETAIL_BASE = "https://www.bezrealitky.cz/nemovitosti-byty-domy/"

_DISPOSITION = {
    "GARSONIERA": "1+kk",
    "DISP_1_KK": "1+kk", "DISP_1_1": "1+1",
    "DISP_2_KK": "2+kk", "DISP_2_1": "2+1",
    "DISP_3_KK": "3+kk", "DISP_3_1": "3+1",
    "DISP_4_KK": "4+kk", "DISP_4_1": "4+1",
    "DISP_5_KK": "5+kk", "DISP_5_1": "5+1",
    "DISP_6_KK": "6+kk", "DISP_6_1": "6+1",
    "DISP_7_KK": "7+kk", "DISP_7_1": "7+1",
}

_QUERY = """query($limit:Int,$offset:Int,$region:ID){
  listAdverts(offerType:[PRONAJEM], estateType:[BYT], regionId:$region,
              limit:$limit, offset:$offset, order:TIMEORDER_DESC){
    totalCount
    list{ id uri price charges surface disposition street houseNumber
          city(locale:CS) cityDistrict(locale:CS) zip availableFrom gps{ lat lng } }
  }
}"""


def _district_from_zip(zip_str: str | None) -> str | None:
    """Prague PSČ '1d0 00' maps to the numbered district 'Praha d' (d=0 -> Praha 10).
    This aligns with Sreality's district field, so the same flat dedups across sources."""
    z = (zip_str or "").replace(" ", "")
    if len(z) >= 2 and z[0] == "1" and z[1].isdigit():
        return f"Praha {10 if z[1] == '0' else int(z[1])}"
    return None


def _to_raw(a: dict) -> RawListing:
    price, surface = a.get("price"), a.get("surface")
    gps = a.get("gps") or {}
    street, num = a.get("street"), a.get("houseNumber")
    city_part = (a.get("cityDistrict") or "").replace("Praha - ", "").strip() or None
    address = ", ".join(x for x in (
        " ".join(y for y in (street, num) if y) or None, city_part, a.get("city")) if x) or None
    return RawListing(
        source="bezrealitky",
        source_id=str(a["id"]),
        url=DETAIL_BASE + a["uri"],
        disposition=_DISPOSITION.get(a.get("disposition")),
        area_m2=float(surface) if surface else None,
        price_czk=price,
        price_per_m2=round(price / surface) if price and surface else None,
        district=_district_from_zip(a.get("zip")),
        city_part=city_part,
        street=street,
        address=address,
        latitude=gps.get("lat"),
        longitude=gps.get("lng"),
        geo_precision="address",
        is_agency=False,            # Bezrealitky is the direct-from-landlord portal
        premise_name=None,
        charges_czk=a.get("charges"),
        images=[],
        raw=a,
    )


def fetch(max_pages: int = 20, *, page_size: int = 50, session=None,
          delay: float = 0.5) -> Iterator[RawListing]:
    """Yield Prague rental flats, newest first, paginating via limit/offset."""
    session = session or make_session()
    seen: set[str] = set()
    for page in range(max_pages):
        resp = session.post(GRAPHQL_URL, timeout=30, json={
            "query": _QUERY,
            "variables": {"limit": page_size, "offset": page * page_size,
                          "region": PRAGUE_REGION_ID}})
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"Bezrealitky GraphQL error: {data['errors'][:1]}")
        items = data["data"]["listAdverts"]["list"]
        if not items:
            break
        fresh = False
        for a in items:
            sid = str(a["id"])
            if sid in seen:
                continue
            seen.add(sid)
            fresh = True
            yield _to_raw(a)
        if not fresh:
            break
        if delay:
            time.sleep(delay)
