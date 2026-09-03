#!/usr/bin/env python3
"""Execute every passing score this cycle on Kalshi, Polymarket US, and 1inch.

Default is dry-run (unsigned payloads). --live signs with keys from .env.
Never prints keys. Trader runs this after the Scorer emits one score per market.

  python3 tools/execute.py --cycle_id c-xyz
  python3 tools/execute.py --cycle_id c-xyz --live --append
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from append_event import append, load_env, ledger_path  # noqa: E402
from ledger_contract import of_kind, passing_score_for, cycle_quiet, load_events  # noqa: E402
from venues import handler  # noqa: E402

load_env(ROOT / ".env")
MAX_TICKETS = int(os.environ.get("MAX_TICKETS_PER_CYCLE", "12"))
MAX_TOTAL_USD = float(os.environ.get("MAX_TOTAL_USD", "40"))
DEFAULT_USD = float(os.environ.get("TICKET_USD", "1"))


def now_iso() -> str:
    try:
        return datetime.now(ZoneInfo("America/Denver")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def size_of(score: dict) -> float:
    try:
        n = float(score.get("size_usd") or DEFAULT_USD)
    except (TypeError, ValueError):
        n = DEFAULT_USD
    return max(0.01, n)


def pending(events: list[dict], cycle_id: str) -> list[dict]:
    if cycle_quiet(events, cycle_id):
        return []
    filled = {
        (e.get("venue"), e.get("market_id"))
        for e in of_kind(events, cycle_id, "fill")
    }
    out = []
    for score in of_kind(events, cycle_id, "score"):
        if score.get("gate_pass") is not True:
            continue
        key = (score.get("venue"), score.get("market_id"))
        if key in filled:
            continue
        if passing_score_for(events, cycle_id, score["venue"], score["market_id"]) is None:
            continue
        out.append(score)
    return out[:MAX_TICKETS]


def ticket_id_for(score: dict, result: dict) -> str:
    if result.get("tx_hash"):
        return str(result["tx_hash"])[:24]
    if result.get("order_id"):
        return str(result["order_id"])
    return f"{score.get('venue')}-{str(score.get('market_id') or '')[:16]}"


def append_fill_path(cycle_id: str, score: dict, result: dict, size: float) -> None:
    ts = now_iso()
    venue = score["venue"]
    market_id = score["market_id"]
    side = "BUY" if venue == "onchain" else score.get("side") or "YES"
    if venue != "onchain" and side not in {"YES", "NO"}:
        side = "YES"
    tid = ticket_id_for(score, result)
    append({
        "ts": ts, "cycle_id": cycle_id, "kind": "ticket", "bot": "trader",
        "venue": venue, "side": side, "size_usd": size,
        "entry_cents": score.get("book_cents") or score.get("ask", 0) * 100,
        "market_id": market_id, "market": score.get("market") or market_id,
    })
    append({
        "ts": ts, "cycle_id": cycle_id, "kind": "post", "bot": "trader",
        "venue": venue, "market_id": market_id,
        "confirmed_live": True, "under_cap": True,
    })
    append({
        "ts": ts, "cycle_id": cycle_id, "kind": "fill", "bot": "trader",
        "ticket_id": tid, "venue": venue, "side": side, "size_usd": size,
        "entry_cents": score.get("book_cents") or 0,
        "market_id": market_id,
    })


def main() -> None:
    load_env(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Execute all passing tickets this cycle")
    parser.add_argument("--cycle_id", required=True)
    parser.add_argument("--live", action="store_true", help="sign and post; default is dry-run")
    parser.add_argument("--append", action="store_true", help="write ticket/post/fill after a live ok")
    parser.add_argument("--ledger", default=None)
    args = parser.parse_args()
    if args.ledger:
        os.environ["LEDGER_PATH"] = args.ledger
    events = load_events(ledger_path())
    scores = pending(events, args.cycle_id)
    if not scores:
        print(json.dumps({"cycle_id": args.cycle_id, "n": 0, "note": "no passing scores left to fill"}))
        return
    total = 0.0
    results = []
    for score in scores:
        size = size_of(score)
        if total + size > MAX_TOTAL_USD + 1e-9:
            results.append({
                "venue": score.get("venue"),
                "market_id": score.get("market_id"),
                "ok": False,
                "live": False,
                "note": f"skip — total would exceed {MAX_TOTAL_USD:g} USD",
            })
            continue
        ticket = {
            "venue": score.get("venue"),
            "market_id": score.get("market_id"),
            "market": score.get("market"),
            "side": score.get("side") or ("BUY" if score.get("venue") == "onchain" else "YES"),
            "size_usd": size,
            "entry_cents": score.get("book_cents"),
        }
        try:
            result = handler(score["venue"]).execute(ticket, live=args.live)
        except Exception as err:
            result = {"ok": False, "live": False, "venue": score.get("venue"), "note": str(err)[:200]}
        result["size_usd"] = size
        results.append(result)
        if result.get("ok") and not (args.live and not result.get("live")):
            total += size
        if args.live and args.append and result.get("ok") and result.get("live"):
            append_fill_path(args.cycle_id, score, result, size)
    n_ok = sum(1 for r in results if r.get("ok"))
    print(json.dumps({
        "cycle_id": args.cycle_id,
        "live": bool(args.live),
        "n": len(results),
        "ok": n_ok,
        "total_usd": round(total, 4),
        "results": results,
    }, indent=2))
    if args.live and n_ok == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
