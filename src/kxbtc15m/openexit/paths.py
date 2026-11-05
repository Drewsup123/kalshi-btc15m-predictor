"""Refuse to write into the original baseline state directory."""

from __future__ import annotations

from pathlib import Path

BLOCKED_FRAGMENTS = (
    "personal-finance/kalshi-paper",
    "kalshi-paper/state",
)


def assert_safe_openexit_dir(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    text = str(resolved)
    if any(fragment in text for fragment in BLOCKED_FRAGMENTS):
        raise RuntimeError(f"refusing to use baseline state dir: {resolved}")
    if resolved.name == "state" and (resolved / "ledger.sqlite").exists() and "openexit" not in text:
        raise RuntimeError(f"refusing directory that already holds a baseline ledger: {resolved}")
    return resolved
