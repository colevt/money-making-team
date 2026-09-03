#!/usr/bin/env python3
"""Pull public + desk sources into ledger/sources_snapshot.json.

This is market data, not the daily git update. Run on a scan or before
editing bots in Cursor so the snapshot is current.

  python3 tools/pull_sources.py

Unusual Whales, X, Kalshi, and Polymarket US still require Scorer plugins /
signed books. This script pulls everything that is public or already on the
live desk so Cursor is not working off a stale blotter.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ledger" / "sources_snapshot.json"
LIVE_DESK = os.environ.get(
    "LIVE_DESK_URL",
    "https://merger-sole-additional-checked.trycloudflare.com/api/desk",
)
POLYGON_RPC = os.environ.get("POLYGON_RPC", "https://polygon-bor.publicnode.com")
ONCHAIN_ADDR = "0xcE01ddD2141e4efDB929265A538981043b7449BF"
USDC_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
UA = "money-team-sources/1"

KRAKEN_PAIRS = "XBTUSD,ETHUSD,SOLUSD,XRPUSD"
ESPN_BOARDS = (
    ("mlb", "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"),
    ("nfl", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"),
    ("nba", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"),
)

REQUIRED = (
    "unusual_whales",
    "x_news",
    "espn",
    "crypto",
    "kalshi",
    "polymarket_us",
    "live_desk",
    "onchain",
)


def now_iso() -> str:
    try:
        return datetime.now(ZoneInfo("America/Denver")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_json(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def fail_row(err: Exception) -> dict:
    return {"ok": False, "error": str(err)[:240]}


def pull_espn() -> dict:
    games = []
    errors = []
    for sport, url in ESPN_BOARDS:
        try:
            payload = fetch_json(url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as err:
            errors.append(f"{sport}: {err}")
            continue
        for ev in payload.get("events") or []:
            comp = (ev.get("competitions") or [{}])[0]
            status = ((comp.get("status") or {}).get("type") or {})
            teams = []
            for c in comp.get("competitors") or []:
                team = c.get("team") or {}
                teams.append({
                    "abbr": team.get("abbreviation"),
                    "score": c.get("score"),
                    "home": c.get("homeAway") == "home",
                })
            games.append({
                "sport": sport,
                "name": ev.get("name") or ev.get("shortName"),
                "state": status.get("description") or status.get("name"),
                "completed": bool(status.get("completed")),
                "started": bool(status.get("state") == "in" or (status.get("description") or "").lower() == "in progress"),
                "detail": status.get("detail"),
                "teams": teams,
            })
    live = [g for g in games if g.get("started") and not g.get("completed")]
    return {
        "ok": not errors or bool(games),
        "live": len(live),
        "games": games[:40],
        "errors": errors,
        "note": f"{len(live)} live / {len(games)} listed",
    }


def kraken_last(result: dict, *keys: str) -> float | None:
    for key in keys:
        row = result.get(key)
        if row and row.get("c"):
            try:
                return float(row["c"][0])
            except (TypeError, ValueError, IndexError):
                return None
    return None


def pull_kraken() -> dict:
    url = f"https://api.kraken.com/0/public/Ticker?pair={KRAKEN_PAIRS}"
    payload = fetch_json(url)
    if payload.get("error"):
        raise RuntimeError(",".join(payload["error"]))
    result = payload.get("result") or {}
    spots = {
        "BTC": kraken_last(result, "XXBTZUSD", "XBTUSD"),
        "ETH": kraken_last(result, "XETHZUSD", "ETHUSD"),
        "SOL": kraken_last(result, "SOLUSD"),
        "XRP": kraken_last(result, "XXRPZUSD", "XRPUSD"),
    }
    missing = [k for k, v in spots.items() if v is None]
    return {
        "ok": not missing,
        "spots": spots,
        "note": "Kraken public ticker " + " ".join(f"{k} {v}" for k, v in spots.items() if v is not None),
        "missing": missing,
    }


def pull_desk() -> dict:
    url = LIVE_DESK
    if not url.endswith("/api/desk"):
        url = url.rstrip("/") + "/api/desk"
    payload = fetch_json(url)
    brain = payload.get("brain") or {}
    sources = brain.get("sources") or []
    intake = payload.get("intake") or {}
    cash = payload.get("cash") or []
    return {
        "ok": True,
        "clock": payload.get("clock"),
        "feeds": payload.get("feeds") or [],
        "brain_sources": sources,
        "intake": {
            k: (v.get("line") if isinstance(v, dict) else v)
            for k, v in intake.items()
            if k in ("whales", "news", "espn", "crypto", "books", "why")
        },
        "cash": [
            {"venue": c.get("venue"), "spendable": c.get("spendable"), "inPlay": c.get("inPlay")}
            for c in cash
        ],
        "open": payload.get("open"),
        "blotter_n": len(payload.get("blotter") or []),
        "x_note": (intake.get("news") or {}).get("line") if isinstance(intake.get("news"), dict) else None,
    }


def pull_onchain() -> dict:
    def rpc(method: str, params: list) -> str:
        req = urllib.request.Request(
            POLYGON_RPC,
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": UA},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
        if payload.get("error"):
            raise RuntimeError(payload["error"])
        return payload["result"]

    pol = int(rpc("eth_getBalance", [ONCHAIN_ADDR, "latest"]), 16) / 1e18
    data = "0x70a08231" + ONCHAIN_ADDR[2:].lower().rjust(64, "0")
    usdc = int(rpc("eth_call", [{"to": USDC_NATIVE, "data": data}, "latest"]), 16) / 1e6
    return {
        "ok": True,
        "usdc": round(usdc, 4),
        "pol": round(pol, 4),
        "address": ONCHAIN_ADDR,
        "note": "native USDC cash; POL is gas",
    }


def checklist(snap: dict) -> list[dict]:
    desk = snap.get("live_desk") or {}
    x_note = str(desk.get("x_note") or "").lower()
    rows = [
        {"key": "unusual_whales", "pulled_here": False, "need": "Scorer plugin 4021654", "desk": _desk_line(desk, "Unusual Whales", "whales")},
        {"key": "x_news", "pulled_here": False, "need": "Scorer plugin 4022021 — must actually pull", "desk": desk.get("x_note"), "illegal_if": "no pull yet" in x_note},
        {"key": "espn", "pulled_here": bool((snap.get("espn") or {}).get("ok")), "need": "public ESPN", "desk": _desk_line(desk, "Score feed", "espn")},
        {"key": "crypto", "pulled_here": bool((snap.get("crypto") or {}).get("ok")), "need": "Kraken public + UW spots", "desk": _desk_line(desk, "Crypto", "crypto")},
        {"key": "kalshi", "pulled_here": False, "need": "live Kalshi book (Scorer read / Trader sign)", "desk": _desk_line(desk, "Kalshi", None)},
        {"key": "polymarket_us", "pulled_here": False, "need": "live Polymarket US book", "desk": _desk_line(desk, "Polymarket", None)},
        {"key": "live_desk", "pulled_here": bool(desk.get("ok")), "need": "GET /api/desk"},
        {"key": "onchain", "pulled_here": bool((snap.get("onchain") or {}).get("ok")), "need": "Polygon USDC"},
    ]
    return rows


def _desk_line(desk: dict, feed_name: str, intake_key: str | None) -> str | None:
    for f in desk.get("feeds") or []:
        if feed_name.lower() in str(f.get("name") or "").lower():
            return f"{f.get('state')} · {f.get('detail')}"
    if intake_key:
        return (desk.get("intake") or {}).get(intake_key)
    return None


def main() -> None:
    snap: dict = {"ts": now_iso(), "required": list(REQUIRED)}
    try:
        snap["espn"] = pull_espn()
    except Exception as err:
        snap["espn"] = fail_row(err)
    try:
        snap["crypto"] = pull_kraken()
    except Exception as err:
        snap["crypto"] = fail_row(err)
    try:
        snap["live_desk"] = pull_desk()
    except Exception as err:
        snap["live_desk"] = fail_row(err)
    try:
        snap["onchain"] = pull_onchain()
    except Exception as err:
        snap["onchain"] = fail_row(err)
    snap["checklist"] = checklist(snap)
    OUT.write_text(json.dumps(snap, indent=2) + "\n")
    print(f"wrote {OUT}", file=sys.stderr)
    for row in snap["checklist"]:
        flag = "OK" if row.get("pulled_here") else "NEED"
        if row.get("illegal_if"):
            flag = "GAP"
        extra = row.get("desk") or row.get("need")
        print(f"{flag:4} {row['key']:16} {extra}")
    x = next((r for r in snap["checklist"] if r["key"] == "x_news"), None)
    if x and x.get("illegal_if"):
        print("X is still 'no pull yet' on the live desk. Scorer must search_news this cycle.", file=sys.stderr)


if __name__ == "__main__":
    main()
