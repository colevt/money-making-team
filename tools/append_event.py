#!/usr/bin/env python3
"""Append one ledger event from a Grok bot. Same contract as tools/append-event.mjs.

The cycle stays in this repo: events land in ledger/events.jsonl. Do not POST
anywhere. Lovable is a public view of site/, not part of the agent loop.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from ledger_contract import ContractError, validate as contract_validate  # noqa: E402


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def ledger_path() -> Path:
    return Path(os.environ.get("LEDGER_PATH", ROOT / "ledger" / "events.jsonl"))


def append(event: dict) -> Path:
    path = ledger_path()
    contract_validate(event, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")
    print(f"appended {event['kind']} cycle={event['cycle_id']} → {path}", file=sys.stderr)
    return path


def read_payload(args: list[str]) -> dict:
    if args[:1] == ["--file"]:
        raw = Path(args[1]).read_text()
    elif args and args[0] != "-":
        raw = args[0]
    else:
        raw = sys.stdin.read()
    return json.loads(raw)


def main() -> None:
    load_env(ROOT / ".env")
    try:
        append(read_payload(sys.argv[1:]))
    except ContractError as err:
        raise SystemExit(str(err) or "invalid event") from err


if __name__ == "__main__":
    main()
