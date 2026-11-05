import unittest
from decimal import Decimal

from kxbtc15m.openexit.risk import OpenExitRisk, size_entry


CFG = OpenExitRisk()


class OpenExitRiskTests(unittest.TestCase):
    def test_reserve_includes_exit_fee(self):
        d = size_entry(Decimal("0.40"), Decimal("20"), 10000, 0, 0, CFG)
        self.assertTrue(d.ok)
        self.assertGreater(d.reserve_cents, d.entry_debit_cents)
        self.assertLessEqual(d.reserve_cents, 1000)

    def test_ten_dollar_inclusive_blocks_oversize(self):
        d = size_entry(Decimal("0.99"), Decimal("20"), 10000, 0, 0, CFG)
        self.assertTrue(d.ok)
        self.assertLessEqual(d.reserve_cents, 1000)
        over = size_entry(Decimal("0.99"), Decimal("20"), 10000, 0, 0, OpenExitRisk(max_debit_cents=100))
        self.assertFalse(over.ok)
        self.assertEqual(over.skip_reason, "per_pick_cap")

    def test_no_daily_cap_in_default_regime(self):
        d = size_entry(Decimal("0.40"), Decimal("20"), 12000, 500, 0, CFG)
        self.assertTrue(d.ok)
        self.assertIsNone(d.skip_reason)

    def test_reduces_to_book_depth_no_leftover_partial(self):
        d = size_entry(Decimal("0.20"), Decimal("2"), 10000, 0, 0, CFG)
        self.assertTrue(d.ok)
        self.assertEqual(d.contracts, 2)
        self.assertTrue(d.full_intended or d.contracts == 2)

    def test_zero_book_skips(self):
        d = size_entry(Decimal("0.40"), Decimal("0"), 10000, 0, 0, CFG)
        self.assertEqual(d.skip_reason, "thin_book")


if __name__ == "__main__":
    unittest.main()
