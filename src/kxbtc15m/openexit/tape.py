"""Public prints. Ambiguous aggressor is stored but never counted."""

from __future__ import annotations


def known_aggressor(print_row: dict) -> str | None:
    outcome = str(print_row.get("taker_outcome_side") or "").strip().lower()
    side = str(print_row.get("taker_side") or "").strip().lower()
    if outcome not in {"yes", "no"}:
        return None
    if side and side not in {"yes", "no"}:
        return None
    if side and side != outcome:
        return None
    return outcome


def count_opposite(prints: list[dict], our_side: str) -> int:
    return sum(1 for row in prints if known_aggressor(row) not in (None, our_side))
