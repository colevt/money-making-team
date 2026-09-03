"""Polygon 1inch classic swap (v6.1). Quote is a scoring book; --live signs a swap.

Wallet 0xcE01…49BF spends native USDC. POL is gas only. Keys stay in .env:

  ONEINCH_API_KEY
  ONCHAIN_PRIVATE_KEY   # only for --live
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .common import env, http_json, load_env, qs

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
OUT = ROOT / "ledger" / "oneinch_snapshot.json"
CHAIN = 137
BASE = os.environ.get("ONEINCH_URL", "https://api.1inch.com/swap/v6.1/137").rstrip("/")
RPC = os.environ.get("POLYGON_RPC", "https://polygon-bor.publicnode.com")
WALLET = "0xcE01ddD2141e4efDB929265A538981043b7449BF"
USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
QUOTE_USDC = 10_000_000  # 10 USDC, 6 decimals
SLIPPAGE = os.environ.get("ONEINCH_SLIPPAGE", "1")

# Polygon tokens we can actually swap from USDC.
TOKENS = {
    "ETH": {"address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", "decimals": 18, "symbol": "WETH"},
    "BTC": {"address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", "decimals": 8, "symbol": "WBTC"},
    "SOL": {"address": "0xd93f7E271cB87c23AaA73edC008A79646d1F9912", "decimals": 9, "symbol": "SOL"},
}


def now_iso() -> str:
    try:
        return datetime.now(ZoneInfo("America/Denver")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _headers() -> dict:
    key = env("ONEINCH_API_KEY", "ONEINCH_KEY", "DEV_PORTAL_API_KEY")
    hdrs = {"Authorization": f"Bearer {key}"} if key else {}
    return hdrs


def has_key() -> bool:
    return bool(env("ONEINCH_API_KEY", "ONEINCH_KEY", "DEV_PORTAL_API_KEY"))


def quote(src: str, dst: str, amount: int, timeout: int = 15) -> dict:
    if not has_key():
        return {"ok": False, "note": "no ONEINCH_API_KEY"}
    url = qs(f"{BASE}/quote", {"src": src, "dst": dst, "amount": str(amount)})
    payload = http_json(url, headers=_headers(), timeout=timeout)
    if payload.get("ok") is False or payload.get("status") in (401, 403, 429):
        return {
            "ok": False,
            "note": f"1inch quote {payload.get('status') or 'fail'}",
            "error": str(payload.get("error") or payload.get("description") or "")[:200],
        }
    dst_amount = payload.get("dstAmount")
    if dst_amount is None:
        return {"ok": False, "note": "no quote", "raw_keys": list(payload)[:8]}
    return {"ok": True, "dst_amount": str(dst_amount), "src_amount": str(amount), "gas": payload.get("gas")}


def implied_dst_price_usd(dst_amount: str, dst_decimals: int, usdc_in: int = QUOTE_USDC) -> float | None:
    try:
        got = int(dst_amount)
    except (TypeError, ValueError):
        return None
    if got <= 0:
        return None
    usd = usdc_in / 1e6
    tokens = got / (10 ** dst_decimals)
    if tokens <= 0:
        return None
    return usd / tokens


def edge_vs_fair(oneinch_price: float, fair: float) -> dict:
    """Buy token on 1inch. book_cents = 1inch/fair * 100. model_cents = 100."""
    if fair <= 0 or oneinch_price <= 0:
        return {"ok": False}
    book = min(100.0, round(oneinch_price / fair * 100.0, 2))
    model = 100.0
    edge = round(model - book, 2)
    ask = round(book / 100.0, 4)
    return {
        "ok": True,
        "model_cents": model,
        "book_cents": book,
        "edge_pct": edge,
        "ask": ask,
        "bid": ask,
        "oneinch_price": oneinch_price,
        "fair": fair,
    }


def pull_quotes(fairs: dict | None = None) -> dict:
    """Quote USDC → ETH/BTC/SOL. fairs is {ETH: 2389.0, ...} from Kraken/UW."""
    load_env()
    fairs = fairs or {}
    rows = {}
    notes = []
    any_ok = False
    for name, meta in TOKENS.items():
        q = quote(USDC, meta["address"], QUOTE_USDC)
        if not q.get("ok"):
            rows[name] = {"ok": False, "note": q.get("note") or "no quote"}
            notes.append(f"{name} {q.get('note') or 'fail'}")
            continue
        px = implied_dst_price_usd(q["dst_amount"], meta["decimals"])
        fair = fairs.get(name)
        scored = edge_vs_fair(px, float(fair)) if (px and fair) else None
        rows[name] = {
            "ok": True,
            "symbol": meta["symbol"],
            "dst": meta["address"],
            "price": px,
            "fair": fair,
            "dst_amount": q["dst_amount"],
            "edge": None if not scored else scored,
        }
        any_ok = True
        if scored:
            notes.append(f"{name} 1inch {px:.4g} vs {fair:g} edge {scored['edge_pct']:+.1f}")
        elif px:
            notes.append(f"{name} 1inch {px:.4g}")
    try:
        from dexscreener import liquidity_note_for_ingest, load_snapshot, update as dex_update  # noqa: E402

        dex = load_snapshot()
        if not dex.get("ok"):
            try:
                dex = dex_update()
            except SystemExit:
                pass
        liq_note = liquidity_note_for_ingest(dex)
        if liq_note and liq_note != "dexscreener unavailable":
            notes.append(liq_note)
    except Exception as err:
        notes.append(f"dex {str(err)[:40]}")
    note = " · ".join(notes) if notes else ("no ONEINCH_API_KEY" if not has_key() else "no quote")
    ingest = {
        "ok": any_ok if has_key() else False,
        "lag_s": 0,
        "note": note,
    }
    if not has_key():
        ingest["ok"] = False
        if note != "no ONEINCH_API_KEY":
            ingest["note"] = f"no ONEINCH_API_KEY · {note}"
        else:
            ingest["note"] = "no ONEINCH_API_KEY"
    snap = {
        "ts": now_iso(),
        "wallet": WALLET,
        "usdc": USDC,
        "chain": CHAIN,
        "quotes": rows,
        "ingest": ingest,
        "ok": ingest["ok"],
    }
    OUT.write_text(json.dumps(snap, indent=2) + "\n")
    return snap


def swap_tx(src: str, dst: str, amount: int, side: str = "BUY", slippage: str | None = None) -> dict:
    """Return 1inch unsigned tx. BUY = USDC→token. SELL = token→USDC."""
    load_env()
    if not has_key():
        return {"ok": False, "live": False, "note": "no ONEINCH_API_KEY"}
    wallet = env("ONCHAIN_ADDRESS", default=WALLET)
    if side == "SELL":
        src, dst = dst, src
    slip = str(slippage or os.environ.get("ONEINCH_SLIPPAGE", SLIPPAGE) or "1")
    url = qs(f"{BASE}/swap", {
        "src": src,
        "dst": dst,
        "amount": str(amount),
        "from": wallet.lower(),
        "origin": wallet.lower(),
        "slippage": slip,
        "disableEstimate": "false",
        "allowPartialFill": "false",
    })
    payload = http_json(url, headers=_headers())
    tx = payload.get("tx") if isinstance(payload, dict) else None
    if not isinstance(tx, dict):
        return {
            "ok": False,
            "live": False,
            "note": "1inch swap build failed",
            "error": str(payload.get("description") or payload.get("error") or payload)[:200],
        }
    return {
        "ok": True,
        "live": False,
        "dst_amount": payload.get("dstAmount"),
        "tx": tx,
        "note": "unsigned 1inch tx — pass --live to sign",
    }


def _rpc(method: str, params: list):
    req = urllib.request.Request(
        RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "money-team-1inch/1"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read())
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return payload["result"]


def broadcast(tx: dict) -> dict:
    """Sign + send. Requires ONCHAIN_PRIVATE_KEY and eth_account."""
    pk = env("ONCHAIN_PRIVATE_KEY", "POLYGON_PRIVATE_KEY")
    if not pk:
        return {"ok": False, "live": False, "note": "no ONCHAIN_PRIVATE_KEY"}
    try:
        from eth_account import Account  # type: ignore
    except ImportError:
        return {"ok": False, "live": False, "note": "pip install eth_account to --live onchain"}
    if pk.startswith("0x"):
        acct = Account.from_key(pk)
    else:
        acct = Account.from_key("0x" + pk)
    wallet = env("ONCHAIN_ADDRESS", default=WALLET)
    if acct.address.lower() != wallet.lower():
        return {"ok": False, "live": False, "note": "ONCHAIN_PRIVATE_KEY does not match desk wallet"}
    nonce = int(_rpc("eth_getTransactionCount", [acct.address, "pending"]), 16)
    gas_price = int(_rpc("eth_gasPrice", []), 16)
    value = int(str(tx.get("value") or "0"), 0)
    gas = int(str(tx.get("gas") or "0"), 0) or 400000
    signed = acct.sign_transaction({
        "to": tx["to"],
        "data": tx.get("data") or "0x",
        "value": value,
        "gas": gas,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": CHAIN,
    })
    raw = "0x" + signed.raw_transaction.hex() if hasattr(signed, "raw_transaction") else signed.rawTransaction.hex()
    if not raw.startswith("0x"):
        raw = "0x" + raw
    txh = _rpc("eth_sendRawTransaction", [raw])
    return {"ok": True, "live": True, "tx_hash": txh, "note": f"broadcast {txh}"}


def execute(ticket: dict, live: bool = False) -> dict:
    """Trader entry. ticket needs market_id like USDC-WETH, size_usd, side BUY|SELL."""
    load_env()
    market = str(ticket.get("market_id") or ticket.get("market") or "").upper()
    dst_name = None
    for name, meta in TOKENS.items():
        if name in market or meta["symbol"] in market:
            dst_name = name
            break
    if dst_name is None:
        return {"ok": False, "live": False, "venue": "onchain", "note": f"unknown 1inch market {market}"}
    meta = TOKENS[dst_name]
    try:
        size = float(ticket.get("size_usd") or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return {"ok": False, "live": False, "venue": "onchain", "note": "size_usd required"}
    amount = int(round(size * 1e6))
    side = str(ticket.get("side") or "BUY").upper()
    if side == "SELL":
        qty = ticket.get("qty_wei") or ticket.get("amount_wei")
        try:
            amount = int(str(qty)) if qty is not None else 0
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            return {"ok": False, "live": False, "venue": "onchain", "note": "SELL needs qty_wei from inventory"}
    built = swap_tx(USDC, meta["address"], amount, side=side, slippage=ticket.get("slippage"))
    built["venue"] = "onchain"
    built["market_id"] = ticket.get("market_id")
    if not built.get("ok") or not live:
        return built
    sent = broadcast(built["tx"])
    sent["venue"] = "onchain"
    sent["market_id"] = ticket.get("market_id")
    sent["dst_amount"] = built.get("dst_amount")
    return sent
