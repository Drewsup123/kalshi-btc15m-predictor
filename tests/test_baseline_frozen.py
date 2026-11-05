"""Strategy modules stay pinned. cycle.py hash is the parser-only v2.1 pin."""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "kxbtc15m"

FROZEN = {
    "cycle.py": "38c9074ce512f086440931074f382ae493e719d96f71d19f90883299b6359f20",
    "quotes.py": "376db685835695956e7ffc608ad79645a6836a3b532643772f100a2854faef4a",
    "signal.py": "7acf6d6ad1845a348fbbf4265a43b92ccf24ed62b839dd0f4dfc65ad761daa54",
    "risk.py": "43f059084d5f4f9a5fa3eadfb5400a1b2b4124ab5e4ba3c65a8bf80d91225746",
    "ledger.py": "86ae01c56dd041885343bcc3cca28b527924e6de8352d3c9f3984859a872a1db",
}


class BaselineFrozenTests(unittest.TestCase):
    def test_baseline_modules_unchanged(self):
        for name, expected in FROZEN.items():
            digest = hashlib.sha256((SRC / name).read_bytes()).hexdigest()
            self.assertEqual(digest, expected, f"{name} was modified")

    def test_model_version_unchanged_software_is_separate(self):
        from kxbtc15m import SOFTWARE_VERSION
        from kxbtc15m.signal import MODEL_VERSION

        self.assertEqual(MODEL_VERSION, "exp-baseline-v1@2026-11-05")
        self.assertEqual(SOFTWARE_VERSION, "2.1.0")
        self.assertNotEqual(SOFTWARE_VERSION, MODEL_VERSION)

    def test_refuses_parent_baseline_state_dir(self):
        from kxbtc15m.openexit.paths import assert_safe_openexit_dir

        with self.assertRaises(RuntimeError):
            assert_safe_openexit_dir("/workspace/personal-finance/kalshi-paper/state")


if __name__ == "__main__":
    unittest.main()
