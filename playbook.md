# Worlds #1 Money Team playbook

Source of truth for the two Grok bots (Scorer + Trader). Unusual Whales, X, ESPN, Kraken, OSIRIS, and 1inch quotes are scoring **feeds**. Kalshi, Polymarket US, and onchain 1inch are **ticket venues**. Use **all** of them every scan. Fire **every** market×venue that clears the gate — do not stop at one ticket. Caps are not optional. [grok/CYCLE.md](grok/CYCLE.md) · [grok/SOURCES.md](grok/SOURCES.md) · [ledger/schema.md](ledger/schema.md).

## Venues

- **Kalshi** — signed fills (sports + crypto 15m).
- **Polymarket US** — signed fills.
- **Onchain** — Polygon 1inch classic swap v6.1 (`python3 tools/oneinch.py`, live via `tools/execute.py --live`). Native USDC from `0xcE01…49BF`. POL is gas. `crypto15m` 6% cheap-vs-fair **and** `crypto_scalp` buy-low/sell-high.

Scoring only (never a fill venue): Unusual Whales, X, ESPN, Kraken, OSIRIS (`python3 tools/osiris.py` — all GET feeds). Never `-s trade`. Never Global CLOB. Never POST github-webhook. Never RECON/scanner.

## Gate (per market × venue)

A ticket is allowed only when that market’s score has:

1. `model_cents` present and `edge_pct` = `model_cents - book_cents`. Kalshi/Poly/`crypto15m`: **≥ 6%**. `crypto_scalp`: **≥ 0.35%**.
2. Kalshi / Poly: live **ask < 0.80**. Onchain: **ask < 1.00** (1inch/fair; do not pay above Kraken/UW).
3. Venue is `kalshi`, `polymarket_us`, or `onchain` (fillable ticker / 1inch pair).
4. Sports: game **has started**; `book_kind=sports`; not onchain.
5. Crypto 15m / 1inch mispricing: `book_kind=crypto15m` (edge ≥ 6%).
6. Crypto scalp: `book_kind=crypto_scalp` from `python3 tools/scalp.py` only. Buy local low, sell local high. Edge ≥ **0.35%**. One lot per token.
7. Ingest is fresh **for that venue**. A dead Poly book does not block Kalshi. A missing 1inch key does not block Kalshi/Poly. X actually pulled. OSIRIS actually pulled.

Otherwise per-market `quiet`, or cycle `quiet` if **none** passed. The append tool refuses a ticket that does not match a passing score for that venue + `market_id`.

## Size and risk

- Dollar-at-risk stays inside `TICKET_USD` / `MAX_TOTAL_USD` / `MAX_TICKETS_PER_CYCLE` (defaults $1 / $40 / 12). Scalps recycle the same $1: SELL does not count against the cap.
- Three runways: Kalshi cash, Poly cash, onchain USDC. Do not mix.
- Never paste keys into chat or the ledger. `--live` reads `.env`.

## Hours

- US hours: live sports on Kalshi/Poly (`sports`). Still quote 1inch and run scalps.
- Overnight + Kalshi 15m crypto: books **and** 1inch (`crypto15m`).
- Every scan: crypto tape + scalp (`crypto_scalp`) — many small ETH/BTC/SOL round-trips.

## Flatten-watch / learning

After fill the trader `mark`s **each** open ticket. Scalp SELL is the flatten. Settle per ticket (`WON` if `pl_usd>0`). Scorer: `python3 tools/learn_from_settle.py --cycle_id … --ticket_id …` — this retunes weights **and** scalp dip/take/stop. Quiet with no settle does not learn. PM gate stays **6%**. Scalp gate starts at **0.35%** and learns.

## Kill switches → skip that market (not the whole desk)

- That venue’s book stale, or core feeds stale (UW>10m, X>5m or no pull, ESPN sports>45s, Kraken>3m on crypto15m, OSIRIS>90s)
- OSIRIS incomplete
- Kalshi/Poly ask ≥ 0.80; onchain ask ≥ 1.00
- Game not started (sports)
- `model_cents` missing
- Global-CLOB-only name
