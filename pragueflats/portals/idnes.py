"""iDnes Reality adapter — HTML scrape (no JSON API).

Cards (.c-products__item) carry title ("pronájem bytu 3+kk 123 m²"), price, and a locality
string ("Truhlářská, Praha 1 - Nové Město, okres Praha"), but NO coordinates — so listings
are geocoded (Mapy) during scoring. See docs/RECON.md.
"""
from __future__ import annotations

import re
import time
from typing import Iterator

from bs4 import BeautifulSoup

from ..http import make_session
from ..normalize import RawListing

SEARCH_URL = "https://reality.idnes.cz/s/pronajem/byty/praha/"

_DISP_RE = re.compile(r"(\d)\s*\+\s*(kk|\d)", re.I)
_AREA_RE = re.compile(r"(\d+)\s*m")
_PRICE_RE = re.compile(r"([\d\s ]+)\s*Kč")
_DISTRICT_RE = re.compile(r"Praha\s*(\d+)")
_CITYPART_RE = re.compile(r"Praha\s*\d+\s*-\s*([^,]+)")


def _text(card, selector):
    el = card.select_one(selector)
    return el.get_text(" ", strip=True) if el else ""


def _parse_card(card) -> RawListing | None:
    link = card.select_one("a.c-products__link") or card.select_one("a[href]")
    if not link or not link.get("href"):
        return None
    href = link["href"]
    source_id = href.rstrip("/").split("/")[-1]
    if not source_id:
        return None

    title = _text(card, ".c-products__title") or link.get_text(" ", strip=True)
    info = _text(card, ".c-products__info")
    price_text = _text(card, ".c-products__price")

    disp = None
    if (m := _DISP_RE.search(title)):
        disp = f"{m.group(1)}+{m.group(2).lower()}"
    area = float(m.group(1)) if (m := _AREA_RE.search(title)) else None
    price = None
    if (m := _PRICE_RE.search(price_text)):
        price = int(re.sub(r"[\s ]", "", m.group(1)))

    street = (info.split(",")[0].strip() or None) if info else None
    district = f"Praha {m.group(1)}" if (m := _DISTRICT_RE.search(info)) else None
    city_part = m.group(1).strip() if (m := _CITYPART_RE.search(info)) else None
    address = ", ".join(x for x in (street, city_part, "Praha") if x) or None

    return RawListing(
        source="idnes",
        source_id=source_id,
        url=href,
        disposition=disp,
        area_m2=area,
        price_czk=price,
        price_per_m2=round(price / area) if price and area else None,
        district=district,
        city_part=city_part,
        street=street,
        address=address,
        latitude=None,            # geocoded during scoring
        longitude=None,
        geo_precision="street",
        is_agency=True,           # iDnes listings are predominantly agency
        premise_name=None,
        charges_czk=None,         # not in the card; all-in estimated
        images=[],
        raw={"title": title, "info": info, "href": href},
    )


def fetch(max_pages: int = 10, *, session=None, delay: float = 0.8) -> Iterator[RawListing]:
    session = session or make_session()
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        url = SEARCH_URL if page == 1 else f"{SEARCH_URL}?page={page}"
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        cards = BeautifulSoup(resp.text, "lxml").select(".c-products__item")
        if not cards:
            break
        fresh = False
        for card in cards:
            rl = _parse_card(card)
            if rl is None or rl.source_id in seen:
                continue
            seen.add(rl.source_id)
            fresh = True
            yield rl
        if not fresh:   # page repeated already-seen ids -> stop (also covers bad ?page param)
            break
        if delay:
            time.sleep(delay)
