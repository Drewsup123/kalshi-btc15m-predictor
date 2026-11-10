"""Refuse to write into old paper ledgers."""

from __future__ import annotations

from pathlib import Path


class V3Error(RuntimeError):
    pass


BLOCKED_FRAGMENTS = (
    "personal-finance/kalshi-paper",
    "kalshi-paper/state",
    "/var/openexit",
    "var/openexit",
)


def assert_safe_v3_dir(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    text = str(resolved)
    lowered = text.lower()
    if any(fragment in text or fragment in lowered for fragment in BLOCKED_FRAGMENTS):
        raise V3Error(f"refusing to use old simulator state dir: {resolved}")
    if resolved.name in {"state", "openexit"} and (resolved / "ledger.sqlite").exists():
        raise V3Error(f"refusing directory that looks like a paper ledger: {resolved}")
    if (resolved / "openexit.sqlite").exists() or (resolved / "ledger.sqlite").exists():
        raise V3Error(f"refusing directory that already holds a paper ledger: {resolved}")
    return resolved
