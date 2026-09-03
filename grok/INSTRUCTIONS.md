# Paste-ready addenda (two Bots)

**This repo is the control plane.** Connect: [CONNECT.md](CONNECT.md). Cursor edits the living files; Bots update once a day (`python3 tools/daily_update.py`).

Paste once:

- Scorer profile → [paste/scorer.txt](paste/scorer.txt)
- Trader profile → [paste/trader.txt](paste/trader.txt)
- Skill (both) → [paste/skill-desk.txt](paste/skill-desk.txt)

Unusual Whales, X, ESPN, and Kraken are feeds on the Scorer, not more Bots. OSIRIS is `python3 tools/osiris.py`. 1inch is `python3 tools/oneinch.py`. Crypto tape + scalps: `python3 tools/scalp.py`. Lovable is display-only.

## Scorer (`bot`: scorer)

Plugins: Unusual Whales `4021654`, X `4022021`, Kraken `4031115`. ESPN is a public game-state pull. Full job: [scorer.md](scorer.md). Scoring only. Never paste keys, never post tickets.

## Trader (`bot`: trader)

Kalshi / Polymarket US / Polygon 1inch via `python3 tools/execute.py`. Fill every passing score this cycle, including scalp SELL. Full job: [trader.md](trader.md).
