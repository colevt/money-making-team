# Connect the two Grok bots (this repo is the control plane)

Tweaks belong in git: [scorer.md](scorer.md), [trader.md](trader.md), [CYCLE.md](CYCLE.md), [playbook.md](../playbook.md). Bot **descriptions** are short pointers ([paste/scorer.txt](paste/scorer.txt), [paste/trader.txt](paste/trader.txt)). After you paste those once, edit files here and the Bots `git pull` them.

Two Bots only. Unusual Whales, X, ESPN, and Kraken are **feeds the Scorer pulls**, not extra Bots. Do not create a news bot, ESPN bot, or crypto bot.

Grok Bot cannot see `localhost` on your laptop. It needs this repo on **its** computer plus plugins. Never put the ingest token or venue keys in a Bot profile, chat, or share link.

PR with these files: https://cursor.com/codebase/coleb/money-making-team/pull/3

**Clone URL (Cursor Origin):** `https://origin.cursor.com/coleb/money-making-team.git`  
Branch until merge: `cursor/grok-bots-better-eb3a`

Origin cannot be made public (beta only has Internal / Private). Anonymous `git clone` returns **401**. Logged-in Cursor teammates clone after `origin auth login`. Grok Bot’s cloud computer has no Cursor login, so it needs a **public GitHub** mirror (create an empty public repo, then this desk can push to it) **or** a read-only clone token stored only in `.env` on the Bot computer — never in the Bot description.

Official UI: [Create and manage Bots](https://docs.x.ai/grok-bot/bots) · [cursor.com/bot/onboarding](https://cursor.com/bot/onboarding)

## 1. Clone this repo on the Bot computer (once)

If you have a public GitHub mirror, clone that. Otherwise, on a machine that is logged into Origin:

```text
git clone https://origin.cursor.com/coleb/money-making-team.git
cd money-making-team
git checkout cursor/grok-bots-better-eb3a
cp .env.example .env
# Fill LOVABLE_INGEST_URL and LOVABLE_INGEST_TOKEN from Lovable secrets. Do not print .env.
python3 tools/test_ledger_contract.py
```

If local tools stay on `never`, POST cycle JSON to `LOVABLE_INGEST_URL` with the Bearer token from `.env`. Still never paste that token into a Bot description.

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

Enable the `money-team-desk` skill on both (Settings → Plugins → Yours).

First messages:

- Scorer: `git pull, then read grok/scorer.md and grok/CYCLE.md. Run one ingest+score. Quiet if the gate fails. Do not fill.`
- Trader: `git pull, then read grok/trader.md. Fill only if this cycle already has score.gate_pass true.`

## 4. Routines

**Scorer:** every 5 minutes `git pull --ff-only && python3 tools/heartbeat.py --bot scorer`, then one scan from CYCLE.md.

**Trader:** no scan of its own. When Scorer hands over `gate_pass true`, `git pull --ff-only` then ticket → post → fill → mark.

## 5. How tweaks work

1. Edit `grok/scorer.md`, `grok/trader.md`, `grok/CYCLE.md`, or `playbook.md` in this repo.
2. Push.
3. Next cycle the Bot pulls and uses the new file. Do not re-paste the profile unless the pointer text itself changed.

## 6. Check it worked

```bash
git pull --ff-only
tail -n 20 ledger/events.jsonl
```

Quiet: `ingest` (six feeds, X actually pulled) + `score` with `model_cents` + `quiet`. Fired: Trader `ticket` → `post` → `fill` → `mark`, later `settle`, then Scorer `python3 tools/learn_from_settle.py --cycle_id …`.

## Illegal on both Bots

- Keys, ingest token, RSA, signed payloads in chat or description
- Live Kraken, Global CLOB, Onchain as a ticket venue
- Ask ≥ 0.80, sports before first pitch, null `model_cents`
- `learn` on quiet
- A third Bot for X, ESPN, or Kraken
