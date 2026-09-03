# Connect the two Grok bots (this repo is the control plane)

Cursor is how you make the bots better: edit [scorer.md](scorer.md), [trader.md](trader.md), [CYCLE.md](CYCLE.md), [playbook.md](../playbook.md), push, and the Bots `git pull`. Bot **descriptions** are short pointers ([paste/scorer.txt](paste/scorer.txt), [paste/trader.txt](paste/trader.txt)). Paste those once.

Two Bots only. Unusual Whales, X, ESPN, and Kraken are **feeds the Scorer pulls**, not extra Bots.

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

If you already cloned the nested copy (`money-making-team/money-making-team`), `git pull --ff-only` from the clone root; tools now sit at the repo root. No `.env`. No Origin login.

## 2. Scorer plugins (account-wide)

Settings → Plugins, enable on the **Scorer** (Trader does not need them):

| Plugin | ID | Role |
| --- | --- | --- |
| Unusual Whales | `4021654` | OHLC / flow for the model |
| X | `4022021` | news + lag (must actually pull) |
| Kraken | `4031115` | public ticker / paper only — never `-s trade` |

Trader gets Kalshi + Polymarket US signed-post connectors only. ESPN is a public pull the Scorer does. MCP must be public HTTPS. Local stdio / `localhost` will not attach.

## 3. Paste once into each Bot profile

New → Create new agent (twice). Bot actions → **Edit Profile** → description:

| Bot | `bot` field | Copy this |
| --- | --- | --- |
| Scorer | `scorer` | [paste/scorer.txt](paste/scorer.txt) |
| Trader | `trader` | [paste/trader.txt](paste/trader.txt) |

Save [paste/skill-desk.txt](paste/skill-desk.txt) as the `money-team-desk` skill and enable it on both (Settings → Plugins → Yours). Cursor agents pick up the same skill from [`.agents/skills/money-team-desk/SKILL.md`](../.agents/skills/money-team-desk/SKILL.md).

First messages:

- Scorer: `git pull --ff-only, then read grok/scorer.md and grok/CYCLE.md. Run bash tools/bootstrap.sh if tools/ is missing. Run one ingest+score. Quiet if the gate fails. Do not fill. Ledger is local. Do not ask for Lovable tokens.`
- Trader: `git pull --ff-only, then read grok/trader.md. Fill only if this cycle already has score.gate_pass true. Ledger is local. Do not ask for Lovable tokens.`

## 4. Routines

**Scorer:** every 5 minutes `git pull --ff-only && python3 tools/heartbeat.py --bot scorer`, then one scan from CYCLE.md.

**Trader:** no scan of its own. When Scorer hands over `gate_pass true`, `git pull --ff-only` then ticket → post → fill → mark.

## 5. How tweaks work (Cursor)

1. Open this GitHub repo in Cursor.
2. Edit `grok/scorer.md`, `grok/trader.md`, `grok/CYCLE.md`, or `playbook.md`.
3. Push to `main`.
4. Next cycle the Bot pulls and uses the new file. Do not re-paste the profile unless the pointer text itself changed.

## 6. Check it worked

```bash
git pull --ff-only
python3 tools/test_ledger_contract.py
tail -n 20 ledger/events.jsonl
```

Quiet: `ingest` (six feeds, X actually pulled) + `score` with `model_cents` + `quiet`. Fired: Trader `ticket` → `post` → `fill` → `mark`, later `settle`, then Scorer `python3 tools/learn_from_settle.py --cycle_id …`.

Local app: `python3 tools/serve_desk.py` → http://127.0.0.1:8765. That is the desk. Lovable is a later public copy of `site/`, not a token the bots wait on.

## Illegal on both Bots

- Keys, RSA, signed payloads in chat or description
- Asking for or storing a Lovable ingest token
- Live Kraken, Global CLOB, Onchain as a ticket venue
- Ask ≥ 0.80, sports before first pitch, null `model_cents`
- `learn` on quiet
- A third Bot for X, ESPN, or Kraken
