#!/usr/bin/env python3
"""Pull every OSIRIS GET feed the Scorer can use. Docs: https://osirisai.live/docs

  python3 tools/osiris.py
  python3 tools/osiris.py --json

All keyless map/intel/market GETs are pulled every scan. Heavy GeoJSON
(flights, satellites, CCTV, fires, frontlines, malware hosts) is compacted
to counts + heads so the snapshot stays small. The Scorer still uses the
numbers: military traffic, GPS jamming, fire count, quake mag, etc.

Not pulled (not feeds / not safe to poll every scan):

  POST /api/github-webhook  POST /api/sdk/ingest  POST /api/ai/*
  /api/scanner  /api/osint/sweep          # active scan
  /api/osint/* lookups                   # need a subject
  /api/cctv/proxy  /api/proxy-tiles      # stream/tile proxies
  /api/region-dossier  /api/sentinel     # need a map point
  /api/entity/expand  /api/malware/stream /api/sdk/stream
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ledger" / "osiris_snapshot.json"
BASE = os.environ.get("OSIRIS_URL", "https://osirisai.live").rstrip("/")
UA = "money-team-osiris/1"
DOCS = "https://osirisai.live/docs"

# Every keyless GET that is a live feed (not a lookup, proxy, or POST).
ALL_GETS = (
    "health",
    "stats",
    "flights",
    "satellites",
    "space-weather",
    "earthquakes",
    "fires",
    "weather",
    "air-quality",
    "radar",
    "conflicts",
    "frontlines",
    "gdelt",
    "country-risk",
    "news",
    "live-news",
    "markets",
    "crypto",
    "scm-suppliers",
    "cctv",
    "infrastructure",
    "maritime",
    "geo",
    "cyber-threats",
    "cyber-attacks",
    "malware",
    "sdk/ingest",
)
HEAVY = {"flights", "satellites", "cctv", "fires", "frontlines", "malware"}
CORE = ("stats", "markets", "crypto", "news")


def now_iso() -> str:
    try:
        return datetime.now(ZoneInfo("America/Denver")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _failed(payload) -> bool:
    return isinstance(payload, dict) and bool(payload.get("error"))


def fetch_json(path: str, timeout: int = 20):
    url = f"{BASE}/api/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _n_list(payload, *keys) -> int:
    if not isinstance(payload, dict):
        return 0
    for key in keys:
        val = payload.get(key)
        if isinstance(val, list):
            return len(val)
        if isinstance(val, dict) and key != "stats":
            return len(val)
        if isinstance(val, int) and key in ("total", "count"):
            return val
    for key in ("total", "count"):
        try:
            return int(payload.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return 0


def compact(route: str, payload):
    """Drop multi-MB geometry. Keep counts and a few heads the Scorer can read."""
    if _failed(payload):
        return payload
    if route == "flights" and isinstance(payload, dict):
        return {
            "total": payload.get("total"),
            "commercial": _n_list(payload, "commercial_flights"),
            "private": _n_list(payload, "private_flights"),
            "jets": _n_list(payload, "private_jets"),
            "military": _n_list(payload, "military_flights"),
            "gps_jamming": _n_list(payload, "gps_jamming"),
            "source": payload.get("source"),
        }
    if route == "satellites" and isinstance(payload, dict):
        return {
            "total": payload.get("total") or _n_list(payload, "satellites"),
            "category_counts": payload.get("category_counts"),
            "source": payload.get("source"),
        }
    if route == "cctv" and isinstance(payload, dict):
        regions = payload.get("regions") or []
        names = []
        if isinstance(regions, list):
            for row in regions[:12]:
                if isinstance(row, dict):
                    names.append(str(row.get("name") or row.get("region") or "")[:40])
                elif isinstance(row, str):
                    names.append(row[:40])
        return {
            "total": payload.get("total") or _n_list(payload, "cameras"),
            "n_regions": len(regions) if isinstance(regions, list) else 0,
            "n_sources": len(payload.get("sources") or {}),
            "regions": [n for n in names if n],
        }
    if route == "fires" and isinstance(payload, dict):
        fires = payload.get("fires") or []
        hot = 0
        if isinstance(fires, list):
            for row in fires:
                if not isinstance(row, dict):
                    continue
                try:
                    if float(row.get("frp") or 0) >= 20:
                        hot += 1
                except (TypeError, ValueError):
                    continue
        return {"total": payload.get("total") or _n_list(payload, "fires"), "hot_frp20": hot, "source": payload.get("source")}
    if route == "frontlines" and isinstance(payload, dict):
        blob = payload.get("frontlines") or payload
        if isinstance(blob, dict):
            theatres = [k for k in blob.keys() if k not in ("id", "map", "datetime", "timestamp", "type")]
            return {
                "n": len(theatres) or (1 if blob.get("id") or blob.get("map") else 0),
                "theatres": theatres[:8] or ([blob.get("id")] if blob.get("id") else []),
                "datetime": blob.get("datetime") or payload.get("timestamp"),
            }
        if isinstance(blob, list):
            return {"n": len(blob), "theatres": [str((r or {}).get("id") or (r or {}).get("name") or "")[:40] for r in blob[:8] if isinstance(r, dict)]}
        return {"n": 0}
    if route == "malware" and isinstance(payload, dict):
        threats = payload.get("threats") or []
        families = {}
        sample = []
        if isinstance(threats, list):
            for row in threats:
                if not isinstance(row, dict):
                    continue
                fam = str(row.get("malware") or "unknown")
                families[fam] = families.get(fam, 0) + 1
            top = sorted(families.items(), key=lambda kv: kv[1], reverse=True)[:6]
            sample = [{"malware": k, "n": v} for k, v in top]
        return {"total": payload.get("total") or _n_list(payload, "threats"), "families": sample, "source": payload.get("source")}
    if route == "earthquakes" and isinstance(payload, dict):
        rows = payload.get("earthquakes") or []
        ranked = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    mag = float(row.get("magnitude") or row.get("mag") or 0)
                except (TypeError, ValueError):
                    mag = 0
                ranked.append({"mag": mag, "place": str(row.get("place") or "")[:80], "tsunami": bool(row.get("tsunami"))})
            ranked.sort(key=lambda r: r["mag"], reverse=True)
        return {"n": payload.get("total") or len(ranked), "max_mag": ranked[0]["mag"] if ranked else 0, "top": ranked[:6]}
    if route == "radar" and isinstance(payload, dict):
        rows = payload.get("outages") or []
        ranked = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    score = float(row.get("score") or 0)
                except (TypeError, ValueError):
                    score = 0
                ranked.append({"country": row.get("country") or row.get("code"), "score": round(score, 1), "level": row.get("level")})
            ranked.sort(key=lambda r: r["score"], reverse=True)
        return {"n": payload.get("total") or len(ranked), "top": ranked[:8], "source": payload.get("source")}
    if route == "gdelt" and isinstance(payload, dict):
        rows = payload.get("events") or []
        names = []
        if isinstance(rows, list):
            for row in rows[:12]:
                if isinstance(row, dict) and row.get("name"):
                    names.append(str(row.get("name"))[:80])
        return {"n": payload.get("total") or _n_list(payload, "events"), "top": names, "source": payload.get("source")}
    if route == "weather" and isinstance(payload, dict):
        rows = payload.get("events") or []
        top = []
        if isinstance(rows, list):
            for row in rows[:8]:
                if isinstance(row, dict):
                    top.append({
                        "title": str(row.get("title") or "")[:100],
                        "type": row.get("type") or row.get("category"),
                        "severity": row.get("severity"),
                    })
        return {"n": payload.get("total") or len(rows) if isinstance(rows, list) else 0, "top": top}
    if route == "live-news" and isinstance(payload, dict):
        return {
            "n": payload.get("total") or _n_list(payload, "feeds"),
            "categories": payload.get("categories") or [],
            "feeds": [
                str(r.get("name") or "")[:40]
                for r in (payload.get("feeds") or [])[:12]
                if isinstance(r, dict)
            ],
        }
    if route == "scm-suppliers" and isinstance(payload, dict):
        rows = payload.get("suppliers") or []
        flagged = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                level = str(row.get("risk_level") or "").upper()
                if level and level not in ("NORMAL", "OK", "LOW", ""):
                    flagged.append({"name": row.get("name"), "country": row.get("country"), "level": level, "category": row.get("category")})
        return {
            "n": payload.get("total") or _n_list(payload, "suppliers"),
            "critical_count": payload.get("critical_count"),
            "flagged": flagged[:8],
        }
    if route == "infrastructure" and isinstance(payload, dict):
        rows = payload.get("infrastructure") or []
        hot = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                status = str(row.get("status") or "")
                if status and status.lower() not in ("operational", "active", "normal", ""):
                    hot.append({"name": row.get("name"), "country": row.get("country"), "status": status[:80]})
        return {"n": payload.get("total") or _n_list(payload, "infrastructure"), "hot": hot[:8]}
    if route == "maritime" and isinstance(payload, dict):
        return {
            "ports": payload.get("total_ports") or _n_list(payload, "ports"),
            "chokepoints": payload.get("total_chokepoints") or _n_list(payload, "chokepoints"),
            "ships": payload.get("total_ships") or _n_list(payload, "ships"),
            "chokepoint_names": [
                str(r.get("name") or r.get("id") or "")[:40]
                for r in (payload.get("chokepoints") or [])[:10]
                if isinstance(r, dict)
            ],
        }
    if route == "cyber-attacks" and isinstance(payload, dict):
        rows = payload.get("attacks") or []
        ranked = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    sev = int(row.get("severity") or 0)
                except (TypeError, ValueError):
                    sev = 0
                ranked.append({
                    "malware": row.get("malware"),
                    "country": row.get("target_country"),
                    "severity": sev,
                    "port": row.get("port"),
                })
            ranked.sort(key=lambda r: r["severity"], reverse=True)
        return {"n": payload.get("total") or len(ranked), "top": ranked[:8], "source": payload.get("source")}
    if route == "conflicts" and isinstance(payload, dict):
        events = payload.get("liveEvents") or []
        heads = []
        if isinstance(events, list):
            for row in events[:8]:
                if isinstance(row, dict):
                    heads.append(str(row.get("title") or row.get("name") or row.get("summary") or "")[:100])
        return {
            "zones": payload.get("totalZones") or _n_list(payload, "zones"),
            "live": payload.get("totalLiveEvents") or _n_list(payload, "liveEvents"),
            "warzones": payload.get("activeWarzones"),
            "heads": [h for h in heads if h],
        }
    if route == "air-quality" and isinstance(payload, dict):
        return {"n": payload.get("total") or _n_list(payload, "stations")}
    if route == "sdk/ingest" and isinstance(payload, dict):
        return {"entityCount": payload.get("entityCount"), "recent": payload.get("recentIngestions") or []}
    if route == "geo" and isinstance(payload, dict):
        return {k: payload.get(k) for k in ("city", "regionName", "country", "lat", "lon", "org")}
    return payload


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
        if not isinstance(rows, dict) or group in ("count", "timestamp", "scm_alerts"):
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
    return {"n": len(items), "max_risk": max_risk, "top": ranked[:8], "hot": [r for r in ranked if r["risk"] >= 5][:5]}


def _risk_head(payload) -> dict:
    if _failed(payload) or not isinstance(payload, dict):
        return {"top": []}
    countries = payload.get("countries") or payload.get("risks") or payload
    rows = []
    if isinstance(countries, list):
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
    return {"top": rows[:8], "open_exchanges": payload.get("open_exchanges")}


def summarize(raw: dict) -> dict:
    crypto = _crypto_spots(raw.get("crypto"))
    markets = _market_ticks(raw.get("markets") if isinstance(raw.get("markets"), dict) else {})
    news = _news_head(raw.get("news") if isinstance(raw.get("news"), dict) else {})
    risk = _risk_head(raw.get("country-risk") if isinstance(raw.get("country-risk"), dict) else {})
    stats_blob = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    stats = stats_blob.get("stats") if isinstance(stats_blob.get("stats"), dict) else stats_blob
    if not isinstance(stats, dict) or stats.get("error"):
        stats = {}
    flights = raw.get("flights") if isinstance(raw.get("flights"), dict) else {}
    sats = raw.get("satellites") if isinstance(raw.get("satellites"), dict) else {}
    eq = raw.get("earthquakes") if isinstance(raw.get("earthquakes"), dict) else {}
    fires = raw.get("fires") if isinstance(raw.get("fires"), dict) else {}
    radar = raw.get("radar") if isinstance(raw.get("radar"), dict) else {}
    space = raw.get("space-weather") if isinstance(raw.get("space-weather"), dict) else {}
    cyber = raw.get("cyber-threats") if isinstance(raw.get("cyber-threats"), dict) else {}
    attacks = raw.get("cyber-attacks") if isinstance(raw.get("cyber-attacks"), dict) else {}
    malware = raw.get("malware") if isinstance(raw.get("malware"), dict) else {}
    weather = raw.get("weather") if isinstance(raw.get("weather"), dict) else {}
    gdelt = raw.get("gdelt") if isinstance(raw.get("gdelt"), dict) else {}
    conflicts = raw.get("conflicts") if isinstance(raw.get("conflicts"), dict) else {}
    front = raw.get("frontlines") if isinstance(raw.get("frontlines"), dict) else {}
    scm = raw.get("scm-suppliers") if isinstance(raw.get("scm-suppliers"), dict) else {}
    infra = raw.get("infrastructure") if isinstance(raw.get("infrastructure"), dict) else {}
    maritime = raw.get("maritime") if isinstance(raw.get("maritime"), dict) else {}
    live_news = raw.get("live-news") if isinstance(raw.get("live-news"), dict) else {}
    cctv = raw.get("cctv") if isinstance(raw.get("cctv"), dict) else {}
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
            note_bits.append(str(news["hot"][0].get("title") or "")[:80])
    n_conflict = int(conflicts.get("zones") or 0) if conflicts and not _failed(conflicts) else 0
    if n_conflict:
        note_bits.append(f"{n_conflict} conflict zones")
    if risk.get("top"):
        top_r = risk["top"][0]
        note_bits.append(f"risk {top_r.get('name')} {top_r.get('score')}")
    if eq.get("max_mag"):
        note_bits.append(f"quake {eq['max_mag']}")
        if eq.get("top"):
            note_bits.append(str(eq["top"][0].get("place") or "")[:50])
    mil = flights.get("military") if flights and not _failed(flights) else None
    jam = flights.get("gps_jamming") if flights and not _failed(flights) else None
    if mil:
        note_bits.append(f"{mil} military flights")
    if jam:
        note_bits.append(f"{jam} GPS jamming")
    if fires.get("total"):
        note_bits.append(f"{fires.get('total')} fires")
    storm = space.get("storm_level") if space and not _failed(space) else None
    if storm and str(storm).lower() not in ("quiet", "none", ""):
        note_bits.append(f"space {storm} kp {space.get('kp_index')}")
    if cyber_stats.get("threat_level"):
        note_bits.append(f"cyber {cyber_stats.get('threat_level')}")
    if attacks.get("n"):
        note_bits.append(f"{attacks['n']} cyber attacks")
    if malware.get("total"):
        note_bits.append(f"{malware['total']} malware hosts")
    if scm.get("flagged"):
        note_bits.append(f"scm {scm['flagged'][0].get('name')}")
    if infra.get("hot"):
        note_bits.append(str(infra["hot"][0].get("name") or "infra")[:40])
    pulled = [k for k, v in raw.items() if (isinstance(v, list) or (isinstance(v, dict) and not v.get("error")))]
    failed = [k for k, v in raw.items() if isinstance(v, dict) and v.get("error")]
    core_ok = all(k in pulled for k in CORE)
    keep_mkts = ("S&P 500", "Nasdaq 100", "VIX", "WTI Crude", "Gold", "Bitcoin", "Ethereum", "Solana", "XRP")
    return {
        "ok": core_ok,
        "docs": DOCS,
        "base": BASE,
        "pulled": pulled,
        "failed": failed,
        "n_feeds": len(pulled),
        "stats": {k: stats.get(k) for k in ("flights", "sats", "weather", "incidents", "nuclear") if k in stats},
        "crypto": crypto,
        "markets": {k: markets[k] for k in markets if k in keep_mkts},
        "news": news,
        "live_news": live_news if live_news and not _failed(live_news) else None,
        "country_risk": risk.get("top"),
        "conflicts": conflicts if conflicts and not _failed(conflicts) else {"zones": n_conflict},
        "frontlines": front if front and not _failed(front) else None,
        "gdelt": gdelt if gdelt and not _failed(gdelt) else None,
        "space_weather": {
            "kp": space.get("kp_index"),
            "storm": space.get("storm_level"),
            "flares": space.get("solar_flares"),
        } if space and not _failed(space) else None,
        "earthquakes": eq if eq and not _failed(eq) else None,
        "fires": fires if fires and not _failed(fires) else None,
        "weather": weather if weather and not _failed(weather) else None,
        "radar": radar if radar and not _failed(radar) else None,
        "air_quality_n": (raw.get("air-quality") or {}).get("n") if isinstance(raw.get("air-quality"), dict) else None,
        "flights": flights if flights and not _failed(flights) else None,
        "satellites": sats if sats and not _failed(sats) else None,
        "cctv": cctv if cctv and not _failed(cctv) else None,
        "maritime": maritime if maritime and not _failed(maritime) else None,
        "infrastructure": infra if infra and not _failed(infra) else None,
        "scm": scm if scm and not _failed(scm) else None,
        "cyber": {
            "level": cyber_stats.get("threat_level"),
            "cves": cyber_stats.get("active_cves"),
            "attacks": attacks,
            "malware": malware,
        },
        "sdk": raw.get("sdk/ingest") if isinstance(raw.get("sdk/ingest"), dict) and not _failed(raw.get("sdk/ingest")) else None,
        "geo": raw.get("geo") if isinstance(raw.get("geo"), dict) and not _failed(raw.get("geo")) else None,
        "note": " · ".join(str(b) for b in note_bits if b) or "osiris pulled",
    }


def ingest_row(summary: dict, lag_s: float) -> dict:
    note = summary.get("note") or "osiris pulled"
    if not summary.get("ok"):
        failed = ",".join(summary.get("failed") or []) or "core routes"
        note = f"osiris incomplete ({failed})"
    n = summary.get("n_feeds")
    if n and summary.get("ok"):
        note = f"{n} feeds · {note}"
    return {"ok": bool(summary.get("ok")), "lag_s": round(lag_s, 1), "note": note}


def pull() -> dict:
    raw = {}

    def one(route: str):
        timeout = 25 if route in HEAVY else 15
        try:
            payload = fetch_json(route, timeout=timeout)
            return route, compact(route, payload)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as err:
            return route, {"error": str(err)[:200]}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(one, route) for route in ALL_GETS]
        for fut in as_completed(futs):
            route, payload = fut.result()
            raw[route] = payload
    summary = summarize(raw)
    summary["ts"] = now_iso()
    summary["ingest"] = ingest_row(summary, 0)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull every OSIRIS GET feed")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = pull()
    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    if args.json:
        print(json.dumps(summary["ingest"]))
    else:
        flag = "OK" if summary["ok"] else "GAP"
        print(f"{flag} osiris  {summary['ingest']['note']}", file=sys.stderr)
        print(f"wrote {OUT}  pulled={len(summary.get('pulled') or [])} failed={summary.get('failed')}", file=sys.stderr)
        if not summary["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
