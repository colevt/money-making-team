# Worlds #1 Money Team — two Grok bots

Living jobs: [scorer.md](scorer.md), [trader.md](trader.md). One-time profile paste: [paste/scorer.txt](paste/scorer.txt), [paste/trader.txt](paste/trader.txt). Wire-up: [CONNECT.md](CONNECT.md). Two Bots; feeds are not Bots.

| Bot | `bot` field | Tools | Job |
| --- | --- | --- | --- |
| Scorer | `scorer` | Unusual Whales `4021654`, X `4022021`, Kraken `4031115`, ESPN game state, live books | Pull every feed, write `ingest` + `score` (`model_cents` required). Gate fail → `quiet`. After settle run `learn_from_settle.py`. Does not fill. |
| Trader | `trader` | Kalshi + Polymarket US signed post | Only if this cycle already `gate_pass`. `ticket → post → fill → mark → flatten or settle`. Does not score. Does not learn. |

Scoring feeds (Scorer pulls these; do not create extra Bots): Unusual Whales, X, ESPN, Kraken public/paper. Never live Kraken, never `-s trade`.

## Cycle

See [CYCLE.md](CYCLE.md). Short form:

Scorer ingest (six feeds) → Scorer score with **model_cents** → **6% and ask < 0.80** or Quiet → Trader ticket → post → fill → flatten-watch → settle → Scorer `python3 tools/learn_from_settle.py`.

Quiet still emits `ingest` + `score` + `quiet`. No `learn` on quiet. Two weight books in [ledger/weights.json](../ledger/weights.json). ESPN does not train on crypto 15m.

Heartbeat: `python3 tools/heartbeat.py` (scorer + trader).

## Ledger

```bash
python3 tools/append_event.py '{"ts":"ISO","cycle_id":"…","kind":"score","bot":"scorer",...}'
```

A score without `model_cents` is rejected. If Grok local tools stay on `never`, POST the same JSON to `LOVABLE_INGEST_URL` with the Bearer token from `.env`. Do not paste the token into a Bot description.

Standing rules: [playbook.md](../playbook.md) · [ledger/schema.md](../ledger/schema.md) · paste: [paste/scorer.txt](paste/scorer.txt), [paste/trader.txt](paste/trader.txt)
