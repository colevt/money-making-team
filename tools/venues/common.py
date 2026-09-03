"""Shared HTTP + env helpers for venue clients. Never print secrets."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
UA = "money-team-venues/1"


def load_env(path: Path | None = None) -> None:
    p = path or (ROOT / ".env")
    if not p.is_file():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def env(*names: str, default: str = "") -> str:
    for name in names:
        val = os.environ.get(name)
        if val and val.strip():
            return val.strip()
    return default


def has_env(*names: str) -> bool:
    return all(bool(env(n)) for n in names)


def http_json(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: dict | bytes | None = None,
    timeout: int = 20,
) -> dict:
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        if isinstance(body, dict):
            data = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        else:
            data = body
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return {"ok": True, "status": resp.status}
            return json.loads(raw)
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:400]
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = {"error": detail}
        parsed["ok"] = False
        parsed["status"] = err.code
        return parsed


def qs(url: str, params: dict) -> str:
    return url + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
