#!/usr/bin/env python3
"""Open onchain lots. One position per token. Gitignored JSON.

BUY records qty + entry. SELL closes and returns realized USD.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = Path(os.environ.get("INVENTORY_PATH", ROOT / "ledger" / "inventory.json"))

MARKETS = {
    "ETH": "USDC-WETH",
    "BTC": "USDC-WBTC",
    "SOL": "USDC-SOL",
}
MARKET_TO_SYM = {v: k for k, v in MARKETS.items()}
MARKET_TO_SYM.update({"WETH": "ETH", "WBTC": "BTC", "ETH": "ETH", "BTC": "BTC", "SOL": "SOL"})


def inventory_path() -> Path:
    return Path(os.environ.get("INVENTORY_PATH", PATH))


def symbol_of(market_id: str | None) -> str | None:
    text = str(market_id or "").upper()
    if text in MARKET_TO_SYM:
        return MARKET_TO_SYM[text]
    for name, mid in MARKETS.items():
        if name in text or mid in text:
            return name
        if name == "ETH" and "WETH" in text:
            return "ETH"
        if name == "BTC" and "WBTC" in text:
            return "BTC"
    return None


def load(path: Path | None = None) -> dict:
    p = path or inventory_path()
    if not p.is_file():
        return {"positions": {}}
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {"positions": {}}
    if not isinstance(data, dict):
        return {"positions": {}}
    data.setdefault("positions", {})
    return data


def save(data: dict, path: Path | None = None) -> Path:
    p = path or inventory_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")
    return p


def get(symbol: str, data: dict | None = None) -> dict | None:
    pos = (data or load()).get("positions") or {}
    row = pos.get(symbol)
    return row if isinstance(row, dict) else None


def open_buy(
    symbol: str,
    *,
    qty_wei: int,
    entry_px: float,
    size_usd: float,
    ticket_id: str,
    cycle_id: str,
    market_id: str,
    path: Path | None = None,
) -> dict:
    data = load(path)
    data["positions"][symbol] = {
        "symbol": symbol,
        "market_id": market_id,
        "qty_wei": str(int(qty_wei)),
        "entry_px": float(entry_px),
        "size_usd": float(size_usd),
        "ticket_id": ticket_id,
        "cycle_id": cycle_id,
        "side": "BUY",
    }
    save(data, path)
    return data["positions"][symbol]


def close(symbol: str, *, exit_px: float | None = None, path: Path | None = None) -> dict | None:
    data = load(path)
    pos = (data.get("positions") or {}).pop(symbol, None)
    if not pos:
        return None
    if exit_px and pos.get("entry_px"):
        try:
            entry = float(pos["entry_px"])
            size = float(pos.get("size_usd") or 0)
            pos["exit_px"] = float(exit_px)
            pos["pl_usd"] = round(size * (float(exit_px) / entry - 1.0), 6) if entry else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            pos["pl_usd"] = 0.0
    save(data, path)
    return pos


def qty_wei_of(symbol: str, path: Path | None = None) -> int | None:
    pos = get(symbol, load(path))
    if not pos:
        return None
    try:
        n = int(str(pos.get("qty_wei") or "0"))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None
