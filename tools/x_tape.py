#!/usr/bin/env python3
"""Rolling X tape. Last pull is the prior for this one (~2 minutes apart).

Grok bots do not keep chat memory across scans. This file is that memory.

  python3 tools/x_tape.py              # before search_news: queries + last delta
  python3 tools/x_tape.py --json       # same, machine-readable
  python3 tools/x_tape.py --record     # after the pull: stdin posts → tape + ingest note

Record shape (stdin JSON):

  {
    "cycle_id": "...",
    "market": "XRP 15m",
    "market_id": "KXXRP15M-...",
    "book_cents": 72,
    "queries": ["XRP", "XRP 15m"],
    "posts": [
      {"id": "...", "text": "...", "author": "...", "ts": "...", "url": "...", "tickers": ["XRP"]}
    ]
  }

A raw list of posts or strings is also accepted. First record is a baseline.
The next scan diffs against it: new prints, repeats, book lag, next queries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("X_TAPE_PATH", ROOT / "ledger" / "x_tape.json"))
KEEP_PULLS = 8
MAX_POSTS = 40
TEXT_KEEP = 240
BOOK_MOVE_CENTS = 2.0
FRESH_S = 180  # ~2–3 min scans; still usable under the 300s x_news stale cap
BASE_QUERIES = ("BTC", "ETH", "SOL", "XRP", "IBIT", "MSTR")
KNOWN = {
    "BTC", "ETH", "SOL", "XRP", "IBIT", "MSTR", "BITCOIN", "ETHEREUM",
    "NFL", "NBA", "MLB", "NHL", "CFB",
}

TICKER_RE = re.compile(
    r"(?:(?<![A-Za-z])(?:\$|#)?(BTC|ETH|SOL|XRP|IBIT|MSTR|NFL|NBA|MLB|NHL)\b)"
    r"|(?:(?<![A-Za-z])\$([A-Z]{2,5})\b)",
    re.I,
)


def now_dt() -> datetime:
    try:
        return datetime.now(ZoneInfo("America/Denver"))
    except Exception:
        return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_dt().isoformat(timespec="seconds")


def parse_ts(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def age_s(iso: str | None, now: datetime | None = None) -> float | None:
    dt = parse_ts(iso)
    if dt is None:
        return None
    now = now or now_dt()
    return max(0.0, (now - dt).total_seconds())


def tape_path() -> Path:
    return Path(os.environ.get("X_TAPE_PATH", OUT))


def load_tape(path: Path | None = None) -> dict:
    p = path or tape_path()
    if not p.is_file():
        return {"ts": None, "pulls": []}
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {"ts": None, "pulls": []}
    if not isinstance(data, dict):
        return {"ts": None, "pulls": []}
    data.setdefault("pulls", [])
    return data


def save_tape(tape: dict, path: Path | None = None) -> Path:
    p = path or tape_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(tape, indent=2) + "\n")
    return p


def _text_of(post) -> str:
    if isinstance(post, str):
        return post.strip()
    if not isinstance(post, dict):
        return ""
    for key in ("text", "title", "headline", "body", "content", "note"):
        val = post.get(key)
        if val:
            return str(val).strip()
    return ""


def fingerprint(post) -> str:
    if isinstance(post, dict):
        pid = post.get("id") or post.get("post_id") or post.get("tweet_id")
        if pid:
            return "id:" + str(pid)
        url = str(post.get("url") or post.get("link") or "").split("?")[0].rstrip("/")
        if url:
            return "url:" + url.lower()
    text = re.sub(r"\s+", " ", _text_of(post).lower())
    if not text:
        return "empty"
    return "t:" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def extract_tickers(post, extra: list | None = None) -> list[str]:
    found: list[str] = []
    if isinstance(post, dict):
        raw = post.get("tickers") or post.get("symbols") or []
        if isinstance(raw, str):
            raw = [raw]
        for t in raw:
            tok = str(t).upper().replace("$", "").replace("#", "").strip()
            if tok:
                found.append("BTC" if tok == "BITCOIN" else "ETH" if tok == "ETHEREUM" else tok)
    text = _text_of(post)
    for m in TICKER_RE.finditer(text):
        tok = (m.group(1) or m.group(2) or "").upper()
        if tok == "BITCOIN":
            tok = "BTC"
        elif tok == "ETHEREUM":
            tok = "ETH"
        if tok:
            found.append(tok)
    for t in extra or []:
        tok = str(t).upper().replace("$", "").strip()
        if tok:
            found.append(tok)
    out = []
    seen = set()
    for t in found:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:8]


def normalize_post(post, market_tickers: list[str] | None = None) -> dict | None:
    text = _text_of(post)
    if not text:
        return None
    src = post if isinstance(post, dict) else {}
    tickers = extract_tickers(post, market_tickers)
    return {
        "fp": fingerprint(post),
        "id": src.get("id") or src.get("post_id") or src.get("tweet_id"),
        "author": src.get("author") or src.get("user") or src.get("handle"),
        "ts": src.get("ts") or src.get("created_at") or src.get("time"),
        "text": text[:TEXT_KEEP],
        "tickers": tickers,
        "url": src.get("url") or src.get("link"),
    }


def parse_record(payload) -> dict:
    if isinstance(payload, list):
        payload = {"posts": payload}
    if not isinstance(payload, dict):
        raise ValueError("record must be a JSON object or list")
    posts_in = payload.get("posts") or payload.get("items") or payload.get("tweets") or []
    if isinstance(posts_in, dict):
        posts_in = posts_in.get("posts") or posts_in.get("data") or []
    if not isinstance(posts_in, list):
        posts_in = []
    market = str(payload.get("market") or payload.get("market_id") or "").strip()
    market_tickers = extract_tickers({"text": market, "tickers": payload.get("tickers") or []})
    posts = []
    seen = set()
    for raw in posts_in[: MAX_POSTS * 2]:
        row = normalize_post(raw, market_tickers)
        if not row or row["fp"] in seen:
            continue
        seen.add(row["fp"])
        posts.append(row)
        if len(posts) >= MAX_POSTS:
            break
    book = payload.get("book_cents")
    try:
        book_cents = float(book) if book is not None else None
    except (TypeError, ValueError):
        book_cents = None
    queries = payload.get("queries") or payload.get("search") or []
    if isinstance(queries, str):
        queries = [queries]
    return {
        "cycle_id": payload.get("cycle_id"),
        "market": market or None,
        "market_id": payload.get("market_id"),
        "book_cents": book_cents,
        "queries": [str(q) for q in queries if str(q).strip()][:12],
        "posts": posts,
    }


def _ticker_counts(posts: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in posts:
        for t in p.get("tickers") or []:
            counts[t] = counts.get(t, 0) + 1
    return counts


def _headline(post: dict) -> str:
    text = re.sub(r"\s+", " ", str(post.get("text") or "")).strip()
    return text[:100]


def analyze(current: dict, prior: dict | None) -> dict:
    posts = current.get("posts") or []
    prior_posts = (prior or {}).get("posts") or []
    prior_fps = {p.get("fp") for p in prior_posts if p.get("fp")}
    new_posts = [p for p in posts if p.get("fp") not in prior_fps]
    repeat_posts = [p for p in posts if p.get("fp") in prior_fps]
    gone = [p for p in prior_posts if p.get("fp") not in {x.get("fp") for x in posts}]
    now_counts = _ticker_counts(posts)
    prior_counts = _ticker_counts(prior_posts)
    accelerating = []
    for t, n in now_counts.items():
        if n > prior_counts.get(t, 0):
            accelerating.append(t)
    fresh_tickers = [t for t in now_counts if t not in prior_counts]
    continuing = [t for t in now_counts if t in prior_counts]
    book_now = current.get("book_cents")
    book_prior = (prior or {}).get("book_cents")
    book_delta = None
    if book_now is not None and book_prior is not None:
        book_delta = round(float(book_now) - float(book_prior), 2)
    book_flat = book_delta is not None and abs(book_delta) < BOOK_MOVE_CENTS
    book_moved = book_delta is not None and abs(book_delta) >= BOOK_MOVE_CENTS
    lag_candidates = []
    priced_in = []
    if prior and continuing:
        if book_flat:
            lag_candidates = list(continuing)
        elif book_moved:
            priced_in = list(continuing)
    baseline = prior is None
    if baseline:
        decision = "baseline — next scan (~2 min) diffs this pull"
    elif new_posts and book_flat:
        decision = "fresh print, book flat — lag detector; include x in feeds_used"
    elif lag_candidates:
        decision = "same headlines as last pull, book still flat — lag confirmed"
    elif priced_in:
        decision = "headline already on tape and book moved — do not chase"
    elif not new_posts:
        decision = "no new posts vs last pull — x is quiet, do not invent a story"
    else:
        decision = "new posts, book not comparable — use as lag next to OSIRIS, not a standalone buy"
    next_queries = list(BASE_QUERIES)
    for t in fresh_tickers + accelerating + continuing:
        if t not in next_queries:
            next_queries.append(t)
    for q in current.get("queries") or []:
        if q not in next_queries:
            next_queries.append(q)
    if current.get("market"):
        m = str(current["market"])
        if m not in next_queries:
            next_queries.insert(0, m)
    next_queries = next_queries[:10]
    n_new = len(new_posts)
    n_keep = len(repeat_posts)
    bits = [f"{n_new} new / {n_keep} kept"]
    if baseline:
        bits = [f"baseline {len(posts)} posts"]
    if fresh_tickers:
        bits.append("fresh " + ",".join(fresh_tickers[:4]))
    if lag_candidates:
        bits.append("lag " + ",".join(lag_candidates[:4]))
    if priced_in:
        bits.append("priced " + ",".join(priced_in[:4]))
    if book_delta is not None:
        bits.append(f"book {book_delta:+.1f}¢")
    if new_posts:
        bits.append(_headline(new_posts[0]))
    elif posts:
        bits.append(_headline(posts[0]))
    note = " · ".join(bits)
    return {
        "baseline": baseline,
        "n_posts": len(posts),
        "n_new": n_new,
        "n_repeat": n_keep,
        "n_gone": len(gone),
        "new_headlines": [_headline(p) for p in new_posts[:5]],
        "repeat_headlines": [_headline(p) for p in repeat_posts[:3]],
        "fresh_tickers": fresh_tickers,
        "accelerating": accelerating,
        "lag_candidates": lag_candidates,
        "priced_in": priced_in,
        "book_delta_cents": book_delta,
        "book_flat": book_flat,
        "decision": decision,
        "next_queries": next_queries,
        "note": note,
        "ok": True,
    }


def ingest_row(analysis: dict, lag_s: float) -> dict:
    note = analysis.get("note") or "x tape pulled"
    if analysis.get("n_posts", 0) == 0:
        note = "pulled 0 posts · tape recorded"
    return {"ok": True, "lag_s": round(lag_s, 1), "note": note}


def record(payload, tape: dict | None = None, ts: str | None = None) -> dict:
    current = parse_record(payload)
    tape = tape if tape is not None else load_tape()
    pulls = list(tape.get("pulls") or [])
    prior = pulls[-1] if pulls else None
    analysis = analyze(current, prior)
    ts = ts or now_iso()
    pull = {
        "ts": ts,
        "cycle_id": current.get("cycle_id"),
        "market": current.get("market"),
        "market_id": current.get("market_id"),
        "book_cents": current.get("book_cents"),
        "queries": current.get("queries"),
        "posts": current["posts"],
        "n_new": analysis["n_new"],
        "n_repeat": analysis["n_repeat"],
        "note": analysis["note"],
        "decision": analysis["decision"],
        "next_queries": analysis["next_queries"],
        "lag_candidates": analysis["lag_candidates"],
        "priced_in": analysis["priced_in"],
        "fresh_tickers": analysis["fresh_tickers"],
    }
    pulls.append(pull)
    tape = {
        "ts": ts,
        "pulls": pulls[-KEEP_PULLS:],
        "last": {
            "ts": ts,
            "cycle_id": pull.get("cycle_id"),
            "note": analysis["note"],
            "decision": analysis["decision"],
            "next_queries": analysis["next_queries"],
            "lag_candidates": analysis["lag_candidates"],
            "priced_in": analysis["priced_in"],
            "fresh_tickers": analysis["fresh_tickers"],
            "n_new": analysis["n_new"],
            "n_posts": analysis["n_posts"],
            "book_cents": current.get("book_cents"),
            "market": current.get("market"),
        },
    }
    save_tape(tape)
    lag = 0.0
    analysis["ingest"] = ingest_row(analysis, lag)
    analysis["ts"] = ts
    analysis["cycle_id"] = current.get("cycle_id")
    analysis["wrote"] = str(tape_path())
    return analysis


def plan(tape: dict | None = None) -> dict:
    tape = tape if tape is not None else load_tape()
    last = tape.get("last") or ((tape.get("pulls") or [None])[-1])
    if not last:
        return {
            "have_tape": False,
            "age_s": None,
            "fresh": False,
            "next_queries": list(BASE_QUERIES),
            "watch": [],
            "lag_candidates": [],
            "priced_in": [],
            "last_note": None,
            "decision": "no tape yet — this pull is the baseline for the next (~2 min) scan",
            "how": "search_news those queries, then python3 tools/x_tape.py --record",
        }
    age = age_s(last.get("ts"))
    fresh = age is not None and age <= FRESH_S
    stale = age is not None and age > 300
    decision = last.get("decision") or "use last delta as the prior for this pull"
    if stale:
        decision = f"tape {age:.0f}s old — still pull; treat as a new baseline if headlines look cold"
    elif fresh:
        decision = last.get("decision") or "last pull is ~2 min old — search next_queries and diff"
    return {
        "have_tape": True,
        "age_s": round(age, 1) if age is not None else None,
        "fresh": fresh,
        "next_queries": last.get("next_queries") or list(BASE_QUERIES),
        "watch": last.get("fresh_tickers") or last.get("lag_candidates") or [],
        "lag_candidates": last.get("lag_candidates") or [],
        "priced_in": last.get("priced_in") or [],
        "last_note": last.get("note"),
        "last_ts": last.get("ts"),
        "market": last.get("market"),
        "book_cents": last.get("book_cents"),
        "decision": decision,
        "how": "search_news next_queries + a fresh scan, then --record this pull against the tape",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rolling X tape across ~2 min scans")
    parser.add_argument("--record", action="store_true", help="stdin JSON of this pull")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--file", help="read record JSON from a file instead of stdin")
    args = parser.parse_args()
    if args.record:
        raw = Path(args.file).read_text() if args.file else sys.stdin.read()
        if not raw.strip():
            raise SystemExit("x_tape --record needs JSON on stdin or --file")
        analysis = record(json.loads(raw))
        if args.json:
            print(json.dumps(analysis["ingest"]))
        else:
            print(f"OK x_tape  {analysis['ingest']['note']}", file=sys.stderr)
            print(analysis["decision"], file=sys.stderr)
            print("next_queries: " + ", ".join(analysis["next_queries"]), file=sys.stderr)
            print(json.dumps(analysis["ingest"]))
        return
    planned = plan()
    if args.json:
        print(json.dumps(planned))
        return
    if not planned["have_tape"]:
        print("no X tape yet — this pull is the baseline", file=sys.stderr)
    else:
        age = planned.get("age_s")
        age_txt = f"{age:.0f}s ago" if age is not None else "unknown age"
        print(f"last X pull {age_txt}: {planned.get('last_note')}", file=sys.stderr)
    print(planned["decision"], file=sys.stderr)
    print("search: " + ", ".join(planned["next_queries"]), file=sys.stderr)
    print(json.dumps({
        "next_queries": planned["next_queries"],
        "lag_candidates": planned["lag_candidates"],
        "priced_in": planned["priced_in"],
        "watch": planned["watch"],
        "age_s": planned.get("age_s"),
        "decision": planned["decision"],
    }))


if __name__ == "__main__":
    main()
