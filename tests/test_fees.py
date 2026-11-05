import unittest
from decimal import Decimal
from pathlib import Path

from kxbtc15m.fees import (
    FEE_CONSTANT,
    OFFICIAL_EXCERPT_PATH,
    assert_fee_source_ok,
    load_official_excerpt,
    taker_fee_cents,
)


class FeeTests(unittest.TestCase):
    def test_fee_constant_is_official(self):
        self.assertEqual(FEE_CONSTANT, Decimal("0.07"))

    def test_mid_price_one_contract_rounds_up(self):
        # 0.07 * 1 * 0.5 * 0.5 = 0.0175 -> 2 cents
        self.assertEqual(taker_fee_cents(1, Decimal("0.50")), 2)

    def test_low_price_rounds_up_to_one_cent(self):
        # 0.07 * 0.10 * 0.90 = 0.0063 -> 1 cent
        self.assertEqual(taker_fee_cents(1, Decimal("0.10")), 1)

    def test_exact_cent_does_not_round_again(self):
        # 0.07 * 1 * 1 * 0.5 * 0.5 with a constructed total of 0.02
        # 0.07 * 10 * 0.50 * 0.50 = 0.175 -> 18 cents
        self.assertEqual(taker_fee_cents(10, Decimal("0.50")), 18)

    def test_order_total_not_per_contract_then_sum(self):
        # 0.07 * 2 * 0.10 * 0.90 = 0.0126 -> 2 cents (not 1+1 after per-contract ceil)
        self.assertEqual(taker_fee_cents(2, Decimal("0.10")), 2)

    def test_high_price_tiny_fee_rounds_up(self):
        # 0.07 * 1 * 0.99 * 0.01 = 0.000693 -> 1 cent
        self.assertEqual(taker_fee_cents(1, Decimal("0.99")), 1)

    def test_multiplier_scales(self):
        # 2 * 0.0175 = 0.035 -> 4 cents
        self.assertEqual(taker_fee_cents(1, Decimal("0.50"), multiplier=Decimal("2")), 4)

    def test_zero_contracts_rejected(self):
        with self.assertRaises(ValueError):
            taker_fee_cents(0, Decimal("0.50"))

    def test_missing_excerpt_fails_closed(self):
        with self.assertRaises(ValueError) as ctx:
            assert_fee_source_ok("unrelated text")
        self.assertIn("fee", str(ctx.exception).lower())

    def test_repo_excerpt_is_accepted(self):
        text = load_official_excerpt(OFFICIAL_EXCERPT_PATH)
        assert_fee_source_ok(text)
        self.assertTrue(Path(OFFICIAL_EXCERPT_PATH).is_file())


if __name__ == "__main__":
    unittest.main()
