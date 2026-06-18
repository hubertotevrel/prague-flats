# Source recon (as of 2026-06-18)

Live findings from probing each source. The spec assumed a couple of endpoints that
turned out to be stale, so this is the corrected map. Re-verify if a source breaks —
`verify.py` is the canary.

## Sreality  ✅ (method changed vs. spec)

- **The documented public JSON API `/api/cs/v2/estates` is GONE** — returns a genuine
  nginx `404` (not a bot block; headers/cookies don't change it). `/api/v1/estates`
  exists but returns `401`. The old endpoint that every community scraper references no
  longer works.
- **What works now:** the site is a Next.js app. The search page
  `https://www.sreality.cz/hledani/pronajem/byty/praha?strana=N` server-renders the
  results into a `<script id="__NEXT_DATA__">` blob. Path to the data:
  `props.pageProps.dehydratedState.queries[] -> queryKey[0] == "estatesSearch" ->
  state.data.{results, pagination}`.
- Default sort is `-date` (**newest first** — ideal for "new since last run").
  Pagination via `?strana=N` works (page 1 vs 2 had zero ID overlap). ~22 listings/page,
  ~4,477 Prague rentals total. Watch for the known ~100-page loop on broad filters
  (detect by repeated first-id).
- **This payload is richer than the old API.** Per-listing fields:
  - `id` — stable listing id → dedup key + "new" detection within Sreality
  - `categorySubCb.name` — disposition, e.g. `"1+kk"` → the layout hard filter, directly
  - `priceCzk`, `priceCzkPerSqM` → **m² is derivable** (`priceCzk / priceCzkPerSqM`)
  - `priceSummaryCzk`, `priceUnitCb.name` (`"za měsíc"`)
  - `locality.{latitude, longitude}` — **GPS included, so no geocoding needed for Sreality**;
    `locality.{district, districtSeoName, cityPart, street, zip}`; `inaccuracyType`
    ("street"/"address") signals geo precision → drives the confidence band
  - `premiseId` + `premise` present ⇒ **agency**; absent ⇒ private. (Note: `premise.citySeoName`
    is the *agency's* city, not the flat's — use `locality` for the flat.)
  - `images[].url` (protocol-relative `//d18-a.sdn.cz/...`)
  - `name` e.g. `"Pronájem bytu 1+kk 30 m²"` (also carries m²)
- All-in cost: the list view shows base rent; service charges/utilities live on the
  detail page → fetch detail for shortlisted/high-score items, else estimate + flag.

## Bezrealitky  ✅ (better than expected)

- **Live public GraphQL API at `https://api.bezrealitky.cz/graphql/`** (POST). 91 root
  queries. Relevant: `listAdverts` (search), `advert` (detail), `advertMarkers` (map
  pins w/ GPS), `listSimilarAdverts`, `advertFilterOptions`, `listRegions`.
- Direct-from-landlord (no agency commission), so a strong source for "real cost".
- Exact `listAdverts` argument/field shape to be nailed down in step 4 (use introspection
  on the `listAdverts` field + `advertFilterOptions` for region enum values).

## iDnes Reality  ✅ (HTML, use requests)

- `https://reality.idnes.cz/s/pronajem/byty/praha/` returns 200, full page ~174 KB.
- **Connection quirk:** stdlib `urllib` gets intermittent `ConnectionReset` (1/3 success)
  and partial bodies; `curl` and `requests` are 5/5 with full bodies. → the pipeline uses
  `requests` (Session + urllib3 Retry). HTML parsing via BeautifulSoup in step 4.

## Mapy.com  ⏳ (needs key)

- REST API at `https://api.mapy.com/v1/` — `geocode` and `routing/route`. Key via
  https://developer.mapy.com; free Basic plan = 250k credits/mo (ample). Docs:
  `https://api.mapy.com/v1/docs/`.
- Geocoding mostly a fallback (Sreality already has GPS); routing gives door-to-door
  commute time to Zápova at morning peak. `verify.py` confirms the geocode response shape
  the moment the key is added.

## Telegram  ⏳ (needs token + chat id)

- Standard Bot API. Token from @BotFather; get your chat id with
  `python verify.py --telegram-chatid` after messaging the bot once.

## HTTP foundation

`requests.Session` with a browser User-Agent + `urllib3 Retry` (total=4, backoff 0.6,
retry on 429/5xx and connection resets). Reused by `verify.py` and all adapters. Keep
request rates polite and low-profile (personal use).
