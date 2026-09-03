# Live desk

Work happens in this repo. Improve the Grok bots in Cursor; they pull this git remote. Lovable is a **static public URL** for `site/`. Do not use Lovable chat, Cloud, or ingest — those burn credits. The page polls the live Cloudflare desk API.

## Local dashboard

```bash
python3 tools/serve_desk.py
```

Then open http://127.0.0.1:8765 (Learn: http://127.0.0.1:8765/#learn).

The server proxies `GET /api/desk` from `LIVE_DESK_URL` and verifies Onchain native USDC on Polygon. Kalshi and Polymarket US balances still come from the live desk keys.

## Accounts (fill)

- **Polymarket US** — signed fills
- **Kalshi** — signed fills
- **Onchain** — Polygon 1inch (`python3 tools/oneinch.py` / `execute.py --live`). Native USDC `0xcE01…49BF`. POL is gas. Do not mix this USDC into Kalshi/Poly size.

Kraken, Unusual Whales, X, and ESPN are scoring feeds, not fill accounts. Global CLOB is not a wallet.

## URLs

- Live blotter API: `GET https://merger-sole-additional-checked.trycloudflare.com/api/desk` (CORS is open)
- Lovable project (host only): https://lovable.dev/projects/818c0ae4-01a3-494b-9415-568cacef4992

## Public publish (no Lovable credits)

The desk data already lives on Cloudflare. Lovable only needs to serve the three files in `site/` (`index.html`, `app.js`, `style.css`). Those files fetch the Cloudflare `/api/desk` URL in the browser.

Do **not**:

- Type anything in Lovable chat (that is what spends credits)
- Turn on Lovable Cloud / Supabase
- Set `PUBLISH_URL` or `LOVABLE_INGEST_TOKEN`
- Run `python3 tools/ingest.py`

In the existing Lovable project: skip the AI prompt. If GitHub is connected, pull `site/` from this repo and hit **Publish**. If it is not connected, upload those three files as the app and publish. Share the `*.lovable.app` URL.

Local still works: `python3 tools/serve_desk.py` → http://127.0.0.1:8765.
