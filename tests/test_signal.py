import unittest
from decimal import Decimal

from kxbtc15m.signal import LastPrint, choose_side


class SignalTests(unittest.TestCase):
    def test_momentum_up_is_yes(self):
        signal = choose_side(
            "KXBTC15M-26NOV051430-30",
            LastPrint(floor=Decimal("76000"), expiration=Decimal("76040")),
            seed=20261105,
            threshold_dollars=Decimal("20"),
        )
        self.assertEqual(signal.side, "yes")
        self.assertEqual(signal.rule, "momentum")
        self.assertEqual(signal.entry_class, "experimental")
        self.assertIsNone(signal.p_hat)
        self.assertEqual(signal.model_version, "exp-baseline-v1@2026-11-05")

    def test_momentum_down_is_no(self):
        signal = choose_side(
            "KXBTC15M-26NOV051430-30",
            LastPrint(floor=Decimal("76040"), expiration=Decimal("76000")),
            seed=20261105,
            threshold_dollars=Decimal("20"),
        )
        self.assertEqual(signal.side, "no")
        self.assertEqual(signal.rule, "momentum")

    def test_below_threshold_falls_back_to_seeded(self):
        signal = choose_side(
            "KXBTC15M-26NOV051430-30",
            LastPrint(floor=Decimal("76000"), expiration=Decimal("76005")),
            seed=20261105,
            threshold_dollars=Decimal("20"),
        )
        self.assertIn(signal.side, ("yes", "no"))
        self.assertEqual(signal.rule, "seeded_control")
        self.assertIsNone(signal.p_hat)

    def test_missing_print_falls_back_to_seeded(self):
        signal = choose_side("KXBTC15M-26NOV051430-30", None, seed=20261105)
        self.assertEqual(signal.rule, "seeded_control")
        self.assertIn(signal.side, ("yes", "no"))

    def test_seeded_is_deterministic(self):
        a = choose_side("KXBTC15M-26NOV051430-30", None, seed=20261105)
        b = choose_side("KXBTC15M-26NOV051430-30", None, seed=20261105)
        c = choose_side("KXBTC15M-26NOV051445-45", None, seed=20261105)
        self.assertEqual(a.side, b.side)
        self.assertEqual(a.inputs_hash, b.inputs_hash)
        self.assertNotEqual(a.inputs_hash, c.inputs_hash)

    def test_does_not_invent_calibrated_probability(self):
        signal = choose_side("KXBTC15M-26NOV051430-30", None, seed=1)
        self.assertIsNone(signal.p_hat)
        self.assertEqual(signal.entry_class, "experimental")
        self.assertNotEqual(signal.entry_class, "model_gated")


if __name__ == "__main__":
    unittest.main()
