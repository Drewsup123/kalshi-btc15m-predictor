import unittest
from decimal import Decimal

from kxbtc15m.openexit.exits import ExitConfig, choose_exit


CFG = ExitConfig()


class ExitTests(unittest.TestCase):
    def test_target_beats_other_rules(self):
        d = choose_exit("yes", Decimal("0.40"), Decimal("0.49"), Decimal("0.49"), 5, CFG)
        self.assertEqual(d.reason, "exit_target")

    def test_trail_after_five_cents(self):
        d = choose_exit("yes", Decimal("0.40"), Decimal("0.42"), Decimal("0.46"), 0, CFG)
        self.assertEqual(d.reason, "exit_trail")

    def test_no_trail_before_arm(self):
        d = choose_exit("yes", Decimal("0.40"), Decimal("0.41"), Decimal("0.41"), 0, CFG)
        self.assertEqual(d.reason, "hold")

    def test_adverse_tape_only_known_prints(self):
        d = choose_exit("yes", Decimal("0.40"), Decimal("0.40"), Decimal("0.40"), 5, CFG)
        self.assertEqual(d.reason, "exit_adverse_tape")
        d2 = choose_exit("yes", Decimal("0.40"), Decimal("0.40"), Decimal("0.40"), 4, CFG)
        self.assertEqual(d2.reason, "hold")

    def test_adverse_book_stop(self):
        d = choose_exit("yes", Decimal("0.40"), Decimal("0.29"), Decimal("0.40"), 0, CFG)
        self.assertEqual(d.reason, "exit_adverse_book")

    def test_does_not_invent_fill_across_gap(self):
        # caller must not pass a reconstructed mid-gap bid
        d = choose_exit("yes", Decimal("0.40"), Decimal("0.41"), Decimal("0.41"), 0, CFG)
        self.assertEqual(d.reason, "hold")


if __name__ == "__main__":
    unittest.main()
