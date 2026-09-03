#!/usr/bin/env python3
"""Ledger event contract. Shared by append_event.py, append-event.mjs, and tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

KINDS = {
    "ingest", "score", "quiet", "ticket", "post", "fill", "mark",
    "flatten", "settle", "learn", "feed_health", "heartbeat",
}
BOTS = {"scorer", "news", "espn", "crypto", "trader"}
VENUES = {"kalshi", "polymarket_us"}
BOOK_KINDS = {"sports", "crypto15m"}
WEIGHT_KEYS = ("uw", "x", "espn", "crypto", "book")
INGEST_FEEDS = (
    "unusual_whales", "x_news", "espn", "crypto", "kalshi", "polymarket_us",
)
FEED_TO_WEIGHT = {
    "unusual_whales": "uw",
    "x_news": "x",
    "espn": "espn",
    "crypto": "crypto",
    "kalshi": "book",
    "polymarket_us": "book",
}
RESULTS = {"WON", "LOST"}
HEALTH = {"ok", "warn", "bad"}
SIDES = {"YES", "NO", "BUY", "SELL"}
CONSTRAINTS = {"scoring", "execution"}
GATE_PCT = 6.0
ASK_CAP = 0.80
LEARN_STEP = 0.02
MIN_WEIGHT = 0.02

# Kill-switch lag (seconds). Gate cannot pass if ingest is older than this.
STALE_S = {
    "unusual_whales": 600,
    "x_news": 300,
    "espn": 45,
    "crypto": 180,
    "kalshi": 20,
    "polymarket_us": 20,
}

DEFAULT_WEIGHTS = {
    "sports": {"uw": 0.12, "x": 0.18, "espn": 0.35, "crypto": 0.05, "book": 0.30},
    "crypto15m": {"uw": 0.28, "x": 0.12, "espn": 0.05, "crypto": 0.30, "book": 0.25},
}


class ContractError(SystemExit):
    pass


def fail(msg: str) -> None:
    raise ContractError(msg)


def _num(event: dict, key: str) -> float:
    if key not in event or event[key] is None:
        fail(f"missing {key}")
    try:
        return float(event[key])
    except (TypeError, ValueError):
        fail(f"{key} must be a number")
        return 0.0


def _str(event: dict, key: str) -> str:
    val = event.get(key)
    if not val or not str(val).strip():
        fail(f"missing {key}")
    return str(val)


def _bool(event: dict, key: str) -> bool:
    if key not in event or not isinstance(event[key], bool):
        fail(f"{key} must be a boolean")
    return event[key]


def load_events(ledger_path: Path) -> list[dict]:
    if not ledger_path or not ledger_path.is_file():
        return []
    out = []
    for line in ledger_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def last_of(events: list[dict], cycle_id: str, kind: str) -> dict | None:
    found = None
    for e in events:
        if e.get("cycle_id") == cycle_id and e.get("kind") == kind:
            found = e
    return found


def gate_pass_value(event: dict) -> bool:
    return (
        float(event.get("edge_pct") or 0) >= GATE_PCT
        and float(event.get("ask") or 1) < ASK_CAP
        and event.get("venue") in VENUES
    )


def ingest_kill_reason(ingest: dict, book_kind: str | None) -> str | None:
    feeds = ingest.get("feeds") or {}
    for name in INGEST_FEEDS:
        row = feeds.get(name) or {}
        note = str(row.get("note") or "").lower()
        ok = row.get("ok")
        try:
            lag = float(row.get("lag_s"))
        except (TypeError, ValueError):
            lag = 10**9
        if name == "x_news" and ("no pull" in note or "no pull yet" in note):
            return "x_news did not pull"
        if name == "espn" and book_kind == "crypto15m":
            continue
        if name == "crypto" and book_kind == "sports":
            if ok is False:
                return f"{name} ok=false"
            continue
        if ok is False:
            return f"{name} ok=false"
        limit = STALE_S[name]
        if name == "espn" and book_kind != "sports":
            continue
        if lag > limit:
            return f"{name} lag_s {lag:.0f} > {limit}s stale"
    return None


def validate_weights(weights: dict, label: str) -> None:
    if not isinstance(weights, dict):
        fail(f"{label} must be an object")
    missing = [k for k in WEIGHT_KEYS if k not in weights]
    if missing:
        fail(f"{label} missing keys {missing}")
    total = 0.0
    for k in WEIGHT_KEYS:
        try:
            v = float(weights[k])
        except (TypeError, ValueError):
            fail(f"{label}.{k} must be a number")
            return
        if v < MIN_WEIGHT - 1e-9:
            fail(f"{label}.{k} {v} below min {MIN_WEIGHT}")
        total += v
    if abs(total - 1.0) > 0.02:
        fail(f"{label} must sum to 1.0, got {total:.4f}")


def apply_learn(weights: dict, feeds_used: list[str], result: str, book_kind: str) -> tuple[dict, dict]:
    w = {k: float(weights[k]) for k in WEIGHT_KEYS}
    sign = 1.0 if result == "WON" else -1.0
    deltas = {k: 0.0 for k in WEIGHT_KEYS}
    used = [k for k in feeds_used if k in w]
    if not used:
        used = list(WEIGHT_KEYS)
    frozen = set()
    if book_kind == "crypto15m":
        frozen.add("espn")
    if book_kind == "sports":
        frozen.add("crypto")
    for k in used:
        if k in frozen:
            continue
        deltas[k] = round(sign * LEARN_STEP, 4)
        w[k] = max(MIN_WEIGHT, w[k] + deltas[k])
    held = {k: float(weights[k]) for k in frozen}
    free = [k for k in WEIGHT_KEYS if k not in frozen]
    room = max(MIN_WEIGHT * len(free), 1.0 - sum(held.values()))
    sub = sum(w[k] for k in free) or 1.0
    out = dict(held)
    for k in free:
        out[k] = max(MIN_WEIGHT, round(w[k] / sub * room, 4))
    drift = round(1.0 - sum(out.values()), 4)
    pivot = "book" if "book" not in frozen else free[-1]
    out[pivot] = round(out[pivot] + drift, 4)
    return out, {k: v for k, v in deltas.items() if v}


def validate(event: dict, ledger_path: Path | None = None) -> None:
    if not isinstance(event, dict):
        fail("event must be a JSON object")
    for key in ("ts", "cycle_id", "kind", "bot"):
        if not event.get(key):
            fail(f"missing {key}")
    if event["kind"] not in KINDS:
        fail(f"unknown kind {event['kind']}")
    if event["bot"] not in BOTS:
        fail(f"unknown bot {event['bot']}")

    kind = event["kind"]
    events = load_events(ledger_path) if ledger_path else []

    if kind == "ingest":
        _validate_ingest(event)
    elif kind == "score":
        _validate_score(event, events)
    elif kind == "quiet":
        _str(event, "reason")
    elif kind == "ticket":
        _validate_ticket(event, events)
    elif kind == "post":
        _validate_post(event, events)
    elif kind == "fill":
        _validate_fill(event, events)
    elif kind == "mark":
        _str(event, "ticket_id")
        _num(event, "mark_cents")
    elif kind == "flatten":
        _str(event, "ticket_id")
        _str(event, "trigger")
    elif kind == "settle":
        _validate_settle(event)
    elif kind == "learn":
        _validate_learn(event, events)
    elif kind == "feed_health":
        _str(event, "name")
        if event.get("state") not in HEALTH:
            fail("state must be ok|warn|bad")
        _str(event, "detail")
    elif kind == "heartbeat":
        _str(event, "role")
        if event.get("constraint") not in CONSTRAINTS:
            fail("constraint must be scoring|execution")


def _validate_ingest(event: dict) -> None:
    feeds = event.get("feeds")
    if not isinstance(feeds, dict):
        fail("ingest requires feeds{}")
    missing = [name for name in INGEST_FEEDS if name not in feeds]
    if missing:
        fail(f"ingest missing feeds {missing}")
    for name in INGEST_FEEDS:
        row = feeds[name]
        if not isinstance(row, dict):
            fail(f"feeds.{name} must be an object")
        if not isinstance(row.get("ok"), bool):
            fail(f"feeds.{name}.ok must be boolean")
        try:
            float(row.get("lag_s"))
        except (TypeError, ValueError):
            fail(f"feeds.{name}.lag_s must be a number")
        if not str(row.get("note") or "").strip():
            fail(f"feeds.{name}.note required")
        note = str(row.get("note")).lower()
        if name == "x_news" and row.get("ok") is True and "no pull" in note:
            fail("x_news ok=true cannot be 'no pull' — pull or set ok=false")


def _validate_score(event: dict, events: list[dict]) -> None:
    edge = _num(event, "edge_pct")
    ask = _num(event, "ask")
    _num(event, "bid")
    model = _num(event, "model_cents")
    book = _num(event, "book_cents")
    if not (0 <= model <= 100) or not (0 <= book <= 100):
        fail("model_cents and book_cents must be 0–100")
    if abs((model - book) - edge) > 0.25:
        fail(f"edge_pct {edge} must equal model_cents-book_cents {model - book:.2f}")
    if abs(ask - book / 100.0) > 0.03:
        fail("ask must match book_cents/100")
    _str(event, "reason")
    _str(event, "market_id")
    venue = _str(event, "venue")
    if venue not in VENUES:
        fail("venue must be kalshi or polymarket_us")
    book_kind = _str(event, "book_kind")
    if book_kind not in BOOK_KINDS:
        fail("book_kind must be sports or crypto15m")
    used = event.get("feeds_used")
    if not isinstance(used, list) or not used:
        fail("score requires feeds_used[] (uw|x|espn|crypto|book)")
    bad = [x for x in used if x not in WEIGHT_KEYS]
    if bad:
        fail(f"unknown feeds_used {bad}")
    if "weights" in event:
        validate_weights(event["weights"], "weights")
    expected = gate_pass_value(event)
    if event.get("gate_pass") is not expected:
        fail(f"gate_pass must be {expected} (edge>={GATE_PCT:g} and ask<{ASK_CAP} and kalshi|polymarket_us)")

    ingest = last_of(events, event["cycle_id"], "ingest")
    if expected:
        if not ingest:
            fail("gate_pass true requires ingest in the same cycle_id")
        why = ingest_kill_reason(ingest, book_kind)
        if why:
            fail(f"gate_pass true blocked: {why}")


def _validate_ticket(event: dict, events: list[dict]) -> None:
    venue = _str(event, "venue")
    if venue not in VENUES:
        fail("venue must be kalshi or polymarket_us")
    side = _str(event, "side")
    if side not in SIDES:
        fail("side must be YES|NO|BUY|SELL")
    _num(event, "size_usd")
    _num(event, "entry_cents")
    _str(event, "market_id")
    _str(event, "market")
    if events:
        score = last_of(events, event["cycle_id"], "score")
        if score is None or score.get("gate_pass") is not True:
            fail("ticket requires score.gate_pass true in this cycle")
        if last_of(events, event["cycle_id"], "quiet") is not None:
            fail("ticket after quiet in this cycle")


def _validate_post(event: dict, events: list[dict]) -> None:
    venue = _str(event, "venue")
    if venue not in VENUES:
        fail("venue must be kalshi or polymarket_us")
    _str(event, "market_id")
    if event.get("confirmed_live") is not True:
        fail("post requires confirmed_live true")
    if event.get("under_cap") is not True:
        fail("post requires under_cap true")
    if events:
        score = last_of(events, event["cycle_id"], "score")
        if score is None or score.get("gate_pass") is not True:
            fail("post requires score.gate_pass true in this cycle")


def _validate_fill(event: dict, events: list[dict]) -> None:
    _str(event, "ticket_id")
    venue = _str(event, "venue")
    if venue not in VENUES:
        fail("venue must be kalshi or polymarket_us")
    _str(event, "side")
    _num(event, "size_usd")
    _num(event, "entry_cents")
    _str(event, "market_id")
    if events:
        score = last_of(events, event["cycle_id"], "score")
        if score is None or score.get("gate_pass") is not True:
            fail("fill requires score.gate_pass true in this cycle")
        if last_of(events, event["cycle_id"], "post") is None:
            fail("fill requires post in the same cycle_id")
        if last_of(events, event["cycle_id"], "quiet") is not None:
            fail("fill after quiet in this cycle")


def _validate_settle(event: dict) -> None:
    _str(event, "ticket_id")
    if event.get("result") not in RESULTS:
        fail("result must be WON or LOST")
    _num(event, "pl_usd")
    _num(event, "settle_cents")


def _validate_learn(event: dict, events: list[dict]) -> None:
    if event.get("bot") != "scorer":
        fail("learn must be bot=scorer")
    book_kind = _str(event, "book_kind")
    if book_kind not in BOOK_KINDS:
        fail("book_kind must be sports or crypto15m")
    _str(event, "gate_notes")
    deltas = event.get("weight_deltas")
    if not isinstance(deltas, dict) or not deltas:
        fail("learn requires weight_deltas")
    extra = [k for k in deltas if k not in WEIGHT_KEYS]
    if extra:
        fail(f"weight_deltas unknown keys {extra}")
    validate_weights(event.get("weights") or {}, "weights")
    if "gate_pct" in event and float(event["gate_pct"]) != GATE_PCT:
        fail(f"gate stays {GATE_PCT:g} until 60 settled tickets")
    settle = last_of(events, event["cycle_id"], "settle")
    if events and settle is None:
        fail("learn requires settle in the same cycle_id")
    quiet = last_of(events, event["cycle_id"], "quiet")
    if quiet is not None and settle is None:
        fail("quiet cycles must not emit learn")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ledger = Path(argv[argv.index("--ledger") + 1]) if "--ledger" in argv else None
    if argv[:1] == ["--file"]:
        event = json.loads(Path(argv[1]).read_text())
    else:
        event = json.loads(sys.stdin.read())
    validate(event, ledger)
    print("ok", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except ContractError as err:
        print(str(err) or "invalid event", file=sys.stderr)
        sys.exit(1)
