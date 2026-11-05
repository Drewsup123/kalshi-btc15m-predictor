import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from kxbtc15m.cli import main
from kxbtc15m.openexit.compare import build_compare


class CompareTests(unittest.TestCase):
    def test_report_does_not_create_baseline_ledger(self):
        with tempfile.TemporaryDirectory() as raw:
            openexit = Path(raw) / "oe"
            baseline = Path(raw) / "missing-baseline"
            payload = build_compare(baseline / "ledger.sqlite", openexit)
            self.assertFalse((baseline / "ledger.sqlite").exists())
            self.assertEqual(payload["baseline"]["status"], "ledger_not_in_this_environment")
            self.assertEqual(payload["open_exit"]["status"], "not_running")
            self.assertNotEqual(payload["observed_at"], "2026-11-05T19:45:00Z")
            self.assertEqual(payload["loss_analysis"]["cause"], "unknown")

    def test_cli_report_isolated(self):
        with tempfile.TemporaryDirectory() as raw:
            oe = Path(raw) / "oe"
            base = Path(raw) / "base"
            now = datetime(2026, 11, 5, 19, 40, 0, tzinfo=timezone.utc)
            with patch("kxbtc15m.openexit.compare.utc_now", return_value=now):
                rc = main(
                    [
                        "report",
                        "--state-dir",
                        str(oe),
                        "--baseline-state-dir",
                        str(base),
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertFalse((base / "ledger.sqlite").exists())
            self.assertFalse(Path("/workspace/personal-finance/kalshi-paper/state/ledger.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
