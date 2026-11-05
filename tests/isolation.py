"""Prove the parent baseline ledger is left untouched. Never write it."""

from __future__ import annotations

import hashlib
from pathlib import Path

PARENT_LEDGER = Path("/workspace/personal-finance/kalshi-paper/state/ledger.sqlite")


def fingerprint(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False, "sha256": None, "size": None}
    data = path.read_bytes()
    return {
        "exists": True,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def snapshot_parent_ledger() -> dict:
    return fingerprint(PARENT_LEDGER)


def assert_parent_ledger_untouched(testcase, before: dict) -> None:
    after = snapshot_parent_ledger()
    testcase.assertEqual(after["exists"], before["exists"])
    testcase.assertEqual(after["sha256"], before["sha256"])
    testcase.assertEqual(after["size"], before["size"])
    if after["exists"]:
        testcase.assertNotEqual(after["sha256"], "")
        # Tests must not use the parent file as their working ledger.
        testcase.assertTrue(PARENT_LEDGER.is_file())
