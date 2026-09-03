#!/usr/bin/env python3
"""Rolling crypto tape: Kraken bars + 1inch quotes + UW/X flow.

This is the model's short-horizon memory. Grok does not keep chat memory
across scans; ledger/crypto_tape.json does.

  python3 tools/crypto_tape.py
  python3 tools/crypto_tape.py --json
  python3 tools/crypto_tape.py --flow   # stdin JSON {ETH:{side:buy,...},...}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("CRYPTO_TAPE_PATH", ROOT / "ledger" / "crypto_tape.json"))
ONEINCH_SNAP = ROOT / "ledger" / "oneinch_snapshot.json"
X_TAPE = ROOT / "ledger" / "x_tape.json"
KEEP_BARS = 24
SYMBOLS = {
    "BTC": {"kraken": "XBTUSD", "alt": ("XXBTZUSD", "XBTUSD")},
    "ETH": {"kraken": "ETHUSD", "alt": ("XETHZUSD", "ETHUSD")},
    "SOL": {"kraken": "SOLUSD", "alt": ("SOLUSD",)},
}
UA = "money-team-crypto-tape/1"


def now_iso() -> str:
    try:
        return datetime.now(ZoneInfo("America/Denver")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tape_path() -> Path:
    return Path(os.environ.get("CRYPTO_TAPE_PATH", OUT))


def load_tape(path: Path | None = None) -> dict:
    p = path or tape_path()
    if not p.is_file():
        return {"ts": None, "symbols": {}}
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {"ts": None, "symbols": {}}
    if not isinstance(data, dict):
        return {"ts": None, "symbols": {}}
    data.setdefault("symbols", {})
    return data


def save_tape(tape: dict, path: Path | None = None) -> Path:
    p = path or tape_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(tape, indent=2) + "\n")
    return p


def _f(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def bars_from_ohlc(rows: list) -> list[dict]:
    """Kraken OHLC row: time, open, high, low, close, vwap, volume, count."""
    out = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 7:
            continue
        close = _f(row[4])
        high = _f(row[2])
        low = _f(row[3])
        if not close or not high or not low:
            continue
        vol = _f(row[6]) or 0.0
        vwap = _f(row[5]) or close
        out.append({
            "t": int(row[0]) if str(row[0]).isdigit() else row[0],
            "o": _f(row[1]) or close,
            "h": high,
            "l": low,
            "c": close,
            "vwap": vwap,
            "v": vol,
        })
    return out[-KEEP_BARS:]


def summarize(bars: list[dict], lookback: int = 12) -> dict:
    window = [b for b in bars if b.get("c")][-lookback:]
    if not window:
        return {"ok": False, "note": "no bars"}
    last = float(window[-1]["c"])
    highs = [float(b["h"]) for b in window]
    lows = [float(b["l"]) for b in window]
    closes = [float(b["c"]) for b in window]
    vols = [float(b.get("v") or 0) for b in window]
    local_high = max(highs)
    local_low = min(lows)
    vol_sum = sum(vols)
    if vol_sum > 0:
        vwap = sum(float(b.get("vwap") or b["c"]) * float(b.get("v") or 0) for b in window) / vol_sum
    else:
        vwap = sum(closes) / len(closes)
    dip_pct = (vwap - last) / vwap * 100.0 if vwap else 0.0
    bounce_pct = (last - local_low) / vwap * 100.0 if vwap else 0.0
    ext_high_pct = (local_high - last) / vwap * 100.0 if vwap else 0.0
    span = local_high - local_low
    at_low = last <= local_low * 1.0015
    at_high = last >= local_high * 0.9985
    return {
        "ok": True,
        "last": last,
        "vwap": round(vwap, 8),
        "local_low": local_low,
        "local_high": local_high,
        "range_pct": round(span / vwap * 100.0, 4) if vwap else 0.0,
        "dip_pct": round(dip_pct, 4),
        "bounce_pct": round(bounce_pct, 4),
        "ext_high_pct": round(ext_high_pct, 4),
        "at_low": at_low,
        "at_high": at_high,
        "n": len(window),
    }


def _http_json(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def fetch_kraken_ohlc(pair: str, interval: int = 1) -> list:
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}"
    payload = _http_json(url)
    result = payload.get("result") or {}
    rows = []
    for key, val in result.items():
        if key == "last":
            continue
        if isinstance(val, list):
            rows = val
            break
    return rows


def load_oneinch_prices(path: Path | None = None) -> dict:
    p = path or ONEINCH_SNAP
    if not p.is_file():
        return {}
    try:
        snap = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    quotes = snap.get("quotes") or {}
    out = {}
    for name, row in quotes.items():
        if isinstance(row, dict) and row.get("ok") and row.get("price"):
            px = _f(row["price"])
            if px:
                out[name] = px
    return out


def load_x_flow(path: Path | None = None) -> dict[str, int]:
    p = path or X_TAPE
    if not p.is_file():
        return {}
    try:
        tape = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    last = tape.get("last") or {}
    signs: dict[str, int] = {}
    for t in last.get("accelerating") or last.get("fresh_tickers") or last.get("lag_candidates") or []:
        tok = str(t).upper()
        if tok in SYMBOLS:
            signs[tok] = 1
    for t in last.get("priced_in") or []:
        tok = str(t).upper()
        if tok in SYMBOLS:
            signs[tok] = min(signs.get(tok, 0), 0)
    return signs


def _flow_sign(row) -> int:
    if not isinstance(row, dict):
        return 0
    side = str(row.get("side") or row.get("flow") or "").lower()
    if side in {"buy", "bid", "sweep_buy", "up"}:
        return 1
    if side in {"sell", "ask", "sweep_sell", "down"}:
        return -1
    try:
        n = float(row.get("sign") or row.get("net") or 0)
    except (TypeError, ValueError):
        n = 0.0
    if n > 0:
        return 1
    if n < 0:
        return -1
    return 0


def merge_symbol(
    bars: list[dict],
    *,
    oneinch_px: float | None = None,
    flow_sign: int = 0,
    x_sign: int = 0,
    lookback: int = 12,
) -> dict:
    stats = summarize(bars, lookback=lookback)
    if not stats.get("ok"):
        return stats
    last = float(stats["last"])
    cheap_vs_inch = None
    if oneinch_px:
        cheap_vs_inch = round((last - float(oneinch_px)) / last * 100.0, 4)
        stats["oneinch"] = float(oneinch_px)
        stats["oneinch_cheap_pct"] = cheap_vs_inch
    stats["flow_sign"] = int(flow_sign)
    stats["x_sign"] = int(x_sign)
    stats["bars"] = bars[-KEEP_BARS:]
    return stats


def update(
    *,
    flow: dict | None = None,
    lookback: int = 12,
    fetch=None,
    oneinch_prices: dict | None = None,
    x_signs: dict | None = None,
    prior: dict | None = None,
) -> dict:
    fetch = fetch or fetch_kraken_ohlc
    prior = prior if prior is not None else load_tape()
    oneinch_prices = oneinch_prices if oneinch_prices is not None else load_oneinch_prices()
    x_signs = x_signs if x_signs is not None else load_x_flow()
    flow = flow or {}
    symbols = {}
    notes = []
    any_ok = False
    for name, meta in SYMBOLS.items():
        bars = []
        try:
            rows = fetch(meta["kraken"])
            bars = bars_from_ohlc(rows)
        except Exception as err:
            old = ((prior.get("symbols") or {}).get(name) or {}).get("bars") or []
            bars = old
            notes.append(f"{name} kraken {str(err)[:80]}")
        if not bars:
            old = ((prior.get("symbols") or {}).get(name) or {}).get("bars") or []
            bars = old
        fsign = _flow_sign(flow.get(name) or {})
        row = merge_symbol(
            bars,
            oneinch_px=oneinch_prices.get(name),
            flow_sign=fsign,
            x_sign=int(x_signs.get(name) or 0),
            lookback=lookback,
        )
        row["symbol"] = name
        symbols[name] = row
        if row.get("ok"):
            any_ok = True
            bits = [f"{name} {row['last']:g}", f"dip {row['dip_pct']:+.2f}"]
            if row.get("at_low"):
                bits.append("LOW")
            if row.get("at_high"):
                bits.append("HIGH")
            if row.get("flow_sign"):
                bits.append("flow+" if row["flow_sign"] > 0 else "flow-")
            notes.append(" ".join(bits))
        else:
            notes.append(f"{name} {row.get('note') or 'no bars'}")
    tape = {
        "ts": now_iso(),
        "ok": any_ok,
        "lookback": lookback,
        "symbols": symbols,
        "note": " · ".join(notes) if notes else "no crypto tape",
        "ingest": {
            "ok": any_ok,
            "lag_s": 0,
            "note": " · ".join(notes) if notes else "no crypto tape",
        },
    }
    save_tape(tape)
    return tape


def main() -> None:
    parser = argparse.ArgumentParser(description="Rolling Kraken + 1inch + flow tape")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--flow", action="store_true", help="stdin JSON of UW/flow signs")
    parser.add_argument("--lookback", type=int, default=12)
    args = parser.parse_args()
    flow = None
    if args.flow:
        raw = sys.stdin.read()
        if raw.strip():
            flow = json.loads(raw)
    tape = update(flow=flow, lookback=args.lookback)
    ingest = tape.get("ingest") or {}
    if args.json:
        print(json.dumps(ingest))
    else:
        flag = "OK" if ingest.get("ok") else "GAP"
        print(f"{flag} crypto_tape  {ingest.get('note')}", file=sys.stderr)
        print(json.dumps(ingest))
    if not ingest.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
