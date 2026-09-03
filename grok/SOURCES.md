# Data sources (pull every scan)

Git rules update **once a day**. **Market data does not.** Every 5-minute cycle the Scorer must pull every source below. Quiet if any required feed is stale or X was not actually pulled.

Paste this file into Cursor when asking it to improve the bots. Living jobs: [scorer.md](scorer.md), [CYCLE.md](CYCLE.md). Compact copy: [paste/sources.txt](paste/sources.txt).

Refresh public + desk snapshot: `python3 tools/pull_sources.py`

## Scoring feeds (Scorer, every cycle)

These **eight** keys are **required** on every `ingest` event. Each `{ ok, lag_s, note }`. Use **all** of them in the model — do not score off one feed. Score **every** fillable market on Kalshi, Polymarket US, and 1inch; one cycle may fire several tickets. Onchain buy-low/sell-high scores come from `python3 tools/scalp.py` (tape + learned weights), not from a guess.

| # | Ingest key | Source | How to pull | What to take | Max lag | Weight key |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `unusual_whales` | Unusual Whales plugin `4021654` | Scorer plugin | 1m + 15m OHLC; pair state; flow / sweeps / unusual size; IBIT + MSTR in US hours; unusual-markets mapped to a **fillable** Kalshi or Polymarket US ticker (skip CLOB ghosts). Also pass `{ETH:{side:buy}}` into `crypto_tape.py --flow`. | 600s (tape >10m → `ok=false`) | `uw` |
| 2 | `x_news` | X plugin `4022021` | Scorer plugin. **Must actually pull.** | `python3 tools/x_tape.py` first (next queries + last delta), then `search_news` + posts, then `python3 tools/x_tape.py --record`. Beat writers, injuries, lineups, headline lag vs the book. `ok=true` with note `no pull yet` is rejected. | 300s | `x` |
| 3 | `espn` | ESPN public game state | Public HTTPS, no plugin | Live score, inning/clock, period, started-or-not. Sports only after first pitch/tip/kick. On `crypto15m` / `crypto_scalp` still pull, note `not used crypto15m`. | 45s on sports; idle note OK on crypto | `espn` |
| 4 | `crypto` | Kraken plugin `4031115` + UW spots | Kraken **public ticker / OHLC / paper**. Never `-s trade`, never withdraw. Also `python3 tools/crypto_tape.py` (1m bars → local high/low/VWAP). | BTC, ETH, SOL, XRP spot vs UW. Overnight and Kalshi 15m: OHLC vs `KXBTC15M` / `KXETH15M` / `KXXRP15M`. Fair for 1inch. Scalp: last vs VWAP vs local high/low. | 180s | `crypto` |
| 5 | `kalshi` | Kalshi live book | Scorer reads the book; Trader posts via `tools/execute.py` | Bid/ask/mark/depth on **all** fillable tickers. | 20s | `book` |
| 6 | `polymarket_us` | Polymarket US live book | Scorer reads the book; Trader posts via `tools/execute.py` | Bid/ask/mark/depth on **all** fillable US tickers. | 20s | `book` |
| 7 | `osiris` | OSIRIS API https://osirisai.live/docs | `python3 tools/osiris.py` — no key. Then read `ledger/osiris_snapshot.json`. | **Every keyless GET feed** (27). Geometry is compacted. Use all of it in the model. `max_risk>=7`, quake mag≥6, jamming, hot infra, cyber CRITICAL tied to a market → skip unless the book moved. | 90s | `x` |
| 8 | `onchain` | 1inch Swap API v6.1 Polygon + DexScreener public | `python3 tools/oneinch.py` (needs `ONEINCH_API_KEY`); `python3 tools/dexscreener.py` for pool liquidity + volume ratio | USDC → WETH/WBTC/SOL quotes vs Kraken/UW **and** vs the crypto tape VWAP. Ingest note includes deepest Polygon pair liquidity (`liquidity.usd`) and `vol6h/h24` ratio per token. Ticket venue for both 6% mispricing (`crypto15m`) and 0.35% scalp (`crypto_scalp`). Wallet `0xcE01ddD2141e4efDB929265A538981043b7449BF`. POL is gas. DexScreener dead → `onchain` still ok if 1inch quoted; scalp liquidity exit/fee-floor degrade gracefully. | 20s | `book` |

