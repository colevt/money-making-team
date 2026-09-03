# Data sources (pull every scan)

Git rules update **once a day**. **Market data does not.** Every 5-minute cycle the Scorer must pull every source below. Quiet if any required feed is stale or X was not actually pulled.

Paste this file into Cursor when asking it to improve the bots. Living jobs: [scorer.md](scorer.md), [CYCLE.md](CYCLE.md). Compact copy: [paste/sources.txt](paste/sources.txt).

Refresh public + desk snapshot: `python3 tools/pull_sources.py`

## Scoring feeds (Scorer, every cycle)

These **seven** keys are **required** on every `ingest` event. Each `{ ok, lag_s, note }`. Use **all** of them in the model — do not score off one feed.

| # | Ingest key | Source | How to pull | What to take | Max lag | Weight key |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `unusual_whales` | Unusual Whales plugin `4021654` | Scorer plugin | 1m + 15m OHLC; pair state; flow / sweeps / unusual size; IBIT + MSTR in US hours; unusual-markets mapped to a **fillable** Kalshi or Polymarket US ticker (skip CLOB ghosts) | 600s (tape >10m → `ok=false`) | `uw` |
| 2 | `x_news` | X plugin `4022021` | Scorer plugin. **Must actually pull.** | `search_news` + recent posts every cycle. Beat writers, injuries, lineups, headline lag vs the book. `ok=true` with note `no pull yet` is rejected. | 300s | `x` |
| 3 | `espn` | ESPN public game state | Public HTTPS, no plugin | Live score, inning/clock, period, started-or-not. Sports only after first pitch/tip/kick. On `crypto15m` still pull, note `not used crypto15m`. | 45s on sports; idle note OK on crypto | `espn` |
| 4 | `crypto` | Kraken plugin `4031115` + UW spots | Kraken **public ticker / OHLC / paper**. Never `-s trade`, never withdraw. | BTC, ETH, SOL, XRP spot vs UW. Overnight and Kalshi 15m: OHLC vs `KXBTC15M` / `KXETH15M` / `KXXRP15M`. | 180s | `crypto` |
| 5 | `kalshi` | Kalshi live book | Scorer reads the book; Trader is the only one who posts | Bid/ask/mark/depth on fillable tickers. Sports + crypto 15m. | 20s | `book` |
| 6 | `polymarket_us` | Polymarket US live book | Scorer reads the book; Trader is the only one who posts | Bid/ask/mark/depth on fillable US tickers. | 20s | `book` |
| 7 | `osiris` | OSIRIS API https://osirisai.live/docs#quickstart | `python3 tools/osiris.py` — no key | **All trade routes:** `/api/stats` `/api/markets` `/api/crypto` `/api/news` `/api/country-risk` `/api/conflicts` `/api/gdelt` `/api/space-weather` `/api/cyber-threats` `/api/weather`. Cross-check spots vs Kraken/UW. News/risk/conflicts sit on the `x` weight. `max_risk >= 7` tied to the market → quiet unless the book already moved. Skip flights/CCTV/sats GeoJSON (not a book). | 90s | `x` |

Do not create extra Bots for #1–4 or #7. One Scorer pulls all of them. A score that ignores OSIRIS, X, or UW is incomplete.

## Desk / cash (read every cycle, not ticket venues)

| Source | How | What | Use |
| --- | --- | --- | --- |
| Live desk API | `GET https://merger-sole-additional-checked.trycloudflare.com/api/desk` | Blotter, cash, feed health, last intake | Cross-check books + runway. Local proxy: `python3 tools/serve_desk.py` → `/api/desk`. |
| Onchain USDC | Polygon RPC, address `0xcE01ddD2141e4efDB929265A538981043b7449BF`, token `0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359` | Native USDC cash. POL is gas, not spendable. | Runway only. **Not** a ticket `venue`. Do not mix into Kalshi/Poly size. |
| This repo ledger | `ledger/events.jsonl`, `ledger/weights.json` | Prior ingest/score/settle, two weight books | `sports` vs `crypto15m`. Do not reuse ESPN sports weights on KXBTC/KXXRP. |

## Hours → which book

| Window | Book kind | Feeds that drive the model | Freeze |
| --- | --- | --- | --- |
| US hours | `sports` | UW flow (IBIT/MSTR), X lag, OSIRIS news/risk, ESPN live game, Kalshi or Poly US book | `crypto` weight |
| Overnight + Kalshi 15m crypto (also daytime 15m) | `crypto15m` | UW OHLC + Kraken + OSIRIS `/api/crypto`+`/api/markets` vs `KXBTC15M` / `KXETH15M` / `KXXRP15M` | `espn` weight |

## Not sources

| Name | Why |
| --- | --- |
| Global CLOB | 403 geo. Not a wallet. No order path. |
| Lovable | Public view of `site/` later. Not ingest. |
| Live Kraken | Scoring/paper only. Never `-s trade`. |
| Onchain as a ticket | Cash wallet, not `venue`. Tickets are Kalshi or Polymarket US only. |
| `POST /api/github-webhook` | Osiris **write** path. Forwards signed GitHub repo events (`x-hub-signature-256`) to Osiris’s own bot URL. Empty `curl -d '{}'` is not market data (401/403/503). Bots must not POST this on a scan. Scoring is `python3 tools/osiris.py` (GETs). |
| OSIRIS RECON / scanner / `/api/ai/*` | Active scan or 5/min AI POSTs. Not a book. |

## Pull vs git

| Action | Cadence | Command |
| --- | --- | --- |
| Rules from Cursor | Once per America/Denver day | `python3 tools/daily_update.py` |
| All sources above | Every 5-minute scan | Scorer: plugins + public pulls. Snapshot: `python3 tools/pull_sources.py` |
| Heartbeat | Every 5 minutes | `python3 tools/heartbeat.py --bot scorer` |

## Ingest example (all seven keys)

```json
{
  "ts": "ISO",
  "cycle_id": "…",
  "kind": "ingest",
  "bot": "scorer",
  "feeds": {
    "unusual_whales": {"ok": true, "lag_s": 12, "note": "BTC 1m/15m · IBIT flow mapped to KXBTC15M"},
    "x_news": {"ok": true, "lag_s": 20, "note": "pulled 4 posts, no XRP headline"},
    "espn": {"ok": true, "lag_s": 4, "note": "not used crypto15m"},
    "crypto": {"ok": true, "lag_s": 2, "note": "XRP Kraken 1.349 vs UW 1.349"},
    "kalshi": {"ok": true, "lag_s": 1, "note": "KXXRP15M YES 72¢"},
    "polymarket_us": {"ok": true, "lag_s": 1, "note": "no twin"},
    "osiris": {"ok": true, "lag_s": 8, "note": "BTC 77300 · VIX 15.2 · news risk 3"}
  }
}
```

X note must show a real pull. ESPN on crypto15m uses the idle note. Crypto on sports may say `idle US hours`.
