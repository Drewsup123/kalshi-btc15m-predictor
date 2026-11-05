import unittest
from datetime import datetime, timezone

from kxbtc15m.openexit.lean import choose_lean
from kxbtc15m.openexit.tape import count_opposite, known_aggressor


OPEN = datetime(2026, 11, 5, 19, 30, tzinfo=timezone.utc)


def _m(ticker, result, close):
    return {"ticker": ticker, "result": result, "status": "finalized", "close_time": close}


class LeanTests(unittest.TestCase):
    def test_majority_yes(self):
        hist = [_m(f"T{i}", "yes" if i < 7 else "no", f"2026-11-05T19:{10+i:02d}:00Z") for i in range(10)]
        # close times must be before open — use earlier hours
        hist = [_m(f"T{i}", "yes" if i < 7 else "no", f"2026-11-05T18:{i:02d}:00Z") for i in range(10)]
        s = choose_lean(hist, OPEN)
        self.assertEqual(s.side, "yes")
        self.assertEqual(s.yes_count, 7)
        self.assertEqual(s.no_count, 3)

    def test_tie_and_short_history(self):
        hist = [_m(f"T{i}", "yes" if i % 2 == 0 else "no", f"2026-11-05T18:{i:02d}:00Z") for i in range(10)]
        self.assertEqual(choose_lean(hist, OPEN).skip_reason, "lean_tie")
        self.assertEqual(choose_lean(hist[:9], OPEN).skip_reason, "insufficient_history")

    def test_ignores_later_windows_no_lookahead(self):
        hist = [_m(f"T{i}", "no", f"2026-11-05T18:{i:02d}:00Z") for i in range(10)]
        hist.append(_m("FUTURE", "yes", "2026-11-05T19:45:00Z"))
        s = choose_lean(hist, OPEN)
        self.assertEqual(s.side, "no")
        self.assertEqual(s.used, 10)

    def test_drops_empty_result(self):
        hist = [_m(f"T{i}", "yes", f"2026-11-05T18:{i:02d}:00Z") for i in range(9)]
        hist.append(_m("VOID", "", "2026-11-05T18:20:00Z"))
        self.assertEqual(choose_lean(hist, OPEN).skip_reason, "insufficient_history")


class TapeTests(unittest.TestCase):
    def test_ignores_ambiguous_aggressor(self):
        prints = [
            {"taker_outcome_side": "yes", "taker_side": "yes"},
            {"taker_outcome_side": "no", "taker_side": "yes"},  # disagree
            {"taker_outcome_side": "", "taker_side": "no"},
            {"taker_outcome_side": "no", "taker_side": "no"},
        ]
        self.assertEqual(known_aggressor(prints[0]), "yes")
        self.assertIsNone(known_aggressor(prints[1]))
        self.assertIsNone(known_aggressor(prints[2]))
        self.assertEqual(count_opposite(prints, "yes"), 1)


if __name__ == "__main__":
    unittest.main()
