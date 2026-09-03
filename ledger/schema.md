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
| `ingest` | scorer | `feeds`: **all six** keys below. Each `{ ok, lag_s, note }`. `x_news.ok` cannot be true with note `no pull`. |
| `score` | scorer | `edge_pct`, `ask`, `bid`, `model_cents`, `book_cents`, `weights`, `gate_pass`, `venue`, `market_id`, `market`, `book_kind` `sports`\|`crypto15m`, `feeds_used` (`uw`\|`x`\|`espn`\|`crypto`\|`book`), `reason` |
| `quiet` | scorer | `reason` (why the 6% / ask / venue / stale / kill switch failed) |
| `ticket` | trader | `venue` `kalshi` \| `polymarket_us`, `side`, `size_usd`, `entry_cents`, `market_id`, `market`. Refused if this cycle is quiet or `gate_pass` is not true. |
| `post` | trader | `venue`, `market_id`, `confirmed_live` **true**, `under_cap` **true** |
| `fill` | trader | same as ticket plus `ticket_id`. Requires `post` in this cycle. |
| `mark` | trader | `ticket_id`, `mark_cents`, `unrealized_usd` |
| `flatten` | trader | `ticket_id`, `trigger` |
| `settle` | trader | `ticket_id`, `result` `WON` \| `LOST`, `pl_usd`, `settle_cents` |
| `learn` | scorer | Only after settle. Prefer `python3 tools/learn_from_settle.py --cycle_id …`. Fields: `book_kind`, `weight_deltas`, `weights`, `gate_notes`, `gate_pct` (must stay 6). |
| `feed_health` | any | `name`, `state` `ok` \| `warn` \| `bad`, `detail` |
| `heartbeat` | any | `role`, `constraint` (`scoring` \| `execution`). Emit every 5 minutes via `python3 tools/heartbeat.py`. |

## Ingest feeds (required every cycle)

`unusual_whales`, `x_news`, `espn`, `crypto`, `kalshi`, `polymarket_us`.

Stale → `quiet`, never a ticket:

| feed | max `lag_s` |
| --- | --- |
| unusual_whales | 600 |
| x_news | 300 |
| espn (sports only) | 45 |
| crypto | 180 |
| kalshi / polymarket_us | 20 |

ESPN may be `ok` with note `not used crypto15m` on crypto books. Crypto may sit idle on sports. X must actually pull; `no pull yet` with `ok: true` is rejected.

## Gate rule encoded

`gate_pass` is true **iff** `edge_pct >= 6` **and** `ask < 0.80` **and** venue is `kalshi` or `polymarket_us` **and** this cycle’s ingest is fresh.

`edge_pct` must equal `model_cents - book_cents` (±0.25). `ask` must match `book_cents/100`. `model_cents` is required — a null model is not a score.

Onchain USDC is cash on the desk, not a ticket `venue`.

## Two weight books

Do not reuse MLB ESPN weights on KXBTC/KXXRP. Stored in [weights.json](weights.json):

- `sports` — UW flow, X lag, ESPN game state, live book. Crypto weight frozen.
- `crypto15m` — UW OHLC, Kraken, Kalshi 15m book. ESPN weight frozen.

Only `settle` retunes, via `tools/learn_from_settle.py`: ±0.02 on `feeds_used`, renormalize, gate stays 6% until 60 settled tickets **on that book**.

## Emit from a Grok bot

```bash
python3 tools/append_event.py '{"ts":"...","cycle_id":"...","kind":"quiet","bot":"scorer","reason":"gap under 6%"}'
python3 tools/learn_from_settle.py --cycle_id '...'
python3 tools/heartbeat.py
```

Events stay in this file. Do not POST them to Lovable.
