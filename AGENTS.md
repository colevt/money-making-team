# Worlds #1 Money Team

This repo is the live desk for **two** Grok bots (Scorer + Trader). Improve them here in Cursor; they `git pull --ff-only` before a cycle. Follow [grok/CYCLE.md](grok/CYCLE.md), [grok/scorer.md](grok/scorer.md) or [grok/trader.md](grok/trader.md), and [playbook.md](playbook.md). Attach: [grok/CONNECT.md](grok/CONNECT.md). Do not add X/ESPN/Kraken as extra Bots — those are Scorer feeds.

Lovable is a public view of `site/` later. It is not in the agent loop. Do not ask for ingest tokens.

- After every cycle (trade or quiet): `python3 tools/append_event.py '…'`
- Score requires `model_cents`. Null model is not a score.
- Gate: edge >= 6% AND ask < 0.80 AND fresh ingest, else `quiet`.
- Tickets: Kalshi or Polymarket US only. Onchain is cash, not a venue.
- Scoring only: Unusual Whales, X, ESPN, Kraken (never `-s trade`, never withdraw).
- After settle only: `python3 tools/learn_from_settle.py --cycle_id …`. Quiet does not learn.
- Heartbeat: `python3 tools/heartbeat.py`
- Never paste keys into chat.
