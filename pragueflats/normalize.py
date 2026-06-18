"""The canonical listing record every portal adapter produces, plus the dedup key."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class RawListing:
    """One flat as seen on one portal, normalized to a common shape."""
    source: str                 # "sreality" | "bezrealitky" | "idnes"
    source_id: str              # the portal's own stable id for this listing
    url: str
    disposition: str | None     # e.g. "1+kk", "2+1"
    area_m2: float | None
    price_czk: int | None       # advertised base rent (all-in estimation happens in step 3)
    price_per_m2: float | None
    district: str | None        # e.g. "Praha 7"
    city_part: str | None       # e.g. "Holešovice"
    street: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    geo_precision: str | None   # "address" | "street" | ... -> drives the confidence band
    is_agency: bool
    premise_name: str | None
    images: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def _slug(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def dedup_key(rl: RawListing) -> str:
    """Stable cross-source identity for a flat.

    Deliberately PRICE-INDEPENDENT: a price drop must not change a flat's identity, or
    we'd lose price-drop tracking entirely. Cross-source merging in step 4 adds a
    photo-hash tie-breaker; for now geo + area + layout is enough, and within a single
    source the portal's own id (sources.source_id) is the authoritative identity anyway.
    """
    geo = _slug(rl.street)
    if not geo and rl.latitude is not None and rl.longitude is not None:
        geo = f"{rl.latitude:.3f},{rl.longitude:.3f}"  # ~100 m bucket
    area = str(round(rl.area_m2)) if rl.area_m2 else "?"
    return f"{_slug(rl.district)}|{geo}|{area}|{_slug(rl.disposition)}"
