# Prague flat-hunt

A scheduled pipeline that scrapes Prague rental portals several times a day, normalizes
and dedupes across sources, scores each flat on commute + value + area, and sends a
Telegram message for top matches (plus a morning/evening digest). A Leaflet map of the
current matches is published to GitHub Pages. State lives in a SQLite DB committed back
to the repo ("git scraping").

**Status:** all six build steps live (3-source ingest, commute/scoring, Telegram alerts,
map dashboard, cloud automation). Spec is at **v2 — flat-share** (see below).

Run the pipeline:
```bash
python run.py ingest          # crawl all 3 sources, store new/changed listings
python run.py score           # hard filters + commute time + 0–1 score
python run.py top -n 15       # show the top-ranked flats
python run.py notify          # Telegram: instant alerts for new high-score flats
python run.py digest          # Telegram: snapshot of current top matches
python run.py map             # regenerate the Leaflet dashboard (docs/index.html)
python run.py stats           # what's in the database
# offline tests (no network/keys needed):
python tests/test_acceptance.py && python tests/test_scoring.py \
  && python tests/test_adapters.py && python tests/test_notify.py \
  && python tests/test_map.py
```

### Automation (cloud)
`.github/workflows/pipeline.yml` runs ingest → score → notify → map and commits the
updated `data/flats.db` + `docs/index.html` back to the repo (durable state). It is
scheduled hourly 07–21 Prague because GitHub throttles cron heavily (observed: only 2–3
of 6 scheduled runs/day actually fire, often hours late) — hourly scheduling lands at
roughly the intended every-2h cadence. `digest.yml` sends a summary at 08:23 / 18:23
Prague. Both need the repo secrets `MAPY_API_KEY`, `GOOGLE_MAPS_API_KEY`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Trigger manually from the Actions tab to test.

## What it optimizes for (spec v2 — flat-share, July 2026)

Hunting **with a flatmate**: one shared flat, rent split two ways.

- Whole flats only · two work anchors: **Zápova 1559/18, Smíchov (P5)** (you) and
  **Rohanské nábřeží 721/39, Karlín (P8)** (flatmate) — the commute term is the
  **average** transit time to both; if one can't be routed, the known one counts alone
- Ceiling **32k CZK all-in for the whole flat** (16k each, tunable) · layouts
  **2+1, 3+1, 3+kk** only (2+kk excluded — one person would sleep in the kitchen room)
- Preferred areas (soft bonus, not a filter): **Vinohrady as a neighbourhood** (it spans
  Praha 2 + Praha 3 — matched via city_part so both sides count), **Praha 6**, **Praha 7**
- Hard filters (layout allow-list, ≤ ceiling all-in) → soft score, each metric normalized
  0–1 then weighted **0.4 commute + 0.3 price/m² + 0.3 area**. Notify ≥ **0.65**.
- **Freshness:** a flat not re-seen by any crawl for 4 days (`STALE_DAYS`) is treated as
  rented/withdrawn and drops out of alerts, digest, top list and map on its own.
- Quiet hours 21:00–08:00 Prague; alert history re-baselines automatically when
  `SPEC_VERSION` is bumped (one fresh summary instead of a flood of stale "new match" pings).
- Sources: **Sreality**, **Bezrealitky**, **iDnes Reality** (one adapter each; a source
  that fails surfaces as "source down today" rather than killing the run).

See [docs/RECON.md](docs/RECON.md) for the live, current access method of each source
(the documented Sreality JSON API is dead — we read its SSR data instead). The v1 spec's
"available from August" filter was never implementable from list pages (portals don't
ship availability there) and is moot now that August is here.

## Build order (all done)

1. **Verification routine** ✅ — prove all dependencies are reachable. `verify.py`.
2. **Sreality adapter + SQLite schema + dedup** ✅ — core loop end-to-end on one source.
3. **Geocode + routing + scoring** ✅ — Google transit commute, hard filters, 0–1 score.
4. **Bezrealitky + iDnes adapters** ✅ — 3-source ingest, cross-source dedup, real all-in.
5. **GitHub Pages Leaflet map** ✅ — score-coloured markers, shortlist/hide, phone layout.
6. **Telegram notifier (instant + digest) + inquiry drafter** ✅ — plus the scheduled
   GitHub Actions pipeline (ingest → score → notify → map → commit state) and a 2×/day digest.

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
