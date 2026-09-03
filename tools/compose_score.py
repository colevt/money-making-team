#!/usr/bin/env python3
"""Turn the live tape + learned weights into scores. This is the model.

Sports / Kalshi 15m scores still come from the Scorer. Onchain BUY-low / SELL-high
scalps must come from here so weights actually move the next ticket.

  python3 tools/compose_score.py --cycle_id …
  python3 tools/compose_score.py --cycle_id … --append
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

from dexscreener import (  # noqa: E402
    fee_floor_ok,
    load_snapshot as load_dex,
    volume_decay_exit,
)
from inventory import MARKETS, get as inv_get, load as inv_load  # noqa: E402
from ledger_contract import (  # noqa: E402
    DEFAULT_WEIGHTS,
    GATE_PCT,
    SCALP_GATE_PCT,
    WEIGHT_KEYS,
    gate_pass_value,
    load_books,
)

WEIGHTS_PATH = ROOT / "ledger" / "weights.json"
TAPE_PATH = ROOT / "ledger" / "crypto_tape.json"
DEFAULT_USD = float(os.environ.get("TICKET_USD", "1"))
DEFAULT_SCALP = {
    "min_dip_pct": SCALP_GATE_PCT,
    "take_pct": 0.40,
    "stop_pct": 0.45,
    "lookback": 12,
    "max_hold_cycles": 8,
}


def now_iso() -> str:
    try:
        return datetime.now(ZoneInfo("America/Denver")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def scalp_params(books: dict | None = None) -> dict:
    books = books if books is not None else load_books(WEIGHTS_PATH)
    raw = books.get("scalp") or {}
    out = dict(DEFAULT_SCALP)
    for k, v in DEFAULT_SCALP.items():
        try:
            if k in raw:
                out[k] = type(v)(raw[k])
        except (TypeError, ValueError):
            continue
    return out


def _weights(books: dict) -> dict:
    w = dict(DEFAULT_WEIGHTS["crypto_scalp"])
    got = (books.get("books") or {}).get("crypto_scalp") or {}
    for k in WEIGHT_KEYS:
        if k in got:
            try:
                w[k] = float(got[k])
            except (TypeError, ValueError):
                pass
    return w


def fair_px(row: dict, weights: dict) -> float:
    last = float(row["last"])
    vwap = float(row.get("vwap") or last)
    inch = float(row["oneinch"]) if row.get("oneinch") else vwap
    flow_px = vwap if int(row.get("flow_sign") or 0) >= 0 else last
    x_px = vwap if int(row.get("x_sign") or 0) >= 0 else last
    return (
        weights["crypto"] * vwap
        + weights["book"] * inch
        + weights["uw"] * flow_px
        + weights["x"] * x_px
        + weights["espn"] * vwap
    )


def cents_vs_fair(px: float, fair: float) -> dict | None:
    if px <= 0 or fair <= 0:
        return None
    book = min(100.0, round(px / fair * 100.0, 2))
    model = 100.0
    edge = round(model - book, 2)
    ask = round(book / 100.0, 4)
    return {
        "model_cents": model,
        "book_cents": book,
        "edge_pct": edge,
        "ask": ask,
        "bid": ask,
    }


def feeds_used_for(row: dict, side: str) -> list[str]:
    used = ["crypto", "book"]
    if int(row.get("flow_sign") or 0) != 0:
        used.append("uw")
    if int(row.get("x_sign") or 0) != 0:
        used.append("x")
    if side == "SELL":
        used.append("book")
    out = []
    for k in used:
        if k not in out:
            out.append(k)
    return out


def buy_ok(
    row: dict,
    params: dict,
    held: bool,
    *,
    size_usd: float = DEFAULT_USD,
    dex_row: dict | None = None,
) -> tuple[bool, str]:
    if held:
        return False, "already long — wait for SELL"
    if not row.get("ok"):
        return False, row.get("note") or "no tape"
    if int(row.get("flow_sign") or 0) < 0:
        return False, "flow dumping — do not catch the knife"
    dip = float(row.get("dip_pct") or 0)
    min_dip = float(params.get("min_dip_pct") or SCALP_GATE_PCT)
    at_low = bool(row.get("at_low"))
    if row.get("oneinch") and row.get("last"):
        if float(row["oneinch"]) > float(row["last"]) * 1.004:
            return False, "1inch rich vs Kraken — skip"
    if dip >= min_dip:
        last = float(row.get("last") or 0)
        inch = float(row["oneinch"]) if row.get("oneinch") else None
        ok_fee, fee_why, _ = fee_floor_ok(
            size_usd,
            oneinch_px=inch,
            fair_px=last if last > 0 else None,
            scalp_gate_pct=SCALP_GATE_PCT,
        )
        if not ok_fee:
            return False, fee_why
        why = f"local low, dip {dip:.2f}% vs VWAP" if at_low else f"dip {dip:.2f}% vs VWAP"
        if fee_why and "fee floor ok" in fee_why:
            why = f"{why}; {fee_why}"
        if dex_row and dex_row.get("ok"):
            liq = dex_row.get("liquidity_usd")
            ratio = dex_row.get("volume_ratio")
            if liq is not None and ratio is not None:
                why = f"{why} (liq ${liq:,.0f} vol {ratio:.2f})"
        return True, why
    return False, f"dip {dip:.2f}% under {min_dip:g}% (at_low={at_low})"


def sell_ok(row: dict, pos: dict, params: dict, *, dex_row: dict | None = None) -> tuple[bool, str]:
    if not pos:
        return False, "flat"
    decay, decay_why = volume_decay_exit(dex_row)
    if decay:
        return True, decay_why
    if not row.get("ok"):
        return False, row.get("note") or "no tape"
    last = float(row["last"])
    try:
        entry = float(pos.get("entry_px") or 0)
    except (TypeError, ValueError):
        entry = 0.0
    if entry <= 0:
        return False, "no entry"
    move = (last / entry - 1.0) * 100.0
    take = float(params.get("take_pct") or 0.40)
    stop = float(params.get("stop_pct") or 0.45)
    if move >= take or row.get("at_high"):
        return True, f"take {move:+.2f}% (target {take:g}%)" if move >= take else "local high"
    if move <= -stop:
        return True, f"stop {move:+.2f}% (max {stop:g}%)"
    return False, f"hold {move:+.2f}% (take {take:g} / stop {stop:g})"


def score_event(
    *,
    cycle_id: str,
    symbol: str,
    side: str,
    row: dict,
    weights: dict,
    reason: str,
    size_usd: float,
    ts: str | None = None,
    entry_px: float | None = None,
    dex_features: dict | None = None,
) -> dict | None:
    last = float(row.get("oneinch") or row.get("last") or (dex_features or {}).get("price_usd") or 0)
    if last <= 0:
        return None
    if side == "BUY":
        fair = fair_px(row, weights)
        px = min(last, float(row["last"]))
        encoded = cents_vs_fair(px, fair)
    else:
        ref = float(entry_px or row.get("vwap") or last)
        encoded = cents_vs_fair(ref, last) if last >= ref else cents_vs_fair(last, last * (1 + SCALP_GATE_PCT / 100.0))
        # stop: encode |move| so a 0.45% loss still clears the 0.35 scalp gate
        if encoded and encoded["edge_pct"] < SCALP_GATE_PCT:
            move = abs(last / ref - 1.0) * 100.0 if ref else 0.0
            book = min(100.0, round(100.0 - max(move, SCALP_GATE_PCT), 2))
            encoded = {
                "model_cents": 100.0,
                "book_cents": book,
                "edge_pct": round(100.0 - book, 2),
                "ask": round(book / 100.0, 4),
                "bid": round(book / 100.0, 4),
            }
    if not encoded:
        return None
    market_id = MARKETS[symbol]
    event = {
        "ts": ts or now_iso(),
        "cycle_id": cycle_id,
        "kind": "score",
        "bot": "scorer",
        "venue": "onchain",
        "side": side,
        "market_id": market_id,
        "market": f"{symbol} scalp",
        "book_kind": "crypto_scalp",
        "feeds_used": feeds_used_for(row, side),
        "weights": dict(weights),
        "size_usd": size_usd,
        "reason": reason,
        "features": {
            "last": row.get("last"),
            "vwap": row.get("vwap"),
            "local_low": row.get("local_low"),
            "local_high": row.get("local_high"),
            "dip_pct": row.get("dip_pct"),
            "oneinch": row.get("oneinch"),
            "flow_sign": row.get("flow_sign"),
            "x_sign": row.get("x_sign"),
            "at_low": row.get("at_low"),
            "at_high": row.get("at_high"),
            "liquidity_usd": (dex_features or {}).get("liquidity_usd"),
            "volume_ratio": (dex_features or {}).get("volume_ratio"),
            "volume_decay": (dex_features or {}).get("volume_decay"),
            "fee_floor": (dex_features or {}).get("fee_floor"),
        },
        **encoded,
    }
    event["gate_pass"] = gate_pass_value(event)
    return event


def compose(
    cycle_id: str,
    *,
    tape: dict | None = None,
    books: dict | None = None,
    inventory: dict | None = None,
    dex: dict | None = None,
    size_usd: float | None = None,
    ts: str | None = None,
) -> dict:
    tape = tape if tape is not None else load_json(Path(os.environ.get("CRYPTO_TAPE_PATH", TAPE_PATH)))
    books = books if books is not None else load_books(WEIGHTS_PATH)
    inventory = inventory if inventory is not None else inv_load()
    dex = dex if dex is not None else load_dex()
    weights = _weights(books)
    params = scalp_params(books)
    size = float(size_usd if size_usd is not None else DEFAULT_USD)
    scores = []
    skipped = []
    for symbol in MARKETS:
        row = (tape.get("symbols") or {}).get(symbol) or {}
        dex_row = (dex.get("symbols") or {}).get(symbol) or {}
        pos = inv_get(symbol, inventory)
        if pos:
            ok, why = sell_ok(row, pos, params, dex_row=dex_row)
            if ok:
                ev = score_event(
                    cycle_id=cycle_id, symbol=symbol, side="SELL", row=row,
                    weights=weights, reason=why, size_usd=float(pos.get("size_usd") or size),
                    ts=ts, entry_px=pos.get("entry_px"),
                    dex_features=dex_row,
                )
                if ev:
                    scores.append(ev)
                else:
                    skipped.append({"symbol": symbol, "side": "SELL", "note": "encode fail"})
            else:
                skipped.append({"symbol": symbol, "side": "SELL", "note": why})
            continue
        ok, why = buy_ok(row, params, held=False, size_usd=size, dex_row=dex_row)
        if not ok:
            skipped.append({"symbol": symbol, "side": "BUY", "note": why})
            continue
        _, _, fee_floor = fee_floor_ok(
            size,
            oneinch_px=float(row["oneinch"]) if row.get("oneinch") else None,
            fair_px=float(row["last"]) if row.get("last") else None,
            scalp_gate_pct=SCALP_GATE_PCT,
        )
        dex_feat = dict(dex_row) if dex_row else {}
        if fee_floor.get("ok"):
            dex_feat["fee_floor"] = fee_floor
        ev = score_event(
            cycle_id=cycle_id, symbol=symbol, side="BUY", row=row,
            weights=weights, reason=why, size_usd=size, ts=ts,
            dex_features=dex_feat or None,
        )
        if ev and ev.get("gate_pass"):
            scores.append(ev)
        elif ev:
            skipped.append({"symbol": symbol, "side": "BUY", "note": f"edge {ev.get('edge_pct')} under scalp gate"})
        else:
            skipped.append({"symbol": symbol, "side": "BUY", "note": why})
    return {
        "cycle_id": cycle_id,
        "book_kind": "crypto_scalp",
        "gate_pct": SCALP_GATE_PCT,
        "pm_gate_pct": GATE_PCT,
        "params": params,
        "weights": weights,
        "dex_ok": bool(dex.get("ok")),
        "n": len(scores),
        "scores": scores,
        "skipped": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compose onchain scalp scores from tape + weights")
    parser.add_argument("--cycle_id", required=True)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--ledger", default=None)
    args = parser.parse_args()
    if args.ledger:
        os.environ["LEDGER_PATH"] = args.ledger
    out = compose(args.cycle_id)
    if args.append:
        from append_event import append  # noqa: E402
        for score in out["scores"]:
            append(score)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
