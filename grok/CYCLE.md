# Grok cycle (do not skip steps)

One `cycle_id` per scan. **Many tickets per cycle are legal** — one `score` per market×venue, then fill all that pass. Onchain scalps are extra scores on the same cycle: buy the local low, sell the local high, small size, round-trip, then the model learns from that P&L.

```text
daily_update  once/day  python3 tools/daily_update.py
heartbeat (every 5 min)
    python3 tools/heartbeat.py

ingest     scorer   eight feeds: unusual_whales, x_news, espn, crypto,
                    kalshi, polymarket_us, osiris, onchain
                    osiris: python3 tools/osiris.py
                    onchain: python3 tools/oneinch.py
                    tape:   python3 tools/crypto_tape.py
                    x:      python3 tools/x_tape.py          # then search_news + --record
score      scorer   ONE score per fillable Kalshi / Polymarket US / 1inch-fair market
                    PLUS python3 tools/scalp.py --cycle_id <id> --append
                    (buy-low / sell-high from tape + learned weights — do not invent these)
           ├─ none pass  → cycle quiet (no market_id)  STOP. no learn.
           └─ any pass   → keep going; optional per-market quiet for the rest
ticket…    trader   python3 tools/execute.py --cycle_id <id>
                    then --live --append when keys are in .env
                    kalshi + polymarket_us + onchain BUY and SELL in the same cycle
mark       trader   every open ticket
flatten    trader   per ticket if an exit trigger fires (scalp SELL is the exit)
settle     trader   per ticket WON|LOST  (scalp: WON if pl_usd > 0)
learn      scorer   python3 tools/learn_from_settle.py --cycle_id <id> --ticket_id <id>
                    retunes that book AND (for crypto_scalp) dip/take/stop
```

## book_kind

- `sports` — live US sports after the game has started. Venues: kalshi, polymarket_us. Not onchain.
- `crypto15m` — Kalshi/Poly 15m **and** 1inch USDC→WETH/WBTC/SOL vs UW+Kraken+OSIRIS when 1inch is ≥6% cheap vs fair. Freeze `espn`.
- `crypto_scalp` — onchain only. Buy ETH/BTC/SOL at a local low / VWAP dip; sell the same lot at a local high, take (~0.40%), or stop (~0.45%). Gate is **0.35%**, not 6%. Scores **must** come from `tools/scalp.py` / `compose_score.py` so weights actually drive the next ticket. Freeze `espn`.

## Self-learn

The model is the weights + scalp params in `ledger/weights.json` plus the feature tape in `ledger/learn_tape.jsonl`. Do not eyeball a scalp `model_cents`. After every settle the next `scalp.py` uses the new weights. Quiet with no settle does not learn.

## Illegal

- Filling only the first passing score when others also passed
- Inventing crypto_scalp scores instead of `python3 tools/scalp.py --append`
- Holding a scalp lot across a local high / take without emitting SELL
- Fill without a matching `score.gate_pass` for that venue + `market_id` (+ side)
- `x_news.ok=true` with note `no pull yet`
- Skipping OSIRIS, 1inch, or the crypto tape
- POSTing `https://osirisai.live/api/github-webhook`
- Null `model_cents`
- `learn` on a cycle with no settle
- Changing the 6% PM gate (scalp gate is separate and may nudge itself)
- Kraken live order, Global CLOB
- Onchain `book_kind=sports`
- POSTing to Lovable
- `git pull` on every cycle
