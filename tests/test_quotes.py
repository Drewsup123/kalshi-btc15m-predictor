import unittest
from datetime import datetime, timezone
from decimal import Decimal

from kxbtc15m.clock import bucket_id, denver_day
from kxbtc15m.quotes import QuoteConfig, evaluate_quote


def _market(**over):
    base = {
        "ticker": "KXBTC15M-26NOV051430-30",
        "status": "active",
        "yes_ask_dollars": "0.6700",
        "no_ask_dollars": "0.3400",
        "yes_bid_dollars": "0.6600",
        "no_bid_dollars": "0.3300",
        "close_time": "2026-11-05T19:30:00Z",
        "open_time": "2026-11-05T19:15:00Z",
    }
    base.update(over)
    return base


def _book(yes_best="0.6600", no_best="0.3300", yes_sz="100.00", no_sz="100.00"):
    return {
        "orderbook_fp": {
            "yes_dollars": [["0.0100", "10.00"], [yes_best, yes_sz]],
            "no_dollars": [["0.0100", "10.00"], [no_best, no_sz]],
        }
    }


NOW = datetime(2026, 11, 5, 19, 16, 0, tzinfo=timezone.utc)
SNAP = datetime(2026, 11, 5, 19, 16, 0, tzinfo=timezone.utc)
CFG = QuoteConfig()


class ClockTests(unittest.TestCase):
    def test_bucket_from_close_time(self):
        self.assertEqual(bucket_id("2026-11-05T19:30:00Z"), "2026-11-05T19:30:00Z")

    def test_denver_day_after_utc_midnight(self):
        # 02:00 UTC on Nov 6 is still Nov 5 in America/Denver (UTC-7 MST)
        day = denver_day(datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc))
        self.assertEqual(str(day), "2026-11-05")


class QuoteTests(unittest.TestCase):
    def test_executable_ask_from_market_and_book(self):
        decision = evaluate_quote(_market(), _book(), NOW, SNAP, CFG)
        self.assertTrue(decision.ok)
        self.assertIsNone(decision.skip_reason)
        self.assertEqual(decision.yes_ask, Decimal("0.6700"))
        self.assertEqual(decision.no_ask, Decimal("0.3400"))
        self.assertEqual(decision.yes_size, Decimal("100.00"))
        self.assertEqual(decision.no_size, Decimal("100.00"))

    def test_conservative_ask_uses_worse_of_market_and_book(self):
        market = _market(yes_ask_dollars="0.6600")
        decision = evaluate_quote(market, _book(no_best="0.3300"), NOW, SNAP, CFG)
        self.assertTrue(decision.ok)
        self.assertEqual(decision.yes_ask, Decimal("0.6700"))

    def test_inconsistent_book_skips(self):
        decision = evaluate_quote(_market(), _book(no_best="0.2800"), NOW, SNAP, CFG)
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "inconsistent_book")

    def test_invalid_ask_skips(self):
        decision = evaluate_quote(_market(yes_ask_dollars="1.0000"), _book(), NOW, SNAP, CFG)
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "invalid_ask")

    def test_empty_book_skips(self):
        empty = {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}
        decision = evaluate_quote(_market(), empty, NOW, SNAP, CFG)
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "thin_book")

    def test_stale_quote_skips(self):
        snap = datetime(2026, 11, 5, 19, 15, 29, tzinfo=timezone.utc)
        decision = evaluate_quote(_market(), _book(), NOW, snap, CFG)
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "stale_quote")

    def test_near_close_skips(self):
        now = datetime(2026, 11, 5, 19, 29, 31, tzinfo=timezone.utc)
        snap = now
        decision = evaluate_quote(_market(), _book(), now, snap, CFG)
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "near_close")

    def test_closed_market_skips(self):
        decision = evaluate_quote(_market(status="finalized"), _book(), NOW, SNAP, CFG)
        self.assertFalse(decision.ok)
        self.assertEqual(decision.skip_reason, "market_not_open")


if __name__ == "__main__":
    unittest.main()
