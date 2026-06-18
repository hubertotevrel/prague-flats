"""Locked search parameters and paths. Hard filters + scoring get wired in step 3;
they live here now so there's a single place to tune them."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "flats.db"

# Work location — Mapy.com geocode of Zápova 1559/18, Praha 5 (confirmed in step 1).
WORK_ADDRESS = "Zápova 1559/18, Praha 5"
WORK_LAT, WORK_LON = 50.0744, 14.3906

# Tunable default rent ceiling (all-in). Used by the hard filter in step 3.
MAX_PRICE_ALLIN_CZK = 18_000

# Soft district preference (bonus weights for scoring in step 3). Prague 7 preferred,
# then the commute-friendly / better-value comparables.
PREFERRED_DISTRICTS = {
    "Praha 7": 1.0,
    "Praha 5": 0.7,
    "Praha 4": 0.6,
    "Praha 8": 0.6,
    "Praha 3": 0.6,  # Žižkov
}

# Sreality crawl depth. ~20 listings/page, default sort is newest-first, and Sreality's
# pagination loops near ~100 pages on broad filters — so we take the newest slice and
# stay polite. Raise if you want deeper history.
SREALITY_MAX_PAGES = 25

# Score above which a flat is "notify-worthy" (instant alert in step 6). Tunable.
NOTIFY_THRESHOLD = 0.75
