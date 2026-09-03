#!/usr/bin/env python3
"""Pull OSIRIS trade intel. No API key. Docs: https://osirisai.live/docs#quickstart

Every scan the Scorer runs this and puts the result on ingest.osiris.
Tickets are illegal if this feed is missing or stale.

  python3 tools/osiris.py
  python3 tools/osiris.py --json

Heavy GeoJSON (flights, CCTV, satellites, fires maps) is skipped on purpose.
Those do not price Kalshi / Polymarket US tickets. Trade routes:

  /api/stats /api/markets /api/crypto /api/news
  /api/country-risk /api/conflicts /api/gdelt
  /api/space-weather /api/cyber-threats /api/weather

Do not POST /api/github-webhook. That route only forwards signed GitHub
repo events (x-hub-signature-256). An empty JSON body is not a feed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ledger" / "osiris_snapshot.json"
BASE = os.environ.get("OSIRIS_URL", "https://osirisai.live").rstrip("/")
UA = "money-team-osiris/1"
DOCS = "https://osirisai.live/docs#quickstart"

# Trade-relevant GETs. Skip flights/cctv/sats/fires geometry (multi-MB, not a book).
# Skip POSTs: /api/github-webhook (GitHub HMAC forwarder), /api/sdk/ingest, /api/ai/*.
TRADE_ROUTES = (
    "health",
    "stats",
    "markets",
    "crypto",
    "news",
    "country-risk",
    "conflicts",
    "gdelt",
    "space-weather",
    "cyber-threats",
    "weather",
)


def now_iso() -> str:
    try:
        return datetime.now(ZoneInfo("America/Denver")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_json(path: str, timeout: int = 15) -> dict:
    url = f"{BASE}/api/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _failed(payload) -> bool:
    return isinstance(payload, dict) and bool(payload.get("error"))


def _as_rows(payload) -> list:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("crypto", "prices", "items", "news", "countries", "risks"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [row for row in inner if isinstance(row, dict)]
    return []


def _crypto_spots(payload) -> dict:
    spots = {}
    rows = _as_rows(payload)
    if rows:
        iterable = ((row.get("symbol") or row.get("name") or "", row) for row in rows)
    elif isinstance(payload, dict):
        blob = payload.get("crypto") or payload.get("prices") or payload
        if not isinstance(blob, dict):
            return spots
        iterable = blob.items()
    else:
        return spots
    for key, row in iterable:
        if not isinstance(row, dict):
            continue
        name = str(row.get("symbol") or row.get("name") or key).upper()
        price = row.get("price") or row.get("usd")
        if price is None:
            continue
        try:
            spots[name.replace("-USD", "")] = float(price)
        except (TypeError, ValueError):
            continue
    return spots


def _market_ticks(payload) -> dict:
    out = {}
    if not isinstance(payload, dict) or _failed(payload):
        return out
    for group, rows in payload.items():
        if not isinstance(rows, dict):
            continue
        if group in ("count", "timestamp", "scm_alerts"):
            continue
        for name, row in rows.items():
            if not isinstance(row, dict) or row.get("price") is None:
                continue
            try:
                out[name] = {
                    "price": float(row["price"]),
                    "chg": float(row.get("change_percent") or 0),
                    "open": bool(row.get("market_open")),
                }
            except (TypeError, ValueError):
                continue
    return out


def _news_head(payload) -> dict:
    if _failed(payload) or not isinstance(payload, dict):
        items = []
    else:
        items = payload.get("news") or payload.get("items") or []
        if not isinstance(items, list):
            items = []
    ranked = []
    for it in items[:40]:
        if not isinstance(it, dict):
            continue
        try:
            risk = int(it.get("risk_score") or 0)
        except (TypeError, ValueError):
            risk = 0
        ranked.append({
            "title": str(it.get("title") or "")[:160],
            "risk": risk,
            "source": it.get("source"),
            "published": it.get("published") or it.get("date"),
        })
    ranked.sort(key=lambda r: r["risk"], reverse=True)
    max_risk = ranked[0]["risk"] if ranked else 0
    return {
        "n": len(items),
        "max_risk": max_risk,
        "top": ranked[:8],
        "hot": [r for r in ranked if r["risk"] >= 5][:5],
    }


def _risk_head(payload) -> dict:
    if _failed(payload) or not isinstance(payload, dict):
        return {"top": [], "exchanges": None}
    countries = payload.get("countries") or payload.get("risks") or payload
    rows = []
    if isinstance(countries, dict):
        for name, row in countries.items():
            if name in ("timestamp", "exchanges", "count") or not isinstance(row, dict):
                continue
            score = row.get("score") or row.get("risk") or row.get("risk_score")
            try:
                rows.append({"name": name, "score": float(score), "tags": row.get("tags") or []})
            except (TypeError, ValueError):
                continue
    elif isinstance(countries, list):
        for row in countries:
            if not isinstance(row, dict):
                continue
            try:
                rows.append({
                    "name": row.get("country") or row.get("name") or row.get("code"),
                    "score": float(row.get("score") or row.get("risk") or row.get("risk_score") or 0),
                    "tags": row.get("tags") or [],
                    "level": row.get("risk_level"),
                })
            except (TypeError, ValueError):
                continue
    rows.sort(key=lambda r: r["score"], reverse=True)
    return {"top": rows[:8], "exchanges": payload.get("open_exchanges") or payload.get("exchanges")}


def summarize(raw: dict) -> dict:
    crypto = _crypto_spots(raw.get("crypto"))
    markets = _market_ticks(raw.get("markets") if isinstance(raw.get("markets"), dict) else {})
    news = _news_head(raw.get("news") if isinstance(raw.get("news"), dict) else {})
    risk = _risk_head(raw.get("country-risk") if isinstance(raw.get("country-risk"), dict) else {})
    stats_blob = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    stats = stats_blob.get("stats") if isinstance(stats_blob.get("stats"), dict) else stats_blob
    if not isinstance(stats, dict) or stats.get("error"):
        stats = {}
    conflicts = raw.get("conflicts") if isinstance(raw.get("conflicts"), dict) else {}
    n_conflict = 0
    if conflicts and not _failed(conflicts):
        n_conflict = int(conflicts.get("totalZones") or 0)
        if not n_conflict:
            n_conflict = len(conflicts.get("zones") or conflicts.get("conflicts") or conflicts.get("features") or [])
        if not n_conflict and "count" in conflicts:
            try:
                n_conflict = int(conflicts["count"])
            except (TypeError, ValueError):
                n_conflict = 0
    space = raw.get("space-weather") if isinstance(raw.get("space-weather"), dict) else {}
    cyber = raw.get("cyber-threats") if isinstance(raw.get("cyber-threats"), dict) else {}
    weather = raw.get("weather") if isinstance(raw.get("weather"), dict) else {}
    gdelt = raw.get("gdelt") if isinstance(raw.get("gdelt"), dict) else {}
    cyber_stats = cyber.get("stats") if isinstance(cyber.get("stats"), dict) else {}
    vix = (markets.get("VIX") or {}).get("price")
    btc = crypto.get("BTC") or crypto.get("BITCOIN")
    note_bits = []
    if btc:
        note_bits.append(f"BTC {btc:.0f}")
    if vix:
        note_bits.append(f"VIX {vix}")
    if news.get("max_risk"):
        note_bits.append(f"news risk {news['max_risk']}")
        if news.get("hot"):
            note_bits.append(news["hot"][0]["title"][:80])
    if n_conflict:
        note_bits.append(f"{n_conflict} conflict zones")
    if risk.get("top"):
        top_r = risk["top"][0]
        note_bits.append(f"risk {top_r.get('name')} {top_r.get('score')}")
    storm = space.get("storm_level") if not _failed(space) else None
    if storm and str(storm).lower() not in ("quiet", "none", ""):
        note_bits.append(f"space {storm} kp {space.get('kp_index')}")
    if cyber_stats.get("threat_level"):
        note_bits.append(f"cyber {cyber_stats.get('threat_level')}")
    pulled = [k for k, v in raw.items() if (isinstance(v, list) or (isinstance(v, dict) and not v.get("error")))]
    failed = [k for k, v in raw.items() if isinstance(v, dict) and v.get("error")]
    core_ok = all(k in pulled for k in ("stats", "markets", "crypto", "news"))
    keep_mkts = ("S&P 500", "Nasdaq 100", "VIX", "WTI Crude", "Gold", "Bitcoin", "Ethereum", "Solana", "XRP")
    return {
        "ok": core_ok,
        "docs": DOCS,
        "base": BASE,
        "pulled": pulled,
        "failed": failed,
        "stats": {k: stats.get(k) for k in ("flights", "sats", "weather", "incidents", "nuclear") if k in stats},
        "crypto": crypto,
        "markets": {k: markets[k] for k in markets if k in keep_mkts},
        "news": news,
        "country_risk": risk.get("top"),
        "conflicts": n_conflict,
        "space_weather": {
            "kp": space.get("kp_index"),
            "storm": space.get("storm_level"),
        } if space and not _failed(space) else None,
        "cyber": {
            "level": cyber_stats.get("threat_level"),
            "cves": cyber_stats.get("active_cves"),
        } if cyber_stats else None,
        "weather_n": weather.get("total") if weather and not _failed(weather) else None,
        "gdelt_n": gdelt.get("total") if gdelt and not _failed(gdelt) else None,
        "note": " · ".join(note_bits) or "osiris pulled",
    }


def ingest_row(summary: dict, lag_s: float) -> dict:
    note = summary.get("note") or "osiris pulled"
    if not summary.get("ok"):
        failed = ",".join(summary.get("failed") or []) or "core routes"
        note = f"osiris incomplete ({failed})"
    return {"ok": bool(summary.get("ok")), "lag_s": round(lag_s, 1), "note": note}


def pull() -> dict:
    raw = {}
    for route in TRADE_ROUTES:
        try:
            raw[route] = fetch_json(route)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as err:
            raw[route] = {"error": str(err)[:200]}
    summary = summarize(raw)
    summary["ts"] = now_iso()
    summary["ingest"] = ingest_row(summary, 0)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull OSIRIS trade intel")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = pull()
    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    if args.json:
        print(json.dumps(summary["ingest"]))
    else:
        flag = "OK" if summary["ok"] else "GAP"
        print(f"{flag} osiris  {summary['ingest']['note']}", file=sys.stderr)
        print(f"wrote {OUT}", file=sys.stderr)
        if not summary["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
