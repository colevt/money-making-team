"""Kalshi signed post. Read is public; live orders need KALSHI_API_KEY + RSA PEM."""
from __future__ import annotations

import base64
import time

from .common import env, has_env, http_json, load_env

DEFAULT_BASE = "https://api.elections.kalshi.com"


def _base() -> str:
    return env("KALSHI_API_BASE") or DEFAULT_BASE


def _sign(method: str, path: str) -> dict | None:
    pem = env("KALSHI_PRIVATE_KEY", "KALSHI_PRIVATE_KEY_PEM")
    key_id = env("KALSHI_API_KEY", "KALSHI_KEY_ID")
    if not pem or not key_id:
        return None
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        return None
    if "BEGIN" not in pem:
        pem_path = pem
        try:
            pem = open(pem_path).read()
        except OSError:
            return None
    ts = str(int(time.time() * 1000))
    msg = (ts + method.upper() + path).encode()
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    sig = key.sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
    }


def ready() -> bool:
    load_env()
    return has_env("KALSHI_API_KEY") and bool(env("KALSHI_PRIVATE_KEY", "KALSHI_PRIVATE_KEY_PEM"))


def execute(ticket: dict, live: bool = False) -> dict:
    load_env()
    ticker = str(ticket.get("market_id") or "")
    side = str(ticket.get("side") or "YES").upper()
    try:
        size = float(ticket.get("size_usd") or 0)
        entry = float(ticket.get("entry_cents") or 0)
    except (TypeError, ValueError):
        size, entry = 0.0, 0.0
    count = max(1, int(round(size / max(entry / 100.0, 0.01)))) if entry else 1
    body = {
        "ticker": ticker,
        "side": "yes" if side == "YES" else "no",
        "action": "buy",
        "count": count,
        "type": "limit",
        "yes_price": int(round(entry)) if side == "YES" else None,
        "no_price": int(round(entry)) if side == "NO" else None,
    }
    path = "/trade-api/v2/portfolio/orders"
    plan = {"ok": True, "live": False, "venue": "kalshi", "market_id": ticker, "body": body,
            "note": "unsigned Kalshi order — pass --live to sign"}
    if not live:
        return plan
    hdrs = _sign("POST", path)
    if not hdrs:
        return {"ok": False, "live": False, "venue": "kalshi", "note": "no KALSHI_API_KEY / KALSHI_PRIVATE_KEY"}
    payload = http_json(_base() + path, method="POST", headers=hdrs, body={k: v for k, v in body.items() if v is not None})
    if payload.get("ok") is False or payload.get("status", 200) >= 400:
        return {
            "ok": False,
            "live": False,
            "venue": "kalshi",
            "note": "Kalshi order rejected",
            "error": str(payload.get("error") or payload.get("message") or payload)[:200],
        }
    oid = (payload.get("order") or {}).get("order_id") or payload.get("order_id")
    return {"ok": True, "live": True, "venue": "kalshi", "market_id": ticker, "order_id": oid,
            "note": f"Kalshi live {oid or 'posted'}"}
