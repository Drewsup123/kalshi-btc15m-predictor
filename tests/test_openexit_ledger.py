import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from kxbtc15m.openexit.ledger import OpenExitLedger
from kxbtc15m.openexit.risk import OpenExitRisk, size_entry


class LedgerMoneyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = OpenExitLedger(Path(self.tmp.name) / "openexit.sqlite")

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_reserved_exit_fee_returned_on_official_settle(self):
        sized = size_entry(Decimal("0.40"), Decimal("2"), 10000, 0, 0, OpenExitRisk())
        opened = self.ledger.open_position(
            market_ticker="T",
            cycle_id="2026-11-05T19:45:00Z",
            side="yes",
            contracts=sized.contracts,
            entry_ask=sized.ask,
            cost_cents=sized.cost_cents,
            entry_fee_cents=sized.entry_fee_cents,
            exit_fee_reserve_cents=sized.exit_fee_reserve_cents,
            reserve_cents=sized.reserve_cents,
            opened_at="2026-11-05T19:31:00Z",
        )
        self.assertTrue(opened.ok)
        cash_after_open = self.ledger.cash_cents()
        self.assertEqual(cash_after_open, 10000 - sized.reserve_cents)
        settled = self.ledger.official_settle("T", "yes", "2026-11-05T19:46:00Z")
        self.assertTrue(settled.ok)
        leftover = sized.reserve_cents - sized.cost_cents - sized.entry_fee_cents
        self.assertEqual(self.ledger.cash_cents(), cash_after_open + leftover + 100 * sized.contracts)

    def test_daily_downside_counts_pending_and_losses(self):
        sized = size_entry(Decimal("0.40"), Decimal("2"), 10000, 0, 0, OpenExitRisk())
        self.ledger.open_position(
            market_ticker="T1",
            cycle_id="2026-11-05T19:45:00Z",
            side="yes",
            contracts=sized.contracts,
            entry_ask=sized.ask,
            cost_cents=sized.cost_cents,
            entry_fee_cents=sized.entry_fee_cents,
            exit_fee_reserve_cents=sized.exit_fee_reserve_cents,
            reserve_cents=sized.reserve_cents,
            opened_at="2026-11-05T19:31:00Z",
        )
        day = "2026-11-05"
        used = self.ledger.used_downside_cents(day)
        self.assertEqual(used, sized.reserve_cents)
        self.ledger.official_settle("T1", "no", "2026-11-05T19:46:00Z")
        used_after = self.ledger.used_downside_cents(day)
        self.assertGreater(used_after, 0)
        blocked = size_entry(Decimal("0.40"), Decimal("2"), self.ledger.cash_cents(), used_after, 0, OpenExitRisk())
        if used_after >= 500:
            self.assertEqual(blocked.skip_reason, "daily_downside_cap")

    def test_idempotent_settle(self):
        sized = size_entry(Decimal("0.40"), Decimal("1"), 10000, 0, 0, OpenExitRisk())
        self.ledger.open_position(
            market_ticker="T",
            cycle_id="c",
            side="no",
            contracts=sized.contracts,
            entry_ask=sized.ask,
            cost_cents=sized.cost_cents,
            entry_fee_cents=sized.entry_fee_cents,
            exit_fee_reserve_cents=sized.exit_fee_reserve_cents,
            reserve_cents=sized.reserve_cents,
            opened_at="2026-11-05T19:31:00Z",
        )
        first = self.ledger.official_settle("T", "no", "2026-11-05T19:46:00Z")
        cash = self.ledger.cash_cents()
        second = self.ledger.official_settle("T", "no", "2026-11-05T19:46:01Z")
        self.assertTrue(first.ok)
        self.assertFalse(second.ok)
        self.assertEqual(self.ledger.cash_cents(), cash)


if __name__ == "__main__":
    unittest.main()
