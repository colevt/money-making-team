---
name: money-team-desk
description: Run the Worlds #1 Money Team Grok desk from this git repo. Use when scoring, trading, heartbeating, appending ledger events, or improving the Scorer/Trader bots in Cursor.
---

# Money Team desk

This git repo is the control plane for **two** Grok bots (Scorer + Trader). Cursor edits the files; bots pick them up **once a day** with `python3 tools/daily_update.py`. Do not `git pull` on every scan. Lovable only hosts a public copy of `site/` later. It is not in the agent loop. Do not ask for `LOVABLE_INGEST_TOKEN`.

## Clone (once, on the Bot computer)

```bash
cd /workspace
git clone https://github.com/colevt/money-making-team.git
cd money-making-team
bash tools/bootstrap.sh
```

Public GitHub. No Origin login. No `.env` required.

## Once a day

`python3 tools/daily_update.py` — skip if today's pull already landed.

## Every cycle (no git pull)

1. Follow `grok/CYCLE.md` plus `grok/scorer.md` or `grok/trader.md`
2. Append with `python3 tools/append_event.py '…'` into `ledger/events.jsonl`
3. Heartbeat: `python3 tools/heartbeat.py --bot scorer` or `--bot trader`

## Roles

- **Scorer** (`bot=scorer`): pull Unusual Whales, X, ESPN, Kraken, OSIRIS (`python3 tools/osiris.py`), 1inch (`python3 tools/oneinch.py`), live books. One `score` per fillable Kalshi, Polymarket US, and onchain market. Cycle `quiet` only if none pass. Never fill. After settle: `python3 tools/learn_from_settle.py --cycle_id … --ticket_id …`
- **Trader** (`bot=trader`): `python3 tools/execute.py --cycle_id …` then `--live --append`. Fill **every** passing score on kalshi / polymarket_us / onchain. Does not score. Does not learn.

Do not create extra Bots for X, ESPN, or Kraken.

## Gate

Ticket when `edge_pct >= 6` AND venue is `kalshi`, `polymarket_us`, or `onchain`. Kalshi/Poly also need `ask < 0.80`. Onchain needs `ask < 1.00` and `book_kind=crypto15m`. Many tickets per cycle. Cycle `quiet` only if none pass.

## Improve the bots in Cursor

Edit `grok/scorer.md`, `grok/trader.md`, `grok/CYCLE.md`, or `playbook.md`, then push. The next daily update picks up the file. Re-paste `grok/paste/scorer.txt` / `grok/paste/trader.txt` only if the pointer text itself changed.

## Illegal

- Keys, RSA, signed payloads, or ingest tokens in chat or Bot descriptions
- Live Kraken, Global CLOB
- Ask ≥ 0.80 on Kalshi/Poly; filling only one venue when others passed
- Ask ≥ 0.80, sports before first pitch, `learn` on quiet
- POSTing cycle JSON to Lovable
- `git pull` on every 5-minute scan
- POSTing `https://osirisai.live/api/github-webhook` (not a scoring GET)
