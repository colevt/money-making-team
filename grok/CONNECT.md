# Connect the two Grok bots (this repo is the control plane)

Cursor is how you make the bots better: edit [scorer.md](scorer.md), [trader.md](trader.md), [CYCLE.md](CYCLE.md), [playbook.md](../playbook.md), push, and the Bots pick it up on the **once-a-day** `python3 tools/daily_update.py`. Bot **descriptions** are short pointers ([paste/scorer.txt](paste/scorer.txt), [paste/trader.txt](paste/trader.txt)). Paste those once.

Two Bots only. Unusual Whales, X, ESPN, Kraken, OSIRIS, and 1inch quotes are **feeds the Scorer pulls**, not extra Bots. Tickets go to Kalshi, Polymarket US, **and** onchain 1inch — 6% mispricing **and** 0.35% buy-low/sell-high scalps, as many as clear the gate.

The cycle lives in this git repo. Events go to `ledger/events.jsonl` via `python3 tools/append_event.py`. **Lovable is display-only** (`site/` later). Do not ask for ingest tokens. Never put venue keys in a Bot profile, chat, or share link.

**Clone URL:** `https://github.com/colevt/money-making-team.git` (public)

Official UI: [Create and manage Bots](https://docs.x.ai/grok-bot/bots) · [cursor.com/bot/onboarding](https://cursor.com/bot/onboarding)

## 1. Clone this repo on the Bot computer (once)

Grok Bot cannot see `localhost` on your laptop. It needs this repo on **its** computer at `/workspace`.

```text
cd /workspace
git clone https://github.com/colevt/money-making-team.git
cd money-making-team
bash tools/bootstrap.sh
```

If you already cloned the nested copy (`money-making-team/money-making-team`), `python3 tools/daily_update.py --force` from the clone root; tools now sit at the repo root. Trader `--live` needs `.env` keys (never in the Bot profile).

## 2. Scorer plugins (account-wide)

Settings → Plugins, enable on the **Scorer** (Trader does not need them):

| Plugin | ID | Role |
| --- | --- | --- |
| Unusual Whales | `4021654` | OHLC / flow for the model |
| X | `4022021` | news + lag (must actually pull) |
| Kraken | `4031115` | public ticker / paper only — never `-s trade` |

Trader fills Kalshi + Polymarket US + Polygon 1inch via `python3 tools/execute.py`. Keys stay in `.env` on the Bot computer, never in the profile. ESPN is a public pull the Scorer does. MCP must be public HTTPS. Local stdio / `localhost` will not attach.

## 3. Paste once into each Bot profile

New → Create new agent (twice). Bot actions → **Edit Profile** → description:

| Bot | `bot` field | Copy this |
| --- | --- | --- |
| Scorer | `scorer` | [paste/scorer.txt](paste/scorer.txt) |
| Trader | `trader` | [paste/trader.txt](paste/trader.txt) |

Save [paste/skill-desk.txt](paste/skill-desk.txt) as the `money-team-desk` skill and enable it on both (Settings → Plugins → Yours). Cursor agents pick up the same skill from [`.agents/skills/money-team-desk/SKILL.md`](../.agents/skills/money-team-desk/SKILL.md).

First messages:

- Scorer: `read grok/scorer.md and grok/CYCLE.md. Run bash tools/bootstrap.sh if tools/ is missing. Pull all eight feeds (osiris.py + oneinch.py + crypto_tape.py + x_tape.py). python3 tools/scalp.py --cycle_id … --append for buy-low/sell-high. Emit one score per fillable Kalshi, Polymarket US, and 1inch market. Cycle quiet only if none pass. After settle learn_from_settle.py. Do not fill. Do not git pull every scan.`
- Trader: `read grok/trader.md. Fill EVERY passing score this cycle: python3 tools/execute.py --cycle_id … then --live --append. Kalshi, Polymarket US, and 1inch BUY and SELL. Do not stop after one ticket. Do not leave a scalp lot through the high. Do not git pull on a handoff.`

## 4. Routines

**Daily (Scorer, once per America/Denver day):** `python3 tools/daily_update.py`. That is the only scheduled git pull. Calling it extra times the same day is a no-op.

**Scorer scan:** every 5 minutes `python3 tools/heartbeat.py --bot scorer`, then one scan from CYCLE.md. No `git pull`.

**Trader:** no scan of its own. When Scorer emits any `gate_pass true`, run `python3 tools/execute.py --cycle_id …` (then `--live --append`). Fill all of them. No `git pull`.

## 5. How tweaks work (Cursor)

1. Open this GitHub repo in Cursor.
2. Edit `grok/scorer.md`, `grok/trader.md`, `grok/CYCLE.md`, or `playbook.md`.
3. Push to `main`.
4. Next daily update the Bot pulls and uses the new file. Do not re-paste the profile unless the pointer text itself changed. Do not wait for the next 5-minute scan to git pull.

## 6. Check it worked

```bash
python3 tools/daily_update.py
python3 tools/test_ledger_contract.py
python3 tools/test_scalp.py
tail -n 20 ledger/events.jsonl
```

Quiet: `ingest` (eight feeds, X actually pulled, OSIRIS + 1inch quoted, crypto tape) + scores + cycle `quiet` only if none passed. Fired: Trader `python3 tools/execute.py --cycle_id … --live --append` for **every** passing market including scalp SELL. Later `settle` per ticket, then Scorer `python3 tools/learn_from_settle.py --cycle_id … --ticket_id …`.

Local app: `python3 tools/serve_desk.py` → http://127.0.0.1:8765. That is the desk. Lovable is a later public copy of `site/`, not a token the bots wait on.

## 7. OSIRIS GitHub webhook (not a scan)

`POST https://osirisai.live/api/github-webhook` receives **GitHub repository events** and forwards them. It needs `x-hub-signature-256` plus Osiris’s own `GITHUB_WEBHOOK_SECRET` / forward URL. An empty `curl -d '{}'` is not intel and must not run on a 5-minute scan.

Scoring OSIRIS is always:

```bash
python3 tools/osiris.py
```

Do not add this webhook on `colevt/money-making-team` unless Osiris operators give you their webhook secret. This desk does not have it.

## Illegal on both Bots

- Keys, RSA, signed payloads in chat or description
- Asking for or storing a Lovable ingest token
- Live Kraken, Global CLOB
- Ask ≥ 0.80 on Kalshi/Poly; onchain ask ≥ 1.00; sports before first pitch; null `model_cents`
- Filling only one venue when others also passed
- `learn` on quiet
- `git pull` on every scan (use the daily update)
- A third Bot for X, ESPN, or Kraken
- POSTing empty JSON to `https://osirisai.live/api/github-webhook`
