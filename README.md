# Worlds #1 Money Team

Local desk, ledger, and two Grok bots. This git repo is the control plane: edit the bots in Cursor, they pick up changes once a day.

## Run the dashboard

```bash
python3 tools/serve_desk.py
```

Open http://127.0.0.1:8765. That page polls live `/api/desk`, shows Kalshi / Polymarket US / Onchain balances, and the Learn tab replays real decisions. Lovable is not in this loop — it can host a copy of `site/` later as a public view.

## Connect the two Grok bots

**Scorer** pulls UW, X, ESPN, Kraken, OSIRIS, 1inch, crypto tape, and the books — score every fillable market **and** run `scalp.py` (buy low / sell high). **Trader** posts Kalshi, Polymarket US, **and** Polygon 1inch for every passing score this cycle, including scalp SELL. Do not add more Bots.

Clone (public GitHub, no token):

```bash
git clone https://github.com/colevt/money-making-team.git
cd money-making-team
bash tools/bootstrap.sh
```

Paste once: [grok/paste/scorer.txt](grok/paste/scorer.txt) and [grok/paste/trader.txt](grok/paste/trader.txt). Steps: [grok/CONNECT.md](grok/CONNECT.md). Cycle: [grok/CYCLE.md](grok/CYCLE.md). Skill: [`.agents/skills/money-team-desk/SKILL.md`](.agents/skills/money-team-desk/SKILL.md).

Every cycle (including Quiet) must land in `ledger/events.jsonl`. A score without `model_cents` is rejected. No ingest token.

```bash
python3 tools/append_event.py '{"ts":"2026-09-02T14:10:00-06:00","cycle_id":"c-demo","kind":"quiet","bot":"scorer","reason":"gap under 6%"}'
python3 tools/heartbeat.py
python3 tools/learn_from_settle.py --cycle_id c-demo
python3 tools/test_ledger_contract.py
python3 tools/test_scalp.py
```

(`tools/append-event.mjs` is the same contract if Node is installed.)

Roster: [grok/TEAM.md](grok/TEAM.md), [grok/INSTRUCTIONS.md](grok/INSTRUCTIONS.md). Gates: [playbook.md](playbook.md). Event shape: [ledger/schema.md](ledger/schema.md).

## What the two bots are allowed to do

- Scorer: Unusual Whales, X, ESPN, Kraken public data / paper, OSIRIS, 1inch quotes. Never fills.
- Trader: `python3 tools/execute.py` on Kalshi, Polymarket US, and Polygon 1inch. Fill every passing score, not just one.
- Never: live Kraken, withdraw, Global CLOB, keys in chat, a ticket without `model_cents`.

## Desk sample session

`ledger/events.jsonl` is seeded from the existing Desk blotter (PHI @ AZ open, 1W 6L, Global CLOB 403) plus a Quiet KXBTC15M cycle so the dashboard is never empty.
