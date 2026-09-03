# Worlds #1 Money Team — two Grok bots

Living jobs: [scorer.md](scorer.md), [trader.md](trader.md). One-time profile paste: [paste/scorer.txt](paste/scorer.txt), [paste/trader.txt](paste/trader.txt). Skill: [paste/skill-desk.txt](paste/skill-desk.txt). Wire-up: [CONNECT.md](CONNECT.md). Two Bots; feeds are not Bots.

| Bot | `bot` field | Tools | Job |
| --- | --- | --- | --- |
| Scorer | `scorer` | UW `4021654`, X `4022021`, Kraken `4031115`, ESPN, OSIRIS, 1inch, crypto tape, X tape, live books | Pull every feed. One `score` per fillable Kalshi / Polymarket US / 1inch-fair market. Scalp scores from `scalp.py --append`. Cycle quiet only if none pass. After settle: `learn_from_settle.py --ticket_id`. Does not fill. |
| Trader | `trader` | `python3 tools/execute.py` → Kalshi + Polymarket US + Polygon 1inch | Fill **every** passing score this cycle including scalp SELL. `--live --append` when `.env` keys exist. Does not score. Does not learn. |

## Cycle

See [CYCLE.md](CYCLE.md). Short form:

Scorer ingest (eight feeds + tapes) → PM scores + `scalp.py` BUY/SELL → gates (6% PM / 0.35% scalp) → Trader execute all → mark → settle per ticket → Scorer learn per ticket (weights + scalp params).

Heartbeat: `python3 tools/heartbeat.py` (scorer + trader).
