#!/usr/bin/env bash
# Run once on the Grok Bot computer (and after a flatten pull).
# No Lovable token. No Origin login. Ledger is local.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 tools/daily_update.py --force
python3 tools/test_ledger_contract.py
echo "connected: $(pwd)  (git $(git rev-parse --short HEAD))"
echo "rules pull once a day: python3 tools/daily_update.py"
echo "append with: python3 tools/append_event.py '{...}'"
echo "dashboard:   python3 tools/serve_desk.py"
echo "Lovable is display-only. Do not ask for ingest tokens."
