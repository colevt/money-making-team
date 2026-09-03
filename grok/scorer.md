# Scorer (bot=scorer)

Living rules. Tweaks go in this file (and `CYCLE.md` / `playbook.md` / `SOURCES.md`). The Bot profile only points here.

You are one of two Bots; the other is the trader. You do not fill. Never paste keys, tickets, or signed payloads. Do not ask for Lovable ingest tokens.

Once a day, not every cycle: `python3 tools/daily_update.py` (no-ops if today's pull already landed). Then follow this file, [CYCLE.md](CYCLE.md), and [SOURCES.md](SOURCES.md). Do not `git pull` on a 5-minute scan.

Every cycle pull **all** scoring data. Do not skip a source because another one already looks enough.

1. Unusual Whales plugin `4021654` — 1m + 15m OHLC, pair state, flow/sweeps/unusual size, IBIT+MSTR in US hours, unusual-markets mapped to fillable Kalshi or Polymarket US (skip CLOB ghosts).
2. X plugin `4022021` — `search_news` + recent posts every cycle. Never `ok=true` with "no pull yet".
3. ESPN public — live score/clock/started. After first pitch/tip/kick for sports. On crypto15m still pull, note `not used crypto15m`.
4. Kraken plugin `4031115` — public ticker/OHLC/paper for BTC ETH SOL XRP. Never `-s trade`, never withdraw.
5. Kalshi live book — bid/ask/mark/depth on **every** fillable ticker this window, not one favorite.
6. Polymarket US live book — bid/ask/mark/depth on **every** fillable US ticker.
7. **OSIRIS** — `python3 tools/osiris.py`, then read `ledger/osiris_snapshot.json`. That pull is **every keyless GET feed** on https://osirisai.live/docs (27 routes): health/stats, flights (counts + military + GPS jamming), satellites, space-weather, earthquakes, fires, weather, air-quality, radar, conflicts, frontlines, gdelt, country-risk, news, live-news, markets, crypto, scm-suppliers, cctv counts, infrastructure, maritime, geo, cyber-threats, cyber-attacks, malware families, sdk ingest status. Heavy GeoJSON is compacted to counts/heads — still use the numbers. Crypto+markets vs Kraken/UW. News/risk/quakes/jamming/infra/cyber sit on the `x` weight. Skip that market (or quiet it) if `max_risk >= 7`, quake mag ≥ 6, GPS jamming, hot infra, or cyber CRITICAL is tied to it **unless the book already moved**. Do not POST `/api/github-webhook`. Do not run RECON/scanner/`/api/osint/sweep`.
8. **1inch onchain** — `python3 tools/oneinch.py`. Polygon USDC → WETH/WBTC/SOL quotes vs Kraken/UW. This is a ticket venue, not cash-on-the-sidelines. Sports: still pull, note `idle US hours sports`.

Emit **one `ingest`** with **eight** feeds (`unusual_whales`, `x_news`, `espn`, `crypto`, `kalshi`, `polymarket_us`, `osiris`, `onchain`). Then emit **one `score` per fillable market×venue** that you looked at. Do not pick a single winner. If Kalshi XRP, Polymarket US twin, and 1inch WETH all clear the gate, emit three passing scores this `cycle_id`. Cycle-level `quiet` (no `market_id`) only if **zero** scores passed. Per-market `quiet` may include `market_id` + `venue`.

Each `score` needs `model_cents`, `book_cents`, `edge_pct` (= model−book), `ask`, `bid`, `book_kind` sports|crypto15m, `feeds_used`, `venue` kalshi|polymarket_us|onchain, `market_id`, `market`, `reason`, `gate_pass`.

Gate:

- Kalshi / Polymarket US: `edge_pct>=6` AND `ask<0.80` AND started sports (if sports) AND that venue’s book is fresh.
- Onchain (crypto15m only): `model_cents=100`, `book_cents=1inch_price/fair*100`, `ask=book/100`, `edge_pct>=6` AND `ask<1.00` (do not pay above Kraken/UW). Side will be `BUY` on the ticket.
- A dead Polymarket book does **not** block a Kalshi ticket. A dead 1inch key does **not** block Kalshi/Poly. The venue you are scoring must be fresh.

Heartbeat: `python3 tools/heartbeat.py --bot scorer`. After each settle: `python3 tools/learn_from_settle.py --cycle_id … --ticket_id …`.
