# Prague flat-hunt

A scheduled pipeline that scrapes Prague rental portals every ~2h during the active
window, normalizes and dedupes across sources, scores each flat on commute + value, and
sends a Telegram message for top matches (plus a morning/evening digest). A Leaflet map
of the shortlist is published to GitHub Pages. State lives in a SQLite DB committed back
to the repo ("git scraping").

**Status:** Steps 1–2 built (verification + Sreality ingest engine). Steps 3–6 pending.

Run the pipeline:
```bash
python run.py ingest          # crawl Sreality, store new/changed listings
python run.py stats           # what's in the database
python tests/test_acceptance.py   # idempotency + price-change acceptance test
```

## What it optimizes for (locked spec)

- Whole flats only · move-in **August 2026** · work = **Zápova 1559/18, Smíchov (P5)**
- Default ceiling **18k CZK all-in** (tunable) · **1+kk and up** · soft bonus for P7 + P5/P4/P8/Žižkov
- Hard filters (≤ ceiling all-in, available Aug, 1+kk+) → soft score, each metric
  normalized 0–1 then weighted **0.5 commute + 0.3 price/m² + 0.2 district**. Notify ≥ **0.75**.
- Sources: **Sreality**, **Bezrealitky**, **iDnes Reality** (one adapter each; a source
  that fails surfaces as "source down today" rather than killing the run).

See [docs/RECON.md](docs/RECON.md) for the live, current access method of each source
(the spec's assumed Sreality JSON API is dead — we read its SSR data instead).

## Build order

1. **Verification routine** ✅ — prove all dependencies are reachable. `verify.py`.
2. **Sreality adapter + SQLite schema + dedup** ✅ — core loop end-to-end on one source.
3. Geocode + routing + scoring.
4. Bezrealitky + iDnes adapters.
5. GitHub Pages Leaflet map + shortlist tracker.
6. Telegram notifier (instant + digest) + inquiry-message drafter.

## Step 1 — run the verification routine

The portal checks need no secrets and run immediately. Mapy.com and Telegram are skipped
until their secrets are set.

```bash
pip install -r requirements.txt
python verify.py
```

Expected (before secrets): Sreality / Bezrealitky / iDnes `[OK]`, Mapy + Telegram `[--]`.

### Provide the secrets

1. **Mapy.com key** — sign up at https://developer.mapy.com, create an API project + key
   (free Basic plan, 250k credits/mo).
2. **Telegram bot** — message @BotFather → `/newbot` → copy the token.
3. **Telegram chat id** — set the token in `.env`, message your new bot once from your
   phone, then:
   ```bash
   cp .env.example .env      # paste MAPY_API_KEY + TELEGRAM_BOT_TOKEN
   python verify.py --telegram-chatid   # prints your chat id → paste into .env
   python verify.py          # now all five checks should be [OK]
   ```

### Run it on GitHub Actions (the real test)

A local green run proves the *code* works; the point of step 1 is proving it works **from
a GitHub runner**, whose datacenter IPs the portals may treat differently than your home
IP. So:

1. Create a repo and push this project (`gh repo create` or via github.com).
2. Add three **repository secrets** (Settings → Secrets and variables → Actions):
   `MAPY_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
3. Actions tab → **verify** → *Run workflow*. Green = step 1 done; you should also get
   the Telegram test message on your phone.

If a portal that's green locally fails on Actions, that's the IP-reputation risk
materializing — noted as a known risk; the fallback is a different runner/proxy or
running the pipeline from a small always-on box instead.

`gh` is not currently installed locally (`brew install gh` if you want the CLI route).
