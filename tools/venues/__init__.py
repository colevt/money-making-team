"""Venue adapters. Trader posts through tools/execute.py. Keys stay in .env."""
from __future__ import annotations

from . import kalshi, oneinch, polymarket

HANDLERS = {
    "kalshi": kalshi,
    "polymarket_us": polymarket,
    "onchain": oneinch,
}


def handler(venue: str):
    if venue not in HANDLERS:
        raise ValueError(f"unknown venue {venue}")
    return HANDLERS[venue]
