#!/usr/bin/env python3
"""Optional publisher for a public view. Scorer and Trader do not run this.

The agent loop writes ledger/events.jsonl in this repo. Lovable only hosts a
copy of site/ later. If PUBLISH_URL is unset, this script exits 0 and does nothing.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def post(url: str, token: str, event: dict) -> None:
    req = urllib.request.Request(
        url,
        data=json.dumps(event).encode(),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as res:
        res.read()


def flush(ledger: Path, offset_path: Path, url: str, token: str) -> None:
    if not ledger.exists():
        return
    lines = ledger.read_text().splitlines()
    offset = int(offset_path.read_text()) if offset_path.exists() else 0
    for i in range(offset, len(lines)):
        line = lines[i].strip()
        if not line:
            offset = i + 1
            offset_path.write_text(str(offset))
            continue
        event = json.loads(line)
        try:
            post(url, token, event)
        except urllib.error.HTTPError as err:
            raise SystemExit(f"ingest {err.code} at line {i}: {err.read().decode()}") from err
        offset = i + 1
        offset_path.write_text(str(offset))
        print(f"sent {event.get('kind')} {event.get('cycle_id')}", file=__import__("sys").stderr)


def main() -> None:
    load_env(ROOT / ".env")
    url = os.environ.get("PUBLISH_URL", "")
    token = os.environ.get("PUBLISH_TOKEN", "")
    if not url or not token or token.startswith("replace-"):
        print("no publish URL set — agents use the local ledger, nothing to do", file=__import__("sys").stderr)
        return
    ledger = Path(os.environ.get("LEDGER_PATH", ROOT / "ledger" / "events.jsonl"))
    offset_path = ROOT / "ledger" / ".ingest-offset"
    print(f"watching {ledger} → {url}", file=__import__("sys").stderr)
    last_mtime = 0.0
    while True:
        mtime = ledger.stat().st_mtime if ledger.exists() else 0.0
        if mtime != last_mtime:
            last_mtime = mtime
            flush(ledger, offset_path, url, token)
        time.sleep(0.8)


if __name__ == "__main__":
    main()
