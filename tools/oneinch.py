#!/usr/bin/env python3
"""Quote Polygon 1inch books. Scorer runs this every scan onto ingest.onchain.

  python3 tools/oneinch.py
  python3 tools/oneinch.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from venues.oneinch import pull_quotes  # noqa: E402


def _kraken_fairs() -> dict:
    import urllib.request
    url = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD,ETHUSD,SOLUSD"
    req = urllib.request.Request(url, headers={"User-Agent": "money-team-1inch/1"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read())
    except Exception:
        return {}
    result = payload.get("result") or {}

    def last(*keys):
        for k in keys:
            row = result.get(k) or {}
            c = row.get("c") or []
            if c:
                try:
                    return float(c[0])
                except (TypeError, ValueError, IndexError):
                    continue
        return None

    out = {}
    btc = last("XXBTZUSD", "XBTUSD")
    eth = last("XETHZUSD", "ETHUSD")
    sol = last("SOLUSD")
    if btc:
        out["BTC"] = btc
    if eth:
        out["ETH"] = eth
    if sol:
        out["SOL"] = sol
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Quote 1inch Polygon books")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    snap = pull_quotes(_kraken_fairs())
    ingest = snap.get("ingest") or {}
    if args.json:
        print(json.dumps(ingest))
    else:
        flag = "OK" if ingest.get("ok") else "GAP"
        print(f"{flag} onchain  {ingest.get('note')}", file=sys.stderr)
        print(json.dumps(ingest))
    if not ingest.get("ok"):
        raise SystemExit(0 if "no ONEINCH_API_KEY" in str(ingest.get("note")) else 1)


if __name__ == "__main__":
    main()
