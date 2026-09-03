---
name: money-team-desk
description: Run the Worlds #1 Money Team Grok desk from this git repo. Use when scoring, trading, heartbeating, appending ledger events, or improving the Scorer/Trader bots in Cursor.
---

# Money Team desk

This git repo is the control plane for **two** Grok bots (Scorer + Trader). Cursor edits the files; bots `git pull` before every cycle. Lovable only hosts a public copy of `site/` later. It is not in the agent loop. Do not ask for `LOVABLE_INGEST_TOKEN`.

## Clone (once, on the Bot computer)

```bash
cd /workspace
git clone https://github.com/colevt/money-making-team.git
cd money-making-team
bash tools/bootstrap.sh
```

Public GitHub. No Origin login. No `.env` required.

## Every cycle

1. `git pull --ff-only`
2. Follow `grok/CYCLE.md` plus `grok/scorer.md` or `grok/trader.md`
3. Append with `python3 tools/append_event.py '…'` into `ledger/events.jsonl`
4. Heartbeat: `python3 tools/heartbeat.py --bot scorer` or `--bot trader`

## Roles

- **Scorer** (`bot=scorer`): pull Unusual Whales, X, ESPN, Kraken, live books. Emit `ingest` then `score` with `model_cents`. Gate fail → `quiet`. Never fill. After settle: `python3 tools/learn_from_settle.py --cycle_id …`
- **Trader** (`bot=trader`): Kalshi / Polymarket US signed post only if this `cycle_id` already has `score.gate_pass=true`. `ticket → post → fill → mark → flatten or settle`. Does not score. Does not learn.

Do not create extra Bots for X, ESPN, or Kraken.

## Gate

Ticket only when `edge_pct >= 6` AND `ask < 0.80` AND venue is `kalshi` or `polymarket_us` AND ingest is fresh. Else `quiet`. Null `model_cents` is not a score.

## Improve the bots in Cursor

Edit `grok/scorer.md`, `grok/trader.md`, `grok/CYCLE.md`, or `playbook.md`, then push. Next cycle the Bots pull the new file. Re-paste `grok/paste/scorer.txt` / `grok/paste/trader.txt` only if the pointer text itself changed.

## Illegal

- Keys, RSA, signed payloads, or ingest tokens in chat or Bot descriptions
- Live Kraken, Global CLOB, Onchain as a ticket venue
- Ask ≥ 0.80, sports before first pitch, `learn` on quiet
- POSTing cycle JSON to Lovable
