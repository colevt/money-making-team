"""Polymarket US CLOB. Live post needs L2 API creds in .env. Never print them."""
from __future__ import annotations

import hmac
import hashlib
import base64
import time

from .common import env, http_json, load_env

DEFAULT_BASE = "https://clob.polymarket.com"


def _base() -> str:
    return env("POLYMARKET_CLOB_URL") or DEFAULT_BASE


def ready() -> bool:
    load_env()
    return bool(env("POLYMARKET_API_KEY") and env("POLYMARKET_API_SECRET") and env("POLYMARKET_PASSPHRASE"))


def _l2_headers(method: str, path: str, body: str = "") -> dict | None:
    key = env("POLYMARKET_API_KEY")
    secret = env("POLYMARKET_API_SECRET")
    phrase = env("POLYMARKET_PASSPHRASE")
    if not (key and secret and phrase):
        return None
    ts = str(int(time.time()))
    msg = ts + method.upper() + path + (body or "")
    try:
        raw_secret = base64.b64decode(secret)
    except Exception:
        raw_secret = secret.encode()
    sig = base64.b64encode(hmac.new(raw_secret, msg.encode(), hashlib.sha256).digest()).decode()
    return {
        "POLY_ADDRESS": env("POLYMARKET_ADDRESS", default=""),
        "POLY_SIGNATURE": sig,
        "POLY_TIMESTAMP": ts,
        "POLY_API_KEY": key,
        "POLY_PASSPHRASE": phrase,
    }


def execute(ticket: dict, live: bool = False) -> dict:
    load_env()
    token_id = str(ticket.get("market_id") or "")
    side = str(ticket.get("side") or "YES").upper()
    try:
        size = float(ticket.get("size_usd") or 0)
        entry = float(ticket.get("entry_cents") or 0)
    except (TypeError, ValueError):
        size, entry = 0.0, 0.0
    price = max(0.01, min(0.99, entry / 100.0 if entry else 0.5))
    shares = round(size / price, 2) if price else size
    body = {
        "tokenID": token_id,
        "price": price,
        "size": shares,
        "side": "BUY",
        "outcome": "YES" if side == "YES" else "NO",
    }
    plan = {"ok": True, "live": False, "venue": "polymarket_us", "market_id": token_id, "body": body,
            "note": "unsigned Polymarket order — pass --live to sign"}
    if not live:
        return plan
    path = "/order"
    import json
    raw = json.dumps(body, separators=(",", ":"))
    hdrs = _l2_headers("POST", path, raw)
    if not hdrs:
        return {"ok": False, "live": False, "venue": "polymarket_us",
                "note": "no POLYMARKET_API_KEY / SECRET / PASSPHRASE"}
    payload = http_json(_base() + path, method="POST", headers=hdrs, body=body)
    if payload.get("ok") is False or payload.get("status", 200) >= 400:
        return {
            "ok": False,
            "live": False,
            "venue": "polymarket_us",
            "note": "Polymarket order rejected",
            "error": str(payload.get("error") or payload.get("message") or payload)[:200],
        }
    oid = payload.get("orderID") or payload.get("order_id") or (payload.get("order") or {}).get("id")
    return {"ok": True, "live": True, "venue": "polymarket_us", "market_id": token_id, "order_id": oid,
            "note": f"Polymarket live {oid or 'posted'}"}
