# Grok cycle (do not skip steps)

One `cycle_id` per scan. Tools reject a ticket if ingest is missing/stale or `model_cents` is absent.

```text
daily_update  once/day  python3 tools/daily_update.py   # skip if already pulled today
heartbeat (every 5 min, even if idle)
    python3 tools/heartbeat.py     # scorer + trader only. no git pull.

ingest     scorer   all six feeds: unusual_whales, x_news, espn, crypto, kalshi, polymarket_us
score      scorer   model_cents, book_cents, edge_pct = model−book, book_kind, feeds_used
           ├─ gate fail or stale  → quiet (reason)  STOP. no learn.
           └─ gate pass
ticket     trader   kalshi | polymarket_us only
post       trader   confirmed_live=true, under_cap=true
fill       trader   ticket_id
mark       trader   every check while open
flatten    trader   only if an exit trigger fires
settle     trader   WON|LOST, pl_usd, settle_cents
learn      scorer   python3 tools/learn_from_settle.py --cycle_id <id>
```

## book_kind

- `sports` — live US sports after the game has started. Train ESPN + X + book. Freeze `crypto`.
- `crypto15m` — Kalshi KXBTC/KXETH/KXXRP 15m vs UW+Kraken OHLC. Train UW + crypto + book. Freeze `espn`.

## Illegal

- Fill without `score.gate_pass=true` on this cycle
- `x_news.ok=true` with note `no pull yet`
- Null `model_cents`
- `learn` on quiet
- Changing the 6% gate
- Kraken live order, Global CLOB, Onchain as a ticket venue, ask ≥ 0.80
- POSTing to Lovable or waiting on an ingest token
- `git pull` on every cycle (use `python3 tools/daily_update.py`, once a day)
