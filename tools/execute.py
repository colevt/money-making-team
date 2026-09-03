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
from inventory import close as inv_close, open_buy, qty_wei_of, symbol_of  # noqa: E402
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
        (e.get("venue"), e.get("market_id"), e.get("side"))
        for e in of_kind(events, cycle_id, "fill")
    }
    out = []
    for score in of_kind(events, cycle_id, "score"):
        if score.get("gate_pass") is not True:
            continue
        venue = score.get("venue")
        side = score.get("side") or ("BUY" if venue == "onchain" else "YES")
        key = (venue, score.get("market_id"), side)
        if key in filled:
            continue
        if passing_score_for(events, cycle_id, venue, score["market_id"], side) is None:
            continue
        out.append(score)
    return out[:MAX_TICKETS]


def ticket_id_for(score: dict, result: dict) -> str:
    if result.get("tx_hash"):
        return str(result["tx_hash"])[:24]
    if result.get("order_id"):
        return str(result["order_id"])
    return f"{score.get('venue')}-{str(score.get('market_id') or '')[:16]}"


def side_of(score: dict) -> str:
    venue = score.get("venue")
    side = str(score.get("side") or "").upper()
    if venue == "onchain":
        return side if side in {"BUY", "SELL"} else "BUY"
    if side in {"YES", "NO"}:
        return side
    return "YES"


def append_fill_path(cycle_id: str, score: dict, result: dict, size: float) -> None:
    ts = now_iso()
    venue = score["venue"]
    market_id = score["market_id"]
    side = side_of(score)
    tid = ticket_id_for(score, result)
    entry = score.get("book_cents") or score.get("ask", 0) * 100
    append({
        "ts": ts, "cycle_id": cycle_id, "kind": "ticket", "bot": "trader",
        "venue": venue, "side": side, "size_usd": size,
        "entry_cents": entry,
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
    if venue == "onchain":
        _sync_inventory(score, result, size, tid, cycle_id, side)


def _last_px(score: dict) -> float:
    feats = score.get("features") or {}
    for key in ("oneinch", "last"):
        try:
            n = float(feats.get(key) or 0)
        except (TypeError, ValueError):
            n = 0.0
        if n > 0:
            return n
    return 0.0


def _sync_inventory(score: dict, result: dict, size: float, tid: str, cycle_id: str, side: str) -> None:
    symbol = symbol_of(score.get("market_id") or score.get("market"))
    if not symbol:
        return
    px = _last_px(score)
    if side == "BUY":
        qty = result.get("dst_amount") or result.get("qty_wei")
        try:
            qty_wei = int(str(qty))
        except (TypeError, ValueError):
            qty_wei = 0
        if qty_wei <= 0:
            return
        open_buy(
            symbol,
            qty_wei=qty_wei,
            entry_px=px or 0.0,
            size_usd=size,
            ticket_id=tid,
            cycle_id=cycle_id,
            market_id=score.get("market_id") or "",
        )
        return
    if side == "SELL":
        inv_close(symbol, exit_px=px or None)


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
        side = side_of(score)
        if side != "SELL" and total + size > MAX_TOTAL_USD + 1e-9:
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
            "side": side,
            "size_usd": size,
            "entry_cents": score.get("book_cents"),
        }
        if score.get("venue") == "onchain" and score.get("book_kind") == "crypto_scalp":
            ticket["slippage"] = os.environ.get("SCALP_SLIPPAGE", "0.3")
        if score.get("venue") == "onchain" and side == "SELL":
            symbol = symbol_of(score.get("market_id") or score.get("market"))
            qty = qty_wei_of(symbol) if symbol else None
            if qty:
                ticket["qty_wei"] = qty
        try:
            result = handler(score["venue"]).execute(ticket, live=args.live)
        except Exception as err:
            result = {"ok": False, "live": False, "venue": score.get("venue"), "note": str(err)[:200]}
        result["size_usd"] = size
        results.append(result)
        if result.get("ok") and not (args.live and not result.get("live")):
            if side != "SELL":
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
