# Live desk

Work happens in this repo. Improve the Grok bots in Cursor; they pull this git remote. Lovable is only for publishing a public view of `site/` later — not ingest, not tokens, not the agent loop.

## Local dashboard

```bash
python3 tools/serve_desk.py
```

Then open http://127.0.0.1:8765 (Learn: http://127.0.0.1:8765/#learn).

The server proxies `GET /api/desk` from `LIVE_DESK_URL` and verifies Onchain native USDC on Polygon. Kalshi and Polymarket US balances still come from the live desk keys.

## Accounts (fill)

- **Polymarket US** — signed fills
- **Kalshi** — signed fills
- **Onchain** — Polygon DEX native USDC (`0xcE01…49BF`). POL is gas, not cash. Do not mix this into Kalshi/Poly ticket runway.

Kraken, Unusual Whales, X, and ESPN are scoring feeds, not fill accounts. Global CLOB is not a wallet.

## URLs

- Live blotter API: `GET https://merger-sole-additional-checked.trycloudflare.com/api/desk`
- Public view later: https://lovable.dev/projects/818c0ae4-01a3-494b-9415-568cacef4992
