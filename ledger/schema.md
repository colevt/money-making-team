# Ledger event contract

Bots append **one JSON object per line** to `ledger/events.jsonl`.
Never include API keys, RSA keys, cookies, or signed order payloads.

A fired ticket is illegal unless this cycle already has a fresh `ingest` and a `score` with `gate_pass: true`. Quiet is the legal stand-down. `python3 tools/append_event.py` enforces this.

## Required on every event

| Field | Type | Notes |
| --- | --- | --- |
| `ts` | string | ISO-8601, America/Denver preferred |
| `cycle_id` | string | Stable per cycle, e.g. `2026-09-02T14:10:00-06:00` |
| `kind` | string | See kinds below |
| `bot` | string | `scorer` or `trader`. (Legacy `news`/`espn`/`crypto` still accepted on old lines.) |

## Kinds

| kind | Who | Extra fields |
| --- | --- | --- |
| `ingest` | scorer | `feeds`: **all eight** keys below. Each `{ ok, lag_s, note }`. `x_news.ok` cannot be true with note `no pull`. `osiris.ok` cannot be true if incomplete. `onchain.ok` cannot be true if no quote. |
| `score` | scorer | One per market×venue. `edge_pct`, `ask`, `bid`, `model_cents`, `book_cents`, `weights`, `gate_pass`, `venue` `kalshi`\|`polymarket_us`\|`onchain`, `market_id`, `market`, `book_kind` `sports`\|`crypto15m`, `feeds_used`, `reason` |
| `quiet` | scorer | `reason`. Omit `market_id` for a cycle stand-down (blocks all tickets). Include `market_id` (+ `venue`) to skip one name only. |
| `ticket` | trader | `venue` `kalshi` \| `polymarket_us` \| `onchain`, `side` YES\|NO or BUY\|SELL, `size_usd`, `entry_cents`, `market_id`, `market`. Must match a passing score for that venue+market. Many tickets per cycle are legal. |
| `post` | trader | `venue`, `market_id`, `confirmed_live` **true**, `under_cap` **true** |
| `fill` | trader | same as ticket plus `ticket_id`. Requires `post` in this cycle. |
| `mark` | trader | `ticket_id`, `mark_cents`, `unrealized_usd` |
| `flatten` | trader | `ticket_id`, `trigger` |
| `settle` | trader | `ticket_id`, `result` `WON` \| `LOST`, `pl_usd`, `settle_cents` |
| `learn` | scorer | Only after settle. Prefer `python3 tools/learn_from_settle.py --cycle_id …`. Fields: `book_kind`, `weight_deltas`, `weights`, `gate_notes`, `gate_pct` (must stay 6). |
| `feed_health` | any | `name`, `state` `ok` \| `warn` \| `bad`, `detail` |
| `heartbeat` | any | `role`, `constraint` (`scoring` \| `execution`). Emit every 5 minutes via `python3 tools/heartbeat.py`. |

## Ingest feeds (required every cycle)

`unusual_whales`, `x_news`, `espn`, `crypto`, `kalshi`, `polymarket_us`, `osiris`, `onchain`.

Stale → `quiet`, never a ticket:

| feed | max `lag_s` |
| --- | --- |
| unusual_whales | 600 |
| x_news | 300 |
| espn (sports only) | 45 |
| crypto | 180 |
| kalshi / polymarket_us | 20 |
| osiris | 90 |
| onchain (1inch) | 20 |

ESPN may be `ok` with note `not used crypto15m` on crypto books. Crypto may sit idle on sports. X must actually pull; `no pull yet` with `ok: true` is rejected. OSIRIS must actually pull (`python3 tools/osiris.py`). Onchain must quote (`python3 tools/oneinch.py`) when the ticket venue is `onchain`; a missing 1inch key does not block Kalshi/Poly.

## Gate rule encoded

Kalshi / Polymarket US: `gate_pass` iff `edge_pct >= 6` **and** `ask < 0.80` **and** that venue’s book is fresh.

Onchain: `gate_pass` iff `edge_pct >= 6` **and** `ask < 1.00` **and** `book_kind=crypto15m` **and** 1inch quoted. `model_cents` is 100 (Kraken/UW fair); `book_cents` is `1inch_price/fair*100`.

`edge_pct` must equal `model_cents - book_cents` (±0.25). `ask` must match `book_cents/100`. Many passing scores per `cycle_id` are legal. A ticket must match one of them by `venue` + `market_id`.

## Two weight books

Do not reuse MLB ESPN weights on KXBTC/KXXRP. Stored in [weights.json](weights.json):

- `sports` — UW flow, X lag, ESPN game state, live book. Crypto weight frozen.
- `crypto15m` — UW OHLC, Kraken, OSIRIS crypto/markets, Kalshi 15m book. ESPN weight frozen.

Only `settle` retunes, via `tools/learn_from_settle.py`: ±0.02 on `feeds_used`, renormalize, gate stays 6% until 60 settled tickets **on that book**.

## Emit from a Grok bot

```bash
python3 tools/append_event.py '{"ts":"...","cycle_id":"...","kind":"quiet","bot":"scorer","reason":"gap under 6%"}'
python3 tools/learn_from_settle.py --cycle_id '...'
python3 tools/heartbeat.py
```

Events stay in this file. Do not POST them to Lovable.
