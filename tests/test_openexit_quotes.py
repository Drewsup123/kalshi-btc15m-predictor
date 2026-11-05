import unittest
from datetime import datetime, timezone
from decimal import Decimal

from kxbtc15m.openexit.quotes import LiveQuoteConfig, live_quotes


NOW = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
SNAP = NOW


def _market(**over):
    base = {
        "ticker": "KXBTC15M-X",
        "status": "active",
        "yes_ask_dollars": "0.4000",
        "no_ask_dollars": "0.6200",
        "yes_bid_dollars": "0.3800",
        "no_bid_dollars": "0.6000",
        "close_time": "2026-11-05T19:45:00Z",
        "open_time": "2026-11-05T19:30:00Z",
    }
    base.update(over)
    return base


def _book(yes_best="0.3800", no_best="0.5900", yes_sz="20", no_sz="20"):
    return {
        "orderbook_fp": {
            "yes_dollars": [["0.0100", "5"], [yes_best, yes_sz]],
            "no_dollars": [["0.0100", "5"], [no_best, no_sz]],
        }
    }


class LiveQuoteTests(unittest.TestCase):
    def test_uses_conservative_ask_without_skipping_small_disagreement(self):
        # market yes ask 0.40 vs implied 1-0.59=0.41 → disagree 1c, still ok
        q = live_quotes(_market(), _book(), NOW, SNAP, LiveQuoteConfig())
        self.assertTrue(q.ok)
        self.assertEqual(q.yes_ask, Decimal("0.4100"))
        self.assertEqual(q.yes_bid, Decimal("0.3800"))

    def test_large_disagreement_still_uses_conservative_not_systematic_skip(self):
        q = live_quotes(_market(yes_ask_dollars="0.4000"), _book(no_best="0.5000"), NOW, SNAP, LiveQuoteConfig())
        self.assertTrue(q.ok)
        self.assertEqual(q.yes_ask, Decimal("0.5000"))

    def test_book_only_when_market_ask_invalid(self):
        q = live_quotes(_market(yes_ask_dollars="1.0000"), _book(), NOW, SNAP, LiveQuoteConfig())
        self.assertTrue(q.ok)
        self.assertEqual(q.yes_ask, Decimal("0.4100"))

    def test_thin_book_skips(self):
        empty = {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}
        q = live_quotes(_market(), empty, NOW, SNAP, LiveQuoteConfig())
        self.assertFalse(q.ok)
        self.assertEqual(q.skip_reason, "thin_book")

    def test_stale_and_near_close(self):
        late = datetime(2026, 11, 5, 19, 44, 30, tzinfo=timezone.utc)
        q = live_quotes(_market(), _book(), late, late, LiveQuoteConfig())
        self.assertEqual(q.skip_reason, "near_close")


if __name__ == "__main__":
    unittest.main()
