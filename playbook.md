# Worlds #1 Money Team playbook

Source of truth for the two Grok bots (Scorer + Trader). Unusual Whales, X, ESPN, Kraken, and OSIRIS are scoring **feeds**, not extra Bots. Use **all** of them every scan. The desk exists to show **why** a cycle was Quiet vs traded, then retune from settled P/L. Caps are not optional. [grok/CYCLE.md](grok/CYCLE.md) is the step list; [grok/SOURCES.md](grok/SOURCES.md) is the full pull list; [ledger/schema.md](ledger/schema.md) is what `append_event.py` will reject.

## Venues

Execution wallets on the desk:

- **Kalshi** — signed fills (sports + crypto 15m). Ticket venue.
- **Polymarket US** — signed fills. Ticket venue.
- **Onchain** — Polygon DEX native USDC **cash** wallet. POL is gas, not spendable. Not a ticket `venue`. Do not mix this balance into Kalshi or Poly runway.

Scoring only (never a fill venue):

- Unusual Whales, X, ESPN, Kraken, and OSIRIS (`python3 tools/osiris.py` GETs).
- Never place a live Kraken order. Never enable `-s trade`. Never withdraw.
- Global CLOB is not a venue. 403 geo is expected. No order path through it.
- Do not POST `https://osirisai.live/api/github-webhook`. That forwards signed GitHub events; empty `{}` is not a book.

## Gate (must all pass)

A ticket is allowed only when:

1. `model_cents` is present and `edge_pct` equals `model_cents - book_cents` and is **≥ 6%**
2. Live **ask < 0.80** (do not buy because UW looks bullish)
3. Book is Kalshi or Polymarket US (fillable ticker, not a CLOB ghost)
4. Sports: game **has started**; X/ESPN are lag detectors, not standalone buys. Use `book_kind=sports`.
5. Crypto 15m: UW+Kraken+OSIRIS `/api/crypto` vs the Kalshi 15m book. Use `book_kind=crypto15m`. Do not apply ESPN sports weights.
6. Ingest is fresh (kill switches below). X actually pulled. OSIRIS actually pulled.

Otherwise emit `quiet` and stand down. Quiet is a first-class outcome. The append tool refuses `gate_pass: true` when ingest is missing or stale.

## Size and risk

- Dollar-at-risk stays inside side + size caps on the trading bot.
- Runway = spendable / avg stake. If runway is thin, skip marginal edges.
- Never paste keys, RSA material, or signed payloads into chat or the ledger.

## Hours

- US hours: flow, IBIT/MSTR, live US sports books (`sports`).
- Overnight: crypto OHLC vs **KXBTC15M** (`crypto15m`). Daytime Kalshi 15m crypto uses the same book, not ESPN weights.

## Flatten-watch

After fill the trader stays on the ticket: emit `mark` on each check. If an exit trigger fires, emit `flatten` with `trigger`. Market resolve → `settle`. Do not skip `post` or `mark`.

## Learning

- Two books in [ledger/weights.json](ledger/weights.json): `sports` and `crypto15m`.
- Only `settle` retunes, and only by running `python3 tools/learn_from_settle.py --cycle_id …` (±0.02 on `feeds_used`, renormalize).
- ESPN weight is frozen on crypto15m. Crypto weight is frozen on sports.
- Quiet cycles do not change weights.
- Gate stays **6%** until 60 settled tickets on that book. Do not hand-edit the gate.

## Kill switches → Quiet

- Any scoring feed stale (UW>10m, X>5m or no pull, ESPN sports>45s, Kraken>3m, books>20s, OSIRIS>90s)
- OSIRIS incomplete (`python3 tools/osiris.py` failed core routes)
- Ingest/desk heartbeat down (no heartbeat in 5 minutes)
- Market is Global-CLOB-only
- Ask ≥ 0.80
- Game not started (sports)
- `model_cents` missing

## After every cycle

Append with [tools/append_event.py](tools/append_event.py) using [ledger/schema.md](ledger/schema.md). That is how the desk stays connected to this team. Lovable is a public view of `site/` later, not part of the cycle.
