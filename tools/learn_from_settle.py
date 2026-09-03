#!/usr/bin/env python3
"""After a settle, retune sports or crypto15m weights. Quiet does not call this.

  python3 tools/learn_from_settle.py --cycle_id c-xyz
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from append_event import append, load_env  # noqa: E402
from ledger_contract import (  # noqa: E402
    BOOK_KINDS,
    DEFAULT_WEIGHTS,
    GATE_PCT,
    WEIGHT_KEYS,
    apply_learn,
    last_of,
    load_events,
    of_kind,
    passing_score_for,
    cycle_quiet,
)

WEIGHTS_PATH = ROOT / "ledger" / "weights.json"


def load_books(path: Path) -> dict:
    if path.is_file():
        data = json.loads(path.read_text())
    else:
        data = {}
    books = data.get("books") or {}
    for kind in BOOK_KINDS:
        if kind not in books:
            books[kind] = dict(DEFAULT_WEIGHTS[kind])
    data["books"] = books
    data.setdefault("gate_pct", GATE_PCT)
    data.setdefault("settled", {"sports": 0, "crypto15m": 0})
    return data


def main() -> None:
    load_env(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Retune weights from a settled cycle")
    parser.add_argument("--cycle_id", required=True)
    parser.add_argument("--ticket_id", default=None, help="which settle if this cycle filled more than once")
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--weights", default=str(WEIGHTS_PATH))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.ledger:
        os.environ["LEDGER_PATH"] = args.ledger

    ledger = Path(os.environ.get("LEDGER_PATH", ROOT / "ledger" / "events.jsonl"))
    events = load_events(ledger)
    if cycle_quiet(events, args.cycle_id) is not None and not of_kind(events, args.cycle_id, "settle"):
        raise SystemExit("quiet cycle — weights unchanged, no learn")
    settles = of_kind(events, args.cycle_id, "settle")
    learned = {e.get("ticket_id") for e in of_kind(events, args.cycle_id, "learn") if e.get("ticket_id")}
    settle = None
    if args.ticket_id:
        settle = next((s for s in settles if s.get("ticket_id") == args.ticket_id), None)
    else:
        for s in reversed(settles):
            if s.get("ticket_id") not in learned:
                settle = s
                break
        if settle is None:
            settle = last_of(events, args.cycle_id, "settle")
    if settle is None:
        raise SystemExit(f"no settle for {args.cycle_id}")
    fills = of_kind(events, args.cycle_id, "fill")
    fill = next((f for f in fills if f.get("ticket_id") == settle.get("ticket_id")), None)
    if fill:
        score = passing_score_for(events, args.cycle_id, fill.get("venue"), fill.get("market_id"))
    else:
        score = last_of(events, args.cycle_id, "score")
    if score is None:
        raise SystemExit(f"no score for {args.cycle_id}")
    if settle.get("ticket_id") and settle.get("ticket_id") in learned:
        raise SystemExit(f"learn already recorded for ticket {settle.get('ticket_id')}")
    if not args.ticket_id and last_of(events, args.cycle_id, "learn") and not learned:
        raise SystemExit(f"learn already recorded for {args.cycle_id}")

    book_kind = score.get("book_kind")
    if book_kind not in BOOK_KINDS:
        raise SystemExit("score.book_kind must be sports or crypto15m")
    used = score.get("feeds_used") or list(WEIGHT_KEYS)
    prior = load_books(Path(args.weights))
    before = dict(prior["books"][book_kind])
    after, deltas = apply_learn(before, used, settle["result"], book_kind)
    notes = (
        f"{settle['result']} {book_kind} ticket {settle.get('ticket_id')}. "
        f"{'+' if settle['result'] == 'WON' else '-'}0.02 on {', '.join(deltas) or 'none'}; "
        f"espn frozen on crypto15m, crypto frozen on sports. Gate stays {GATE_PCT:g}%."
    )
    event = {
        "ts": settle.get("ts"),
        "cycle_id": args.cycle_id,
        "kind": "learn",
        "bot": "scorer",
        "book_kind": book_kind,
        "weight_deltas": deltas,
        "weights": after,
        "weights_before": before,
        "gate_pct": GATE_PCT,
        "gate_notes": notes,
        "result": settle["result"],
        "feeds_used": used,
        "ticket_id": settle.get("ticket_id"),
        "venue": (fill or score).get("venue"),
        "market_id": (fill or score).get("market_id"),
    }
    if args.dry_run:
        print(json.dumps(event, indent=2))
        return
    prior["books"][book_kind] = after
    prior["settled"][book_kind] = int(prior["settled"].get(book_kind) or 0) + 1
    prior["gate_pct"] = GATE_PCT
    prior["last_cycle"] = args.cycle_id
    Path(args.weights).write_text(json.dumps(prior, indent=2) + "\n")
    append(event)
    print(json.dumps({"book_kind": book_kind, "deltas": deltas, "weights": after}))


if __name__ == "__main__":
    main()
