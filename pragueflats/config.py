"""Locked search parameters and paths — single place to tune the hunt.

Spec v2 (July 2026): hunting WITH A FLATMATE — a shared 2+1 / 3+1 / 3+kk, rent split
two ways, preferred areas Vinohrady (both its Praha 2 and Praha 3 parts), Praha 6 and
Praha 7. Bump SPEC_VERSION whenever filters change meaningfully: it triggers a one-time
alert re-baseline so the Telegram channel starts fresh under the new rules.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "flats.db"

SPEC_VERSION = "v2-flatshare"

# Work location — Mapy.com geocode of Zápova 1559/18, Praha 5 (confirmed in step 1).
# Commute is scored against this address only for now; the flatmate's commute can be
# added later as a second anchor (average of the two).
WORK_ADDRESS = "Zapova 1559/18, Praha 5"
WORK_LAT, WORK_LON = 50.0744, 14.3906

# Total all-in ceiling for the WHOLE flat (both rents + charges), i.e. 16k each.
MAX_PRICE_ALLIN_CZK = 32_000

# Layouts that work for two flatmates: a private room each. 2+kk is excluded (one of
# you would sleep in the kitchen/living room). Compared lowercase.
ALLOWED_DISPOSITIONS = {"2+1", "3+1", "3+kk"}

# Preferred areas (soft bonus, not a hard filter — the rest of Prague stays visible,
# just ranked lower). Vinohrady is matched as a NEIGHBOURHOOD (city_part), because the
# cadastral area spans Praha 2 + Praha 3; matching the district would miss most of it.
PREFERRED_CITY_PARTS = {"Vinohrady"}
PREFERRED_DISTRICTS = {"Praha 6", "Praha 7"}

# A listing not re-seen by any crawl for this many days is treated as gone (rented /
# withdrawn) and drops out of the top list, digest, map and alerts. It comes back by
# itself if a crawl sees it again.
STALE_DAYS = 4

# Sreality crawl depth. ~20 listings/page, default sort is newest-first, and Sreality's
# pagination loops near ~100 pages on broad filters — so we take the newest slice and
# stay polite. Raise if you want deeper history.
SREALITY_MAX_PAGES = 25

# Score above which a flat is "notify-worthy" (instant Telegram alert). Calibrated for
# the v2 weights (0.4 commute / 0.3 price / 0.3 area); revisit after a few cloud runs.
NOTIFY_THRESHOLD = 0.65

# Quiet hours (Prague local): no instant pings when hour >= START or hour < END.
# A flat found during quiet hours isn't dropped — it pings at the next waking run.
QUIET_START_HOUR = 21   # 21:00 (9pm) — evening postings are common, alert same day
QUIET_END_HOUR = 8      # 08:00 (8am)

# Public URL of the hosted Leaflet map (GitHub Pages). When set, the Telegram digest
# carries a tap-to-open "Open map" button. Empty string = no button.
MAP_URL = "https://hubertotevrel.github.io/prague-flats/"