Do not create extra Bots for #1–4, #7, or #8. One Scorer pulls all of them. A score that ignores OSIRIS, X, UW, or 1inch (on crypto15m) is incomplete.

## Desk / cash (read every cycle)

| Source | How | What | Use |
| --- | --- | --- | --- |
| Live desk API | `GET https://merger-sole-additional-checked.trycloudflare.com/api/desk` | Blotter, cash, feed health, last intake | Cross-check books + runway. |
| Onchain USDC + 1inch | Wallet `0xcE01…49BF`, token `0x3c499c…3359`, `python3 tools/oneinch.py` | Native USDC **and** swap quotes. POL is gas. | Ticket venue `onchain` via 1inch. Do not mix this USDC into Kalshi/Poly size. |
| This repo ledger | `ledger/events.jsonl`, `ledger/weights.json`, `ledger/crypto_tape.json`, `ledger/learn_tape.jsonl` | Prior ingest/score/settle, three weight books, scalp params, feature tape | `sports` vs `crypto15m` vs `crypto_scalp`. Learn after every settle. |

## Hours → which book

| Window | Book kind | Feeds that drive the model | Freeze |
| --- | --- | --- | --- |
| US hours | `sports` | UW flow (IBIT/MSTR), X lag, OSIRIS news/risk, ESPN live game, Kalshi or Poly US book | `crypto` weight |
| Overnight + Kalshi 15m crypto (also daytime 15m) | `crypto15m` | UW OHLC + Kraken + OSIRIS `/api/crypto`+`/api/markets` vs `KXBTC15M` / `KXETH15M` / `KXXRP15M` **and** 1inch USDC→WETH/WBTC/SOL | `espn` weight |
| Every scan, day or night | `crypto_scalp` | Crypto tape (local high/low/VWAP) + 1inch + DexScreener liquidity/volume + UW flow + X acceleration. `python3 tools/scalp.py`. Buy dip, sell high, many $1 round-trips. Exit on take/stop **or** volume decay (`h6/(h24/4) < 0.20`). | `espn` weight |

## Not sources

| Name | Why |
| --- | --- |
| Global CLOB | 403 geo. Not a wallet. No order path. |
| Lovable | Public view of `site/` later. Not ingest. |
| Live Kraken | Scoring/paper only. Never `-s trade`. |
| Onchain as cash-only | Stale rule. Onchain is a 1inch ticket venue now. POL is still gas, not spendable. |
| `POST /api/github-webhook` | Osiris **write** path. Forwards signed GitHub repo events (`x-hub-signature-256`) to Osiris’s own bot URL. Empty `curl -d '{}'` is not market data (401/403/503). Bots must not POST this on a scan. Scoring is `python3 tools/osiris.py` (GETs). |
| OSIRIS RECON / scanner / `/api/osint/sweep` / `/api/ai/*` | Active scan or 5/min AI POSTs. Lookups (`/api/osint/*`) need a subject — not a 5-minute feed. |

## Pull vs git

| Action | Cadence | Command |
| --- | --- | --- |
| Rules from Cursor | Once per America/Denver day | `python3 tools/daily_update.py` |
| All sources above | Every 5-minute scan | Scorer: plugins + public pulls. Snapshot: `python3 tools/pull_sources.py`. Tape: `python3 tools/crypto_tape.py`. Dex: `python3 tools/dexscreener.py`. Scalp scores: `python3 tools/scalp.py --cycle_id … --append` |
| Heartbeat | Every 5 minutes | `python3 tools/heartbeat.py --bot scorer` |

## Ingest example (all eight keys)

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
    "osiris": {"ok": true, "lag_s": 8, "note": "BTC 77300 · VIX 15.2 · news risk 3"},
    "onchain": {"ok": true, "lag_s": 8, "note": "WETH 2389 vs 2389 edge +0.0 · ETH liq $2,278,493 vol6h/h24 1.88"}
  }
}
```

X note must show a real pull. ESPN on crypto15m uses the idle note. Crypto on sports may say `idle US hours`.
