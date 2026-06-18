"""Hard filters and the 0–1 soft score.

Hard filters decide in/out. Soft score ranks the survivors:
    score = 0.5 * commute + 0.3 * price_per_m² + 0.2 * district
each term normalized to 0–1 against fixed (tunable) bounds, so a flat's score is stable
across runs rather than drifting as the candidate set changes.
"""
from __future__ import annotations

from . import config

# --- tunable normalization bounds ---
COMMUTE_MAX_MIN = 60      # >= this transit time scores 0; 0 min scores 1
PPM_BEST_CZK = 300.0      # CZK/m² at or below -> 1.0
PPM_WORST_CZK = 900.0     # CZK/m² at or above -> 0.0
# All-in estimate when the listing only shows base rent (service charges + utilities live
# on the detail page). Flagged as estimated so we never silently reject on a guess.
ALLIN_MIN_EXTRA_CZK = 2_500
ALLIN_PER_M2_CZK = 90

WEIGHTS = {"commute": 0.5, "price_per_m2": 0.3, "district": 0.2}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def all_in_cost(base_price: int | None, area_m2: float | None,
                charges: int | None = None) -> tuple[int | None, bool]:
    """Returns (all_in_czk, is_estimated). When the source gives real charges (Bezrealitky)
    the all-in is exact and flagged False; otherwise we estimate from area and flag True."""
    if base_price is None:
        return None, False
    if charges is not None:
        return base_price + charges, False
    extra = max(ALLIN_MIN_EXTRA_CZK, round((area_m2 or 30) * ALLIN_PER_M2_CZK))
    return base_price + extra, True


def passes_hard_filters(disposition, base_price, all_in, estimated, *, ceiling=None) -> bool:
    ceiling = ceiling or config.MAX_PRICE_ALLIN_CZK
    if not disposition:               # need a known layout (1+kk and up — all flats qualify)
        return False
    # Never reject on a *guessed* all-in: judge on the real base rent when all-in is
    # estimated, on the real all-in once we have it.
    effective = base_price if estimated else (all_in if all_in is not None else base_price)
    if effective is None or effective > ceiling:
        return False
    return True


def commute_score(minutes: int | None) -> float:
    if minutes is None:
        return 0.0
    return _clamp01(1 - minutes / COMMUTE_MAX_MIN)


def price_per_m2_score(ppm: float | None) -> float:
    if not ppm:
        return 0.0
    return _clamp01((PPM_WORST_CZK - ppm) / (PPM_WORST_CZK - PPM_BEST_CZK))


def district_score(district: str | None) -> float:
    return config.PREFERRED_DISTRICTS.get(district, 0.0)


def score(minutes: int | None, ppm: float | None, district: str | None) -> tuple[float, dict]:
    commute = commute_score(minutes)
    if district in config.COMMUTE_RELAXED_DISTRICTS:
        # You don't mind the trip from here, so distance can't drag the score down.
        commute = max(commute, config.RELAXED_COMMUTE_FLOOR)
    parts = {
        "commute": commute,
        "price_per_m2": price_per_m2_score(ppm),
        "district": district_score(district),
    }
    total = sum(WEIGHTS[k] * v for k, v in parts.items())
    breakdown = {k: round(v, 3) for k, v in parts.items()}
    breakdown.update(minutes=minutes, ppm=round(ppm, 1) if ppm else None)
    return round(total, 4), breakdown
