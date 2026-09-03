#!/usr/bin/env python3
"""Emit a 5-minute heartbeat for the two Bots (scorer + trader).

  python3 tools/heartbeat.py
  python3 tools/heartbeat.py --bot scorer
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from append_event import append, load_env  # noqa: E402

ROSTER = (
    ("scorer", "Scorer", "scoring"),
    ("trader", "Trader", "execution"),
)


def now_iso() -> str:
    try:
        return datetime.now(ZoneInfo("America/Denver")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    load_env(ROOT / ".env")
    only = None
    if "--bot" in sys.argv:
        only = sys.argv[sys.argv.index("--bot") + 1]
    ts = now_iso()
    cycle_id = "hb-" + ts.replace(":", "").replace("-", "")[:15]
    rows = ROSTER if not only else [r for r in ROSTER if r[0] == only]
    if not rows:
        raise SystemExit(f"unknown bot {only}")
    for bot, role, constraint in rows:
        append({
            "ts": ts,
            "cycle_id": cycle_id,
            "kind": "heartbeat",
            "bot": bot,
            "role": role,
            "constraint": constraint,
        })


if __name__ == "__main__":
    main()
