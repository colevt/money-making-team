#!/usr/bin/env python3
"""Serve the local Money Team desk and proxy live /api/desk.

  python3 tools/serve_desk.py
  open http://127.0.0.1:8765
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
FALLBACK = ROOT / "ledger" / "live_desk.json"
DEFAULT_LIVE = "https://merger-sole-additional-checked.trycloudflare.com/api/desk"
ONCHAIN_ADDR = "0xcE01ddD2141e4efDB929265A538981043b7449BF"
USDC_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
POLYGON_RPC = os.environ.get("POLYGON_RPC", "https://polygon-bor.publicnode.com")
PORT = int(os.environ.get("DESK_PORT", "8765"))


def load_env() -> None:
    env = ROOT / ".env"
    if not env.is_file():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def live_url() -> str:
    url = os.environ.get("LIVE_DESK_URL", DEFAULT_LIVE).strip()
    if url.endswith("/api/desk"):
        return url
    return url.rstrip("/") + "/api/desk"


def fetch_live() -> bytes:
    req = urllib.request.Request(
        live_url(),
        headers={"User-Agent": "money-team-desk/1", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        body = resp.read()
    json.loads(body)
    return body


def rpc(method: str, params: list) -> str:
    req = urllib.request.Request(
        POLYGON_RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "money-team-desk/1"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read())
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return payload["result"]


def verify_onchain(address: str) -> dict | None:
    try:
        pol = int(rpc("eth_getBalance", [address, "latest"]), 16) / 1e18
        data = "0x70a08231" + address[2:].lower().rjust(64, "0")
        usdc = int(rpc("eth_call", [{"to": USDC_NATIVE, "data": data}, "latest"]), 16) / 1e6
        return {"usdc": round(usdc, 4), "pol": round(pol, 4), "rpc": POLYGON_RPC}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, RuntimeError, ValueError):
        return None


def is_onchain(row: dict) -> bool:
    if row.get("id") == "onchain":
        return True
    return "onchain" in str(row.get("venue") or "").lower().replace("-", "")


def enrich(payload: dict) -> dict:
    cash = list(payload.get("cash") or [])
    onchain = next((c for c in cash if is_onchain(c)), None)
    addr = (onchain or {}).get("address") or ONCHAIN_ADDR
    verified = verify_onchain(addr)
    if verified:
        if onchain is None:
            onchain = {
                "id": "onchain",
                "venue": "Onchain",
                "inPlay": 0,
                "note": "Polygon DEX · native USDC · POL is gas",
                "address": addr,
                "token": USDC_NATIVE,
                "network": "polygon",
                "cash_source": "native USDC",
            }
            cash.append(onchain)
        onchain["spendable"] = verified["usdc"]
        onchain["pol"] = verified["pol"]
        onchain["pol_note"] = "gas, not cash"
        onchain["verified"] = True
        onchain["verify_source"] = "polygon rpc"
        onchain["address"] = addr
    names = {(c.get("venue") or "").lower() for c in cash}
    if not any("polymarket" in n for n in names):
        cash.insert(0, {"venue": "Polymarket US", "spendable": 0, "inPlay": 0, "missing": True})
    if not any("kalshi" in n for n in names):
        cash.insert(1 if any("polymarket" in n for n in names) else 0, {"venue": "Kalshi", "spendable": 0, "inPlay": 0, "missing": True})
    payload["cash"] = cash
    payload["accounts"] = [
        {"venue": c.get("venue"), "spendable": c.get("spendable"), "inPlay": c.get("inPlay"), "id": c.get("id"), "verified": c.get("verified", False)}
        for c in cash
    ]
    return payload


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] in ("/api/desk", "/api/desk/"):
            self._desk()
            return
        super().do_GET()

    def _desk(self) -> None:
        src = "live"
        try:
            raw = fetch_live()
            payload = json.loads(raw)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            payload = json.loads(FALLBACK.read_text())
            src = "fallback"
        try:
            payload = enrich(payload)
        except Exception as exc:
            payload.setdefault("feedNote", "")
            payload["feedNote"] = (payload.get("feedNote") or "") + f" Account verify skipped: {exc}"
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Desk-Source", src)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    load_env()
    SITE.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Desk  http://127.0.0.1:{PORT}")
    print(f"Learn http://127.0.0.1:{PORT}/#learn")
    print(f"API   {live_url()}")
    print("Onchain USDC is verified on Polygon. Kalshi/Poly balances come from the live desk keys.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
