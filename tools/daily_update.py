#!/usr/bin/env python3
"""Pull this repo at most once per America/Denver day.

Safe to call from a cycle: if today's pull already landed, this returns in
milliseconds. Do not `git pull` on every scan — that is what slowed the desk.

  python3 tools/daily_update.py
  python3 tools/daily_update.py --force
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
STAMP = ROOT / "ledger" / ".last-rules-pull"
TZ = ZoneInfo("America/Denver")


def today(now: datetime | None = None) -> str:
    stamp = now or datetime.now(TZ)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc).astimezone(TZ)
    else:
        stamp = stamp.astimezone(TZ)
    return stamp.date().isoformat()


def already_pulled(stamp_path: Path, day: str) -> bool:
    if not stamp_path.exists():
        return False
    first = stamp_path.read_text().strip().split()
    return bool(first) and first[0] == day


def write_stamp(stamp_path: Path, day: str, sha: str) -> None:
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(f"{day} {sha}\n")


def git_pull(root: Path) -> str:
    subprocess.run(
        ["git", "-C", str(root), "pull", "--ff-only"],
        check=True,
    )
    sha = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
        text=True,
    ).strip()
    return sha


def run(root: Path, stamp_path: Path, force: bool = False) -> str:
    day = today()
    if not force and already_pulled(stamp_path, day):
        print(f"daily update skip (already pulled {day})", file=sys.stderr)
        return "skip"
    sha = git_pull(root)
    write_stamp(stamp_path, day, sha)
    print(f"daily update {day} {sha}", file=sys.stderr)
    return sha


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull control-plane rules once a day")
    parser.add_argument("--force", action="store_true", help="pull even if already done today")
    args = parser.parse_args()
    try:
        run(ROOT, STAMP, force=args.force)
    except subprocess.CalledProcessError as err:
        raise SystemExit(f"git pull failed: {err}") from err


if __name__ == "__main__":
    main()
