#!/usr/bin/env python3
"""DexScreener liquidity + volume for Polygon scalp pairs.

Public API, no key. Deepest polygon pair per token; volume-decay ratio for exits;
fee-floor estimate for small-lot BUY gates.

  python3 tools/dexscreener.py
  python3 tools/dexscreener.py --json
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
OUT = Path(os.environ.get("DEXSCREENER_SNAPSHOT_PATH", ROOT / "ledger" / "dexscreener_snapshot.json"))
ONEINCH_SNAP = ROOT / "ledger" / "oneinch_snapshot.json"
UA = "money-team-dexscreener/1"
BASE = "https://api.dexscreener.com/latest/dex/tokens"
VOLUME_DECAY_THRESHOLD = 0.20
DEFAULT_GAS_UNITS = 350_000  # per swap leg on Polygon
POLYGON_RPC = os.environ.get("POLYGON_RPC", "https://polygon-bor.publicnode.com")

# Polygon token contracts (same as venues/oneinch.py TOKENS).
TOKENS = {
    "ETH": {"address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", "symbol": "WETH"},
    "BTC": {"address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", "symbol": "WBTC"},
    "SOL": {"address": "0xd93f7E271cB87c23AaA73edC008A79646d1F9912", "symbol": "SOL"},
}


def now_iso() -> str:
    try:
        return datetime.now(ZoneInfo("America/Denver")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _f(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _http_json(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _rpc(method: str, params: list):
    req = urllib.request.Request(
        POLYGON_RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        payload = json.loads(resp.read())
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return payload["result"]


def pol_usd() -> float | None:
    url = "https://api.kraken.com/0/public/Ticker?pair=POLUSD"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
    except Exception:
        return None
    row = (payload.get("result") or {}).get("POLUSD") or {}
    c = row.get("c") or []
    return _f(c[0]) if c else None


def gas_price_wei() -> int | None:
    try:
        return int(_rpc("eth_gasPrice", []), 16)
    except Exception:
        return None


def pick_polygon_pair(pairs: list) -> dict | None:
    poly = [p for p in pairs or [] if str(p.get("chainId") or "").lower() == "polygon"]
    if not poly:
        return None
    return max(poly, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))


def volume_ratio(pair: dict) -> float | None:
    vol = pair.get("volume") or {}
    h6 = _f(vol.get("h6"))
    h24 = _f(vol.get("h24"))
    if h6 is None or h24 is None or h24 <= 0:
        return None
    avg_6h = h24 / 4.0
    if avg_6h <= 0:
        return None
    return round(h6 / avg_6h, 4)


def fetch_token(name: str, meta: dict) -> dict:
    addr = meta["address"]
    try:
        payload = _http_json(f"{BASE}/{addr}")
    except Exception as err:
        return {"ok": False, "symbol": name, "address": addr, "note": str(err)[:120]}
    pair = pick_polygon_pair(payload.get("pairs") or [])
    if not pair:
        return {"ok": False, "symbol": name, "address": addr, "note": "no polygon pair"}
    liq = (pair.get("liquidity") or {}).get("usd")
    vol = pair.get("volume") or {}
    ratio = volume_ratio(pair)
    return {
        "ok": True,
        "symbol": name,
        "address": addr,
        "dex_id": pair.get("dexId"),
        "pair_address": pair.get("pairAddress"),
        "price_usd": _f(pair.get("priceUsd")),
        "liquidity_usd": _f(liq),
        "volume_h1": _f(vol.get("h1")),
        "volume_h6": _f(vol.get("h6")),
        "volume_h24": _f(vol.get("h24")),
        "volume_ratio": ratio,
        "volume_decay": ratio is not None and ratio < VOLUME_DECAY_THRESHOLD,
    }


def round_trip_cost(
    size_usd: float,
    *,
    oneinch_px: float | None = None,
    fair_px: float | None = None,
    gas_units: int = DEFAULT_GAS_UNITS,
    gas_wei: int | None = None,
    pol_px: float | None = None,
) -> dict:
    """Gas + spread for a BUY→SELL round trip at size_usd. break_even_pct is move needed to cover costs."""
    if size_usd <= 0:
        return {"ok": False, "note": "size_usd required"}
    gas_wei = gas_wei if gas_wei is not None else gas_price_wei()
    pol_px = pol_px if pol_px is not None else pol_usd()
    gas_usd = 0.0
    if gas_wei and pol_px:
        gas_pol = (gas_units * 2) * gas_wei / 1e18
        gas_usd = round(gas_pol * pol_px, 6)
    spread_pct = 0.001  # 10 bps default when quotes missing
    if oneinch_px and fair_px and fair_px > 0:
        spread_pct = abs(oneinch_px - fair_px) / fair_px
    spread_usd = round(size_usd * spread_pct * 2.0, 6)
    cost_usd = round(gas_usd + spread_usd, 6)
    break_even_pct = round(cost_usd / size_usd * 100.0, 4)
    return {
        "ok": True,
        "size_usd": size_usd,
        "gas_usd": gas_usd,
        "spread_usd": spread_usd,
        "spread_pct": round(spread_pct * 100.0, 4),
        "cost_usd": cost_usd,
        "break_even_pct": break_even_pct,
    }


def fee_floor_ok(
    size_usd: float,
    *,
    oneinch_px: float | None,
    fair_px: float | None,
    scalp_gate_pct: float,
) -> tuple[bool, str, dict]:
    floor = round_trip_cost(size_usd, oneinch_px=oneinch_px, fair_px=fair_px)
    if not floor.get("ok"):
        return True, "", floor
    be = float(floor["break_even_pct"])
    if be > scalp_gate_pct:
        why = (
            f"fee floor break-even {be:.2f}% > scalp gate {scalp_gate_pct:g}% "
            f"(gas ${floor['gas_usd']:.4f} + spread ${floor['spread_usd']:.4f} @ ${size_usd:g})"
        )
        return False, why, floor
    return True, f"fee floor ok break-even {be:.2f}%", floor


def volume_decay_exit(dex_row: dict | None) -> tuple[bool, str]:
    if not dex_row or not dex_row.get("ok"):
        return False, ""
    if dex_row.get("volume_decay"):
        ratio = dex_row.get("volume_ratio")
        return True, f"liquidity decay vol ratio {ratio:.2f} < {VOLUME_DECAY_THRESHOLD:g} — CLOSE"
    return False, ""


def load_snapshot(path: Path | None = None) -> dict:
    p = path or OUT
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def liquidity_note_for_ingest(snap: dict | None = None) -> str:
    snap = snap if snap is not None else load_snapshot()
    if not snap.get("ok"):
        return str(snap.get("ingest", {}).get("note") or "dexscreener unavailable")
    bits = []
    for name in ("ETH", "BTC", "SOL"):
        row = (snap.get("symbols") or {}).get(name) or {}
        if not row.get("ok"):
            continue
        liq = row.get("liquidity_usd")
        ratio = row.get("volume_ratio")
        if liq is not None and ratio is not None:
            bits.append(f"{name} liq ${liq:,.0f} vol6h/h24 {ratio:.2f}")
    return " · ".join(bits) if bits else "dexscreener ok"


def update(*, fetch=None) -> dict:
    fetch = fetch or fetch_token
    symbols = {}
    notes = []
    any_ok = False
    for name, meta in TOKENS.items():
        row = fetch(name, meta)
        symbols[name] = row
        if row.get("ok"):
            any_ok = True
            liq = row.get("liquidity_usd") or 0
            ratio = row.get("volume_ratio")
            tag = " DECAY" if row.get("volume_decay") else ""
            notes.append(f"{name} liq ${liq:,.0f} vol {ratio:.2f}{tag}" if ratio is not None else f"{name} liq ${liq:,.0f}")
        else:
            notes.append(f"{name} {row.get('note') or 'fail'}")
    ingest = {
        "ok": any_ok,
        "lag_s": 0,
        "note": " · ".join(notes) if notes else "dexscreener empty",
    }
    snap = {
        "ts": now_iso(),
        "chain": "polygon",
        "symbols": symbols,
        "volume_decay_threshold": VOLUME_DECAY_THRESHOLD,
        "ingest": ingest,
        "ok": any_ok,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, indent=2) + "\n")
    return snap


def oneinch_fair(symbol: str) -> float | None:
    if not ONEINCH_SNAP.is_file():
        return None
    try:
        snap = json.loads(ONEINCH_SNAP.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    row = (snap.get("quotes") or {}).get(symbol) or {}
    return _f(row.get("fair"))


def main() -> None:
    parser = argparse.ArgumentParser(description="DexScreener Polygon liquidity/volume for scalps")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    snap = update()
    ingest = snap.get("ingest") or {}
    if args.json:
        print(json.dumps(ingest))
    else:
        flag = "OK" if ingest.get("ok") else "GAP"
        print(f"{flag} dexscreener  {ingest.get('note')}", file=sys.stderr)
        print(json.dumps(ingest))
    if not ingest.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
