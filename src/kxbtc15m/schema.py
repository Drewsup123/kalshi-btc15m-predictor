"""Unwrap official Kalshi public GET envelopes."""

from __future__ import annotations


def unwrap_market(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("market"), dict):
        return payload["market"]
    if payload.get("ticker"):
        return payload
    markets = payload.get("markets")
    if isinstance(markets, list) and markets and isinstance(markets[0], dict):
        return markets[0]
    return None


def unwrap_markets(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("markets"), list):
        return [row for row in payload["markets"] if isinstance(row, dict)]
    inner = unwrap_market(payload)
    return [inner] if inner else []
