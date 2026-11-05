"""Parent ledger fingerprint is read-only and environment-independent."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from kxbtc15m.ledger import Ledger
from tests.isolation import assert_parent_ledger_untouched, fingerprint, snapshot_parent_ledger


class IsolationTests(unittest.TestCase):
    def test_missing_and_present_fingerprints(self):
        with tempfile.TemporaryDirectory() as raw:
            missing = Path(raw) / "nope.sqlite"
            self.assertFalse(fingerprint(missing)["exists"])
            present = Path(raw) / "ledger.sqlite"
            Ledger(present).close()
            fp = fingerprint(present)
            self.assertTrue(fp["exists"])
            self.assertEqual(fp["size"], present.stat().st_size)
            self.assertEqual(len(fp["sha256"]), 64)
            again = fingerprint(present)
            self.assertEqual(again, fp)

    def test_parent_snapshot_does_not_create_or_write(self):
        before = snapshot_parent_ledger()
        again = snapshot_parent_ledger()
        self.assertEqual(again, before)
        assert_parent_ledger_untouched(self, before)

    def test_isolated_fixture_ledger_is_not_the_parent_path(self):
        before = snapshot_parent_ledger()
        with tempfile.TemporaryDirectory() as raw:
            fixture = Path(raw) / "ledger.sqlite"
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
            self.assertEqual(ledger.pending_count(), 1)
            ledger.close()
            self.assertNotEqual(fixture.resolve(), Path("/workspace/personal-finance/kalshi-paper/state/ledger.sqlite"))
            conn = sqlite3.connect(f"file:{fixture.resolve()}?mode=ro", uri=True)
            try:
                row = conn.execute("SELECT side, debit_cents FROM positions").fetchone()
                self.assertEqual(row[0], "no")
                self.assertEqual(row[1], 99)
            finally:
                conn.close()
        assert_parent_ledger_untouched(self, before)


if __name__ == "__main__":
    unittest.main()
