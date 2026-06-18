#!/usr/bin/env python3
"""
Prague flat-hunt — Step 1 verification routine.

Confirms the pipeline's external dependencies are reachable *from wherever this runs*
(your Mac now, GitHub Actions later). The whole project rests on these, so we prove
them before building anything on top.

  1. Sreality      — search page loads and its embedded __NEXT_DATA__ yields listings
  2. Bezrealitky   — GraphQL API answers and still exposes the listAdverts query
  3. iDnes Reality — search page loads
  4. Mapy.com      — geocode call succeeds        (skipped unless MAPY_API_KEY set)
  5. Telegram      — test message delivered        (skipped unless TELEGRAM_* set)

Exit code 0 only if every *enabled* check passes; checks whose secret is missing are
SKIPPED and never fail the run.

Usage:
  python verify.py                     # run the checklist
  python verify.py --telegram-chatid   # print chat ids your bot can currently see
"""
import json
import os
import sys

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover - urllib3 always ships with requests
    Retry = None

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT = 30

# Some portals (notably iDnes) intermittently reset bare connections, so every request
# goes through a session with transparent retries + backoff. This is also the HTTP
# foundation the real adapters reuse.
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": UA,
    "Accept-Language": "cs,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})
if Retry is not None:
    _retry = Retry(total=4, backoff_factor=0.6,
                   status_forcelist=[429, 500, 502, 503, 504],
                   allowed_methods=["GET", "POST"])
    _SESSION.mount("https://", HTTPAdapter(max_retries=_retry))


def _load_dotenv(path=".env"):
    """Minimal .env loader for local runs. On GitHub these come from repo secrets."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


# --- Each check returns (ok, detail). ok is True/False, or None to mean "skipped". ---

def check_sreality():
    """The documented /api/cs/v2/estates endpoint is dead (nginx 404). The live data is
    server-rendered into the search page's __NEXT_DATA__ React Query cache, which is
    actually richer (GPS, disposition, price/m2, district, agency flag all included)."""
    url = "https://www.sreality.cz/hledani/pronajem/byty/praha?strana=1"
    r = _SESSION.get(url, timeout=TIMEOUT)
    marker = '<script id="__NEXT_DATA__" type="application/json">'
    if marker not in r.text:
        return False, f"HTTP {r.status_code} but __NEXT_DATA__ missing (page changed)"
    blob = r.text.split(marker, 1)[1].split("</script>", 1)[0]
    data = json.loads(blob)
    queries = data["props"]["pageProps"]["dehydratedState"]["queries"]
    es = next(q for q in queries if q["queryKey"][0] == "estatesSearch")
    payload = es["state"]["data"]
    n = len(payload["results"])
    total = payload["pagination"]["total"]
    return n > 0, f"HTTP {r.status_code}, {n} listings on page 1, {total} Prague rentals total"


def check_bezrealitky():
    """Public GraphQL API. listAdverts = search, advert = detail, advertMarkers = map pins."""
    r = _SESSION.post("https://api.bezrealitky.cz/graphql/",
                      json={"query": "{ __schema { queryType { fields { name } } } }"},
                      timeout=TIMEOUT)
    fields = {f["name"] for f in r.json()["data"]["__schema"]["queryType"]["fields"]}
    have = "listAdverts" in fields
    return have, f"HTTP {r.status_code}, GraphQL up, listAdverts={'yes' if have else 'MISSING'}"


def check_idnes():
    """HTML scrape target. Reachability + a sanity marker that it's the listings page."""
    r = _SESSION.get("https://reality.idnes.cz/s/pronajem/byty/praha/", timeout=TIMEOUT)
    low = r.text.lower()
    ok = r.status_code == 200 and ("pronájem" in low or "byt" in low)
    return ok, f"HTTP {r.status_code}, {len(r.content)} bytes"


def check_mapy():
    """Geocoding (and later routing) for listings without coordinates. Sreality ships GPS,
    so this mainly serves Bezrealitky/iDnes fallbacks and door-to-door commute routing.
    Response shape (items[].position.{lon,lat}) per api.mapy.com/v1/docs."""
    key = os.environ.get("MAPY_API_KEY")
    if not key:
        return None, "MAPY_API_KEY not set"
    r = _SESSION.get("https://api.mapy.com/v1/geocode", timeout=TIMEOUT, params={
        "query": "Zápova 1559/18, Praha", "apikey": key, "limit": 1, "lang": "cs",
    })
    items = r.json().get("items", [])
    if not items:
        return False, f"HTTP {r.status_code} but no geocode result for the work address"
    pos = items[0].get("position", {})
    return True, f"HTTP {r.status_code}, Zápova 18 -> lat {pos.get('lat')}, lon {pos.get('lon')}"


def check_telegram():
    """Deliver one real message to confirm the bot token + chat id land on your phone."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return None, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"
    text = "✅ Prague flat-hunt: verification routine reached your phone via Telegram."
    r = _SESSION.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text}, timeout=TIMEOUT)
    ok = bool(r.json().get("ok"))
    return ok, f"HTTP {r.status_code}, ok={ok}"


def telegram_chatid():
    """One-off helper: after you message the bot once, this prints your chat id."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN first (in .env or the environment).")
        return 2
    r = _SESSION.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=TIMEOUT)
    seen = {}
    for upd in r.json().get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat", {})
        if chat.get("id") is not None and chat["id"] not in seen:
            seen[chat["id"]] = chat
    if not seen:
        print("No chats yet — open Telegram, send your bot any message, then re-run this.")
        return 1
    for cid, chat in seen.items():
        label = chat.get("title") or chat.get("first_name") or chat.get("username") or "?"
        print(f"chat_id={cid}  type={chat.get('type')}  ({label})")
    return 0


CHECKS = [
    ("Sreality", check_sreality),
    ("Bezrealitky", check_bezrealitky),
    ("iDnes Reality", check_idnes),
    ("Mapy.com geocode", check_mapy),
    ("Telegram", check_telegram),
]


def run():
    print("Prague flat-hunt — verification routine")
    print("=" * 52)
    results = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 - report any failure as a failed check
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((name, ok, detail))
        icon = "[OK]" if ok else ("[--]" if ok is None else "[XX]")
        print(f"{icon} {name:<18} {detail}")
    print("=" * 52)

    enabled = [r for r in results if r[1] is not None]
    failed = [r for r in enabled if not r[1]]
    skipped = [r for r in results if r[1] is None]
    passed = len(enabled) - len(failed)
    summary = f"{passed}/{len(enabled)} enabled checks passed"
    if skipped:
        summary += f", {len(skipped)} skipped (secret not set yet)"
    print(summary)
    if failed:
        print("FAIL: " + ", ".join(n for n, _, _ in failed))
    elif not skipped:
        print("ALL GREEN — every dependency reachable.")
    else:
        print("All reachable so far. Add the missing secrets to light up skipped checks.")
    return 1 if failed else 0


if __name__ == "__main__":
    _load_dotenv()
    if "--telegram-chatid" in sys.argv:
        sys.exit(telegram_chatid())
    sys.exit(run())
