"""Freeze scalers and λ before the one holdout pass."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from kxbtc15m.v3 import MODEL_VERSION, FEATURE_SPEC, REPLAY_ASSUMPTION


def lock_payload(l2_logistic: float, l2_ridge: float, extra: dict | None = None) -> dict:
    body = {
        "model_version": MODEL_VERSION,
        "feature_spec": FEATURE_SPEC,
        "replay_assumption": REPLAY_ASSUMPTION,
        "l2_logistic": l2_logistic,
        "l2_ridge": l2_ridge,
        "holdout_unlocked": False,
        "locked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if extra:
        body.update(extra)
    return body


def write_lock(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError("lock file already exists; refusing to retune")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_lock(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
