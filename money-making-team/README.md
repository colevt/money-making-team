# Worlds #1 Money Team

Local desk, ledger, and ingest for the Grok trading bots.

## Run the dashboard

```bash
python3 tools/serve_desk.py
```

Open http://127.0.0.1:8765. That page polls live `/api/desk`, shows Kalshi / Polymarket US / Onchain balances, and the Learn tab replays real decisions. Lovable is not in this loop.

## Connect the two Grok bots

**Scorer** pulls UW, X, ESPN, Kraken, and the books. **Trader** posts Kalshi / Polymarket US only after a passing score. Do not add more Bots. This repo is the control plane: edit `grok/scorer.md` / `grok/trader.md` here, Bots `git pull`. Paste once: [grok/paste/scorer.txt](grok/paste/scorer.txt) and [grok/paste/trader.txt](grok/paste/trader.txt). Steps: [grok/CONNECT.md](grok/CONNECT.md). Cycle: [grok/CYCLE.md](grok/CYCLE.md).

Every cycle (including Quiet) must land in the ledger. A score without `model_cents` is rejected.

```bash
python3 tools/append_event.py '{"ts":"2026-09-02T14:10:00-06:00","cycle_id":"c-demo","kind":"quiet","bot":"scorer","reason":"gap under 6%"}'
python3 tools/heartbeat.py
python3 tools/learn_from_settle.py --cycle_id c-demo
python3 tools/test_ledger_contract.py
```

(`tools/append-event.mjs` is the same contract if Node is installed.) With `.env` set (`cp .env.example .env`), that POST also hits the desk ingest URL. Or run the watcher:

```bash
python3 tools/ingest.py
```

Roster and MCP paste-ins: [grok/TEAM.md](grok/TEAM.md), [grok/INSTRUCTIONS.md](grok/INSTRUCTIONS.md). Gates: [playbook.md](playbook.md). Event shape: [ledger/schema.md](ledger/schema.md).

## What the two bots are allowed to do

- Scorer: Unusual Whales, X, ESPN, Kraken public data / paper. Never fills.
- Trader: signed Kalshi and Polymarket US only. Onchain USDC is cash, not a ticket venue.
- Never: live Kraken, withdraw, Global CLOB, ask ≥ 0.80, keys in chat, a ticket without `model_cents`.

## Desk sample session

`ledger/events.jsonl` is seeded from the existing Desk blotter (PHI @ AZ open, 1W 6L, Global CLOB 403) plus a Quiet KXBTC15M cycle so the dashboard is never empty.
