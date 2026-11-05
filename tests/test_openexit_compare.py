import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from kxbtc15m.cli import main
from kxbtc15m.openexit.compare import build_compare
from tests.isolation import assert_parent_ledger_untouched, snapshot_parent_ledger


class CompareTests(unittest.TestCase):
    def test_report_reads_fixture_baseline_without_mutating_it(self):
        before = snapshot_parent_ledger()
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw) / "base"
            oe = Path(raw) / "oe"
            base.mkdir()
            from kxbtc15m.ledger import Ledger

            fixture = base / "ledger.sqlite"
            ledger = Ledger(fixture)
            ledger.open_position(
                cycle_id="2026-11-05T19:45:00Z",
                market_ticker="KXBTC15M-26NOV051445-45",
                side="no",
                contracts=15,
                cost_cents=92,
                fee_cents=7,
                debit_cents=99,
                ask_dollars="0.0613",
                model_version="exp-baseline-v1@2026-11-05",
                entry_class="experimental",
                opened_at="2026-11-05T19:39:00Z",
            )
            ledger.close()
            from tests.isolation import fingerprint

            snap = fingerprint(fixture)
            payload = build_compare(fixture, oe)
            self.assertTrue(payload["baseline"]["running"])
            self.assertEqual(payload["baseline"]["pending_count"], 1)
            self.assertEqual(payload["baseline"]["pending_tickers"], ["KXBTC15M-26NOV051445-45"])
            self.assertEqual(fingerprint(fixture), snap)
        assert_parent_ledger_untouched(self, before)

    def test_report_does_not_create_baseline_ledger(self):
        before = snapshot_parent_ledger()
        with tempfile.TemporaryDirectory() as raw:
            openexit = Path(raw) / "oe"
            baseline = Path(raw) / "missing-baseline"
            payload = build_compare(baseline / "ledger.sqlite", openexit)
            self.assertFalse((baseline / "ledger.sqlite").exists())
            self.assertEqual(payload["baseline"]["status"], "ledger_not_in_this_environment")
            self.assertEqual(payload["open_exit"]["status"], "not_running")
            self.assertNotEqual(payload["observed_at"], "2026-11-05T19:45:00Z")
            self.assertEqual(payload["loss_analysis"]["cause"], "unknown")
        assert_parent_ledger_untouched(self, before)

    def test_cli_report_isolated(self):
        before = snapshot_parent_ledger()
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
        assert_parent_ledger_untouched(self, before)


if __name__ == "__main__":
    unittest.main()
