# Worlds #1 Money Team

This repo is the live desk for **two** Grok bots (Scorer + Trader). Before a cycle: `git pull --ff-only`, then follow [grok/CYCLE.md](grok/CYCLE.md), [grok/scorer.md](grok/scorer.md) or [grok/trader.md](grok/trader.md), and [playbook.md](playbook.md). Attach: [grok/CONNECT.md](grok/CONNECT.md). Tweaks in these files apply on the next pull. Do not add X/ESPN/Kraken as extra Bots — those are Scorer feeds.

- After every cycle (trade or quiet): `python3 tools/append_event.py '…'`
- Score requires `model_cents`. Null model is not a score.
- Gate: edge >= 6% AND ask < 0.80 AND fresh ingest, else `quiet`.
- Tickets: Kalshi or Polymarket US only. Onchain is cash, not a venue.
- Scoring only: Unusual Whales, X, ESPN, Kraken (never `-s trade`, never withdraw).
- After settle only: `python3 tools/learn_from_settle.py --cycle_id …`. Quiet does not learn.
- Heartbeat: `python3 tools/heartbeat.py`
- Never paste keys or ingest tokens into chat.
