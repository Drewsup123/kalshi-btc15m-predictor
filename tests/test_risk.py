import unittest
from decimal import Decimal

from kxbtc15m.risk import RiskConfig, size_and_gate


CFG = RiskConfig()


class RiskTests(unittest.TestCase):
    def test_inclusive_max_debit_allows_exactly_one_dollar(self):
        # ask 0.99 -> cost 99c, fee 1c, debit 100c
        decision = size_and_gate(
            ask=Decimal("0.99"),
            book_size=Decimal("10"),
            cash_cents=10000,
            used_downside_cents=0,
            pending_count=0,
            cfg=CFG,
        )
        self.assertTrue(decision.ok)
        self.assertEqual(decision.contracts, 1)
        self.assertEqual(decision.debit_cents, 100)
        self.assertLessEqual(decision.debit_cents, 100)

    def test_debit_over_one_dollar_skipped(self):
        # Force a price whose ceil(cost)+fee exceeds 100 for C=1.
        # ask 0.995 -> cost ceil 100c + fee 1c = 101c
        decision = size_and_gate(
            ask=Decimal("0.995"),
            book_size=Decimal("10"),
            cash_cents=10000,
            used_downside_cents=0,
            pending_count=0,
            cfg=CFG,
        )
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "per_pick_cap")

    def test_sizes_up_to_cap_not_always_one_contract(self):
        decision = size_and_gate(
            ask=Decimal("0.10"),
            book_size=Decimal("50"),
            cash_cents=10000,
            used_downside_cents=0,
            pending_count=0,
            cfg=CFG,
        )
        self.assertTrue(decision.ok)
        self.assertGreater(decision.contracts, 1)
        self.assertLessEqual(decision.debit_cents, 100)

    def test_thin_book_limits_or_skips(self):
        decision = size_and_gate(
            ask=Decimal("0.10"),
            book_size=Decimal("0"),
            cash_cents=10000,
            used_downside_cents=0,
            pending_count=0,
            cfg=CFG,
        )
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "thin_book")

    def test_daily_downside_counts_pending_and_ignores_gain_refill(self):
        # used 400 (e.g. prior realized loss 300 + pending 100). new 101 -> skip
        over = size_and_gate(
            ask=Decimal("0.995"),
            book_size=Decimal("10"),
            cash_cents=10000,
            used_downside_cents=400,
            pending_count=0,
            cfg=CFG,
        )
        self.assertEqual(over.skip_reason, "per_pick_cap")

        allowed = size_and_gate(
            ask=Decimal("0.99"),
            book_size=Decimal("10"),
            cash_cents=10000,
            used_downside_cents=400,
            pending_count=0,
            cfg=CFG,
        )
        self.assertTrue(allowed.ok)
        self.assertEqual(allowed.debit_cents, 100)

        blocked = size_and_gate(
            ask=Decimal("0.99"),
            book_size=Decimal("10"),
            cash_cents=10000,
            used_downside_cents=401,
            pending_count=0,
            cfg=CFG,
        )
        self.assertFalse(blocked.ok)
        self.assertEqual(blocked.skip_reason, "daily_downside_cap")

    def test_wins_do_not_mask_loss_budget(self):
        # used is realized losses only (caller must not subtract wins)
        decision = size_and_gate(
            ask=Decimal("0.99"),
            book_size=Decimal("10"),
            cash_cents=12000,
            used_downside_cents=500,
            pending_count=0,
            cfg=CFG,
        )
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "daily_downside_cap")

    def test_one_pending_blocks_new_entry(self):
        decision = size_and_gate(
            ask=Decimal("0.50"),
            book_size=Decimal("10"),
            cash_cents=10000,
            used_downside_cents=0,
            pending_count=1,
            cfg=CFG,
        )
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "pending_open")

    def test_no_martingale_same_ask_same_size_after_loss(self):
        first = size_and_gate(
            ask=Decimal("0.40"),
            book_size=Decimal("20"),
            cash_cents=10000,
            used_downside_cents=0,
            pending_count=0,
            cfg=CFG,
        )
        after_loss = size_and_gate(
            ask=Decimal("0.40"),
            book_size=Decimal("20"),
            cash_cents=10000 - first.debit_cents,
            used_downside_cents=first.debit_cents,
            pending_count=0,
            cfg=CFG,
        )
        self.assertTrue(first.ok and after_loss.ok)
        self.assertEqual(first.contracts, after_loss.contracts)

    def test_insufficient_cash_skips(self):
        decision = size_and_gate(
            ask=Decimal("0.50"),
            book_size=Decimal("10"),
            cash_cents=1,
            used_downside_cents=0,
            pending_count=0,
            cfg=CFG,
        )
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "insufficient_cash")


if __name__ == "__main__":
    unittest.main()
