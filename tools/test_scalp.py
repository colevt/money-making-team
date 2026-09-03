#!/usr/bin/env python3
"""Buy-low / sell-high tape, compose, inventory, and self-learn."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from compose_score import buy_ok, compose, sell_ok  # noqa: E402
from crypto_tape import bars_from_ohlc, merge_symbol, summarize  # noqa: E402
from inventory import close, load, open_buy, qty_wei_of, symbol_of  # noqa: E402
from ledger_contract import apply_scalp_learn, DEFAULT_SCALP  # noqa: E402

TS = "2026-09-02T16:00:00-06:00"
CID = "c-scalp-eth"


def dip_bars():
    """Last print is the local low, ~0.8% under VWAP."""
    rows = []
    t = 1_700_000_000
    px = 100.0
    for i in range(10):
        close = px - i * 0.08
        rows.append([t + i * 60, close, close + 0.05, close - 0.05, close, close, 10])
    return bars_from_ohlc(rows)


def rally_bars(last=100.5):
    rows = []
    t = 1_700_000_000
    for i, close in enumerate([99.6, 99.7, 99.9, 100.1, 100.3, last]):
        rows.append([t + i * 60, close, close + 0.05, close - 0.05, close, close, 10])
    return bars_from_ohlc(rows)


def test_symbol_map():
    assert symbol_of("USDC-WETH") == "ETH"
    assert symbol_of("WBTC") == "BTC"


def test_summarize_flags_local_low():
    stats = summarize(dip_bars(), lookback=12)
    assert stats["ok"]
    assert stats["at_low"] is True
    assert stats["dip_pct"] > 0.35
    assert stats["last"] < stats["vwap"]


def test_buy_ok_and_flow_dump():
    row = merge_symbol(dip_bars(), flow_sign=1, x_sign=1)
    ok, why = buy_ok(row, dict(DEFAULT_SCALP), held=False)
    assert ok, why
    dumped = merge_symbol(dip_bars(), flow_sign=-1)
    ok2, why2 = buy_ok(dumped, dict(DEFAULT_SCALP), held=False)
    assert not ok2
    assert "dumping" in why2


def test_sell_ok_take_and_stop():
    row = merge_symbol(rally_bars(100.5))
    pos = {"entry_px": 100.0, "size_usd": 1.0}
    ok, why = sell_ok(row, pos, dict(DEFAULT_SCALP))
    assert ok, why
    assert "take" in why or "high" in why
    stop_row = merge_symbol(rally_bars(99.4))
    ok2, why2 = sell_ok(stop_row, pos, dict(DEFAULT_SCALP))
    assert ok2, why2
    assert "stop" in why2
    hold_row = merge_symbol(rally_bars(100.1))
    ok3, _ = sell_ok(hold_row, pos, dict(DEFAULT_SCALP))
    assert not ok3


def test_compose_buy_then_sell(tmp: Path):
    os.environ["INVENTORY_PATH"] = str(tmp / "inv.json")
    os.environ["CRYPTO_TAPE_PATH"] = str(tmp / "tape.json")
    weights = {
        "books": {
            "crypto_scalp": {"uw": 0.30, "x": 0.10, "espn": 0.05, "crypto": 0.35, "book": 0.20},
        },
        "scalp": dict(DEFAULT_SCALP),
    }
    tape = {"symbols": {"ETH": merge_symbol(dip_bars(), oneinch_px=99.2, flow_sign=1)}}
    out = compose(CID, tape=tape, books=weights, inventory={"positions": {}}, size_usd=1.0, ts=TS)
    buys = [s for s in out["scores"] if s["side"] == "BUY" and s["market_id"] == "USDC-WETH"]
    assert len(buys) == 1
    buy = buys[0]
    assert buy["book_kind"] == "crypto_scalp"
    assert buy["gate_pass"] is True
    assert buy["edge_pct"] >= 0.35
    assert "features" in buy
    open_buy("ETH", qty_wei=10**15, entry_px=99.2, size_usd=1.0, ticket_id="t-eth", cycle_id=CID, market_id="USDC-WETH")
    inv = load()
    high = {"symbols": {"ETH": merge_symbol(rally_bars(100.0), oneinch_px=100.0, flow_sign=0)}}
    out2 = compose(CID, tape=high, books=weights, inventory=inv, size_usd=1.0, ts=TS)
    sells = [s for s in out2["scores"] if s["side"] == "SELL"]
    assert len(sells) == 1
    assert sells[0]["gate_pass"] is True
    assert qty_wei_of("ETH") == 10**15
    closed = close("ETH", exit_px=100.0)
    assert closed["pl_usd"] > 0
    assert qty_wei_of("ETH") is None


def test_scalp_params_learn_from_pnl():
    won = apply_scalp_learn(DEFAULT_SCALP, "WON")
    lost = apply_scalp_learn(DEFAULT_SCALP, "LOST")
    assert won["min_dip_pct"] < DEFAULT_SCALP["min_dip_pct"]
    assert lost["min_dip_pct"] > DEFAULT_SCALP["min_dip_pct"]
    runaway = dict(DEFAULT_SCALP)
    runaway["min_dip_pct"] = 1.20
    again = apply_scalp_learn(runaway, "LOST")
    assert again["min_dip_pct"] <= 1.20


def test_learn_from_scalp_settle(tmp: Path):
    from test_ledger_contract import base_ingest, write_ledger, validate  # noqa: E402

    ingest = base_ingest()
    ingest["cycle_id"] = CID
    score = {
        "ts": TS, "cycle_id": CID, "kind": "score", "bot": "scorer",
        "edge_pct": 0.5, "ask": 0.995, "bid": 0.995,
        "model_cents": 100.0, "book_cents": 99.5, "gate_pass": True,
        "venue": "onchain", "side": "BUY", "market_id": "USDC-WETH", "market": "ETH scalp",
        "book_kind": "crypto_scalp", "feeds_used": ["crypto", "book", "uw"],
        "reason": "local low",
        "weights": {"uw": 0.30, "x": 0.10, "espn": 0.05, "crypto": 0.35, "book": 0.20},
        "features": {"dip_pct": 0.5, "flow_sign": 1, "at_low": True},
    }
    events = [
        ingest,
        score,
        {
            "ts": TS, "cycle_id": CID, "kind": "ticket", "bot": "trader",
            "venue": "onchain", "side": "BUY", "size_usd": 1.0, "entry_cents": 99.5,
            "market_id": "USDC-WETH", "market": "ETH scalp",
        },
        {
            "ts": TS, "cycle_id": CID, "kind": "post", "bot": "trader",
            "venue": "onchain", "market_id": "USDC-WETH",
            "confirmed_live": True, "under_cap": True,
        },
        {
            "ts": TS, "cycle_id": CID, "kind": "fill", "bot": "trader",
            "ticket_id": "s-eth", "venue": "onchain", "side": "BUY",
            "size_usd": 1.0, "entry_cents": 99.5, "market_id": "USDC-WETH",
        },
        {
            "ts": TS, "cycle_id": CID, "kind": "settle", "bot": "trader",
            "ticket_id": "s-eth", "result": "WON", "pl_usd": 0.004, "settle_cents": 100.0,
        },
    ]
    ledger = tmp / "e.jsonl"
    weights = tmp / "w.json"
    tape = tmp / "learn.jsonl"
    write_ledger(ledger, events)
    for e in events:
        validate(e, ledger if e["kind"] != "ingest" else None)
    env = os.environ.copy()
    env["LEDGER_PATH"] = str(ledger)
    env["LEARN_TAPE_PATH"] = str(tape)
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "learn_from_settle.py"), "--cycle_id", CID, "--weights", str(weights)],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise AssertionError(r.stderr + r.stdout)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["book_kind"] == "crypto_scalp"
    assert out["deltas"]["crypto"] == 0.02
    assert "espn" not in out["deltas"]
    books = json.loads(weights.read_text())
    assert books["settled"]["crypto_scalp"] == 1
    assert books["scalp"]["min_dip_pct"] < DEFAULT_SCALP["min_dip_pct"]
    assert tape.is_file()
    row = json.loads(tape.read_text().splitlines()[-1])
    assert row["features"]["at_low"] is True


def main() -> None:
    test_symbol_map()
    test_summarize_flags_local_low()
    test_buy_ok_and_flow_dump()
    test_sell_ok_take_and_stop()
    test_scalp_params_learn_from_pnl()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        os.environ["INVENTORY_PATH"] = str(p / "inv.json")
        test_compose_buy_then_sell(p)
        test_learn_from_scalp_settle(p)
    print("scalp tests passed")


if __name__ == "__main__":
    main()
