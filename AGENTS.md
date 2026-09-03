# Worlds #1 Money Team

This repo is the live desk for **two** Grok bots (Scorer + Trader). Improve them here in Cursor; they pick up changes once a day via `python3 tools/daily_update.py`. Follow [grok/CYCLE.md](grok/CYCLE.md), [grok/scorer.md](grok/scorer.md) or [grok/trader.md](grok/trader.md), and [playbook.md](playbook.md). Attach: [grok/CONNECT.md](grok/CONNECT.md). Do not add X/ESPN/Kraken as extra Bots — those are Scorer feeds.

Lovable is a public view of `site/` later. It is not in the agent loop. Do not ask for ingest tokens.

- After every cycle: `python3 tools/append_event.py '…'`
- Score requires `model_cents`. One score per fillable Kalshi, Polymarket US, **and** 1inch market. Scalp scores from `python3 tools/scalp.py --append`. Many tickets per cycle.
- Gate: PM edge >= 6%. Scalp edge >= 0.35%. Kalshi/Poly ask < 0.80. Onchain ask < 1.00.
- Trader: `python3 tools/execute.py --cycle_id …` then `--live --append` (BUY and SELL). Keys in `.env` only.
- After settle: `python3 tools/learn_from_settle.py --cycle_id … --ticket_id …` — the model learns from itself.
- Heartbeat: `python3 tools/heartbeat.py`
- Never paste keys into chat.
