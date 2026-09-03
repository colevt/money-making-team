#!/usr/bin/env python3
"""Contract tests for Grok ledger events. Run: python3 tools/test_ledger_contract.py"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from ledger_contract import ContractError, apply_learn, validate  # noqa: E402

TS = "2026-09-02T16:00:00-06:00"
CID = "c-test-xrp"


def base_ingest(**lags):
    feeds = {
        "unusual_whales": {"ok": True, "lag_s": 12, "note": "BTC 1m/15m vs KXXRP15M"},
        "x_news": {"ok": True, "lag_s": 20, "note": "no XRP headline, pulled 4 posts"},
        "espn": {"ok": True, "lag_s": 4, "note": "not used crypto15m"},
        "crypto": {"ok": True, "lag_s": 2, "note": "XRP Kraken 1.349"},
        "kalshi": {"ok": True, "lag_s": 1, "note": "KXXRP15M YES 72¢"},
        "polymarket_us": {"ok": True, "lag_s": 1, "note": "no twin"},
    }
    for k, v in lags.items():
        feeds[k]["lag_s"] = v
    return {"ts": TS, "cycle_id": CID, "kind": "ingest", "bot": "scorer", "feeds": feeds}


def base_score(**kw):
    e = {
        "ts": TS,
        "cycle_id": CID,
        "kind": "score",
        "bot": "scorer",
        "edge_pct": 7.0,
        "ask": 0.72,
        "bid": 0.70,
        "model_cents": 79.0,
        "book_cents": 72.0,
        "gate_pass": True,
        "venue": "kalshi",
        "market_id": "KXXRP15M-26SEP021700-00",
        "market": "XRP 15m",
        "book_kind": "crypto15m",
        "feeds_used": ["uw", "crypto", "book"],
        "reason": "UW+Kraken vs Kalshi 15m, ask under cap",
        "weights": {"uw": 0.28, "x": 0.12, "espn": 0.05, "crypto": 0.30, "book": 0.25},
    }
    e.update(kw)
    return e


def write_ledger(path: Path, events: list[dict]) -> None:
    path.write_text("".join(json.dumps(e) + "\n" for e in events))


def expect_fail(event, ledger, needle):
    try:
        validate(event, ledger)
    except ContractError as err:
        if needle not in str(err):
            raise AssertionError(f"expected {needle!r} in {err}") from err
        return
    raise AssertionError(f"expected fail {needle!r}, event passed")


def test_score_requires_model():
    e = base_score()
    del e["model_cents"]
    expect_fail(e, None, "missing model_cents")


def test_score_edge_must_match_model_minus_book():
    expect_fail(base_score(edge_pct=3.0, gate_pass=False), None, "edge_pct")


def test_x_news_no_pull_cannot_be_ok():
    ing = base_ingest()
    ing["feeds"]["x_news"]["note"] = "no pull yet"
    expect_fail(ing, None, "x_news")


def test_gate_pass_needs_ingest(tmp: Path):
    write_ledger(tmp, [])
    expect_fail(base_score(), tmp, "requires ingest")


def test_stale_uw_blocks_gate(tmp: Path):
    write_ledger(tmp, [base_ingest(unusual_whales=8000)])
    expect_fail(base_score(), tmp, "unusual_whales")


def test_fresh_ingest_allows_gate(tmp: Path):
    write_ledger(tmp, [base_ingest()])
    validate(base_score(), tmp)


def test_quiet_needs_reason():
    expect_fail({"ts": TS, "cycle_id": CID, "kind": "quiet", "bot": "scorer"}, None, "reason")


def test_ticket_blocked_without_passing_score(tmp: Path):
    write_ledger(tmp, [base_ingest(), {**base_score(), "gate_pass": False, "edge_pct": 2.0, "model_cents": 74.0, "reason": "gap"}])
    ticket = {
        "ts": TS, "cycle_id": CID, "kind": "ticket", "bot": "trader",
        "venue": "kalshi", "side": "YES", "size_usd": 0.72, "entry_cents": 72,
        "market_id": "KXXRP15M", "market": "XRP 15m",
    }
    expect_fail(ticket, tmp, "gate_pass")


def test_learn_formula_freezes_cross_book():
    sports = {"uw": 0.12, "x": 0.18, "espn": 0.35, "crypto": 0.05, "book": 0.30}
    after, deltas = apply_learn(sports, ["espn", "book", "crypto"], "LOST", "sports")
    assert "crypto" not in deltas
    assert deltas["espn"] == -0.02
    assert abs(sum(after.values()) - 1.0) < 1e-9
    crypto = {"uw": 0.28, "x": 0.12, "espn": 0.05, "crypto": 0.30, "book": 0.25}
    after2, d2 = apply_learn(crypto, ["uw", "espn", "crypto"], "WON", "crypto15m")
    assert "espn" not in d2
    assert d2["uw"] == 0.02
    assert after2["espn"] == crypto["espn"]


def test_full_cycle_then_learn(tmp: Path, weights: Path):
    events = [
        base_ingest(),
        base_score(),
        {
            "ts": TS, "cycle_id": CID, "kind": "ticket", "bot": "trader",
            "venue": "kalshi", "side": "YES", "size_usd": 0.72, "entry_cents": 72,
            "market_id": "KXXRP15M-26SEP021700-00", "market": "XRP 15m",
        },
        {
            "ts": TS, "cycle_id": CID, "kind": "post", "bot": "trader",
            "venue": "kalshi", "market_id": "KXXRP15M-26SEP021700-00",
            "confirmed_live": True, "under_cap": True,
        },
        {
            "ts": TS, "cycle_id": CID, "kind": "fill", "bot": "trader",
            "ticket_id": "k-xrp", "venue": "kalshi", "side": "YES",
            "size_usd": 0.72, "entry_cents": 72, "market_id": "KXXRP15M-26SEP021700-00",
        },
        {
            "ts": TS, "cycle_id": CID, "kind": "mark", "bot": "trader",
            "ticket_id": "k-xrp", "mark_cents": 80.0, "unrealized_usd": 0.08,
        },
        {
            "ts": TS, "cycle_id": CID, "kind": "settle", "bot": "trader",
            "ticket_id": "k-xrp", "result": "WON", "pl_usd": 0.28, "settle_cents": 100,
        },
    ]
    write_ledger(tmp, events)
    for e in events:
        validate(e, tmp if e["kind"] != "ingest" else None)
    env = os.environ.copy()
    env["LEDGER_PATH"] = str(tmp)
    env["LOVABLE_INGEST_TOKEN"] = "replace-test"
    env["LOVABLE_INGEST_URL"] = ""
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "learn_from_settle.py"), "--cycle_id", CID, "--weights", str(weights)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise AssertionError(r.stderr + r.stdout)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["book_kind"] == "crypto15m"
    assert out["deltas"]["uw"] == 0.02
    assert "espn" not in out["deltas"]
    books = json.loads(weights.read_text())
    assert books["settled"]["crypto15m"] == 1
    assert books["gate_pct"] == 6.0


def test_quiet_learn_refused(tmp: Path, weights: Path):
    write_ledger(tmp, [
        base_ingest(),
        {**base_score(), "gate_pass": False, "edge_pct": 2.0, "model_cents": 74.0, "reason": "gap"},
        {"ts": TS, "cycle_id": CID, "kind": "quiet", "bot": "scorer", "reason": "gap under 6%"},
    ])
    env = os.environ.copy()
    env["LEDGER_PATH"] = str(tmp)
    env["LOVABLE_INGEST_TOKEN"] = "replace-test"
    env["LOVABLE_INGEST_URL"] = ""
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "learn_from_settle.py"), "--cycle_id", CID, "--weights", str(weights)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert "quiet" in (r.stderr + r.stdout).lower()


def main() -> None:
    test_score_requires_model()
    test_score_edge_must_match_model_minus_book()
    test_x_news_no_pull_cannot_be_ok()
    test_quiet_needs_reason()
    test_learn_formula_freezes_cross_book()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        test_gate_pass_needs_ingest(p / "a.jsonl")
        test_stale_uw_blocks_gate(p / "b.jsonl")
        test_fresh_ingest_allows_gate(p / "c.jsonl")
        test_ticket_blocked_without_passing_score(p / "d.jsonl")
        test_full_cycle_then_learn(p / "e.jsonl", p / "w.json")
        test_quiet_learn_refused(p / "f.jsonl", p / "w2.json")
    print("ledger contract tests passed")


if __name__ == "__main__":
    main()
