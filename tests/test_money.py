import unittest

from kxbtc15m.money import cents_to_dollars, dollars_to_cents_ceil


class MoneyTests(unittest.TestCase):
    def test_ceil_fractional_cent(self):
        self.assertEqual(dollars_to_cents_ceil("0.671"), 68)
        self.assertEqual(dollars_to_cents_ceil(0.01), 1)
        self.assertEqual(dollars_to_cents_ceil(1), 100)

    def test_exact_cents_unchanged(self):
        self.assertEqual(dollars_to_cents_ceil("0.67"), 67)
        self.assertEqual(dollars_to_cents_ceil("1.00"), 100)

    def test_cents_format(self):
        self.assertEqual(cents_to_dollars(10000), "100.00")
        self.assertEqual(cents_to_dollars(1), "0.01")
        self.assertEqual(cents_to_dollars(0), "0.00")


if __name__ == "__main__":
    unittest.main()
