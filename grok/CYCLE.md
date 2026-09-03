# Grok cycle (do not skip steps)

One `cycle_id` per scan. **Many tickets per cycle are legal** — one `score` per market×venue, then fill all that pass.

```text
daily_update  once/day  python3 tools/daily_update.py
heartbeat (every 5 min)
    python3 tools/heartbeat.py

ingest     scorer   eight feeds: unusual_whales, x_news, espn, crypto,
                    kalshi, polymarket_us, osiris, onchain
                    osiris: python3 tools/osiris.py   # all 27 GET feeds → ledger/osiris_snapshot.json
                    onchain: python3 tools/oneinch.py
score      scorer   ONE score per fillable market×venue (kalshi, polymarket_us, onchain)
           ├─ none pass  → cycle quiet (no market_id)  STOP. no learn.
           └─ any pass   → keep going; optional per-market quiet for the rest
ticket…    trader   python3 tools/execute.py --cycle_id <id>
                    then --live --append when keys are in .env
                    kalshi + polymarket_us + onchain in the same cycle
mark       trader   every open ticket
flatten    trader   per ticket if an exit trigger fires
settle     trader   per ticket WON|LOST
learn      scorer   python3 tools/learn_from_settle.py --cycle_id <id> --ticket_id <id>
```

## book_kind

- `sports` — live US sports after the game has started. Venues: kalshi, polymarket_us. Not onchain.
- `crypto15m` — Kalshi/Poly 15m **and** 1inch USDC→WETH/WBTC/SOL vs UW+Kraken+OSIRIS. Freeze `espn`.

## Illegal

- Filling only the first passing score when others also passed
- Fill without a matching `score.gate_pass` for that venue + `market_id`
- `x_news.ok=true` with note `no pull yet`
- Skipping OSIRIS or 1inch (`python3 tools/osiris.py`, `python3 tools/oneinch.py`)
- POSTing `https://osirisai.live/api/github-webhook`
- Null `model_cents`
- `learn` on a cycle with no settle
- Changing the 6% gate
- Kraken live order, Global CLOB
- Onchain `book_kind=sports`
- POSTing to Lovable
- `git pull` on every cycle
