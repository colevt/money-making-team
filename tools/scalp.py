#!/usr/bin/env python3
"""Buy the local low, sell the local high. Small size, many round-trips.

Scorer runs this every scan after osiris.py + oneinch.py:

  python3 tools/scalp.py --cycle_id …
  python3 tools/scalp.py --cycle_id … --append

Trader still fills with execute.py --live --append. After settle, learn_from_settle.py
retunes crypto_scalp weights and the dip/take/stop it used.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from compose_score import compose  # noqa: E402
from crypto_tape import update as update_tape  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Tape + compose onchain buy-low/sell-high scores")
    parser.add_argument("--cycle_id", required=True)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--skip-fetch", action="store_true", help="reuse ledger/crypto_tape.json")
    parser.add_argument("--flow-file", default=None, help="UW/flow JSON {ETH:{side:buy},...}")
    args = parser.parse_args()
    if args.ledger:
        os.environ["LEDGER_PATH"] = args.ledger
    flow = None
    if args.flow_file:
        flow = json.loads(Path(args.flow_file).read_text())
    if not args.skip_fetch:
        tape = update_tape(flow=flow)
        print(f"tape  {tape.get('note')}", file=sys.stderr)
    out = compose(args.cycle_id)
    if args.append:
        from append_event import append  # noqa: E402
        for score in out["scores"]:
            append(score)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
