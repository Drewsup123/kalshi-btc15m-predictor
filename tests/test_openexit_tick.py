import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kxbtc15m.openexit.ledger import OpenExitLedger
from kxbtc15m.openexit.tick import run_tick


def _hist():
    markets = []
    for i in range(10):
        markets.append(
            {
                "ticker": f"OLD-{i}",
                "status": "finalized",
                "result": "yes" if i < 7 else "no",
                "close_time": f"2026-11-05T18:{i:02d}:00Z",
            }
        )
    return {"markets": markets}


def _open(ask="0.4000", bid="0.3900"):
    return {
        "markets": [
            {
                "ticker": "KXBTC15M-NOW",
                "status": "active",
                "result": "",
                "yes_ask_dollars": ask,
                "no_ask_dollars": "0.6200",
                "yes_bid_dollars": bid,
                "no_bid_dollars": "0.6000",
                "open_time": "2026-11-05T19:30:00Z",
                "close_time": "2026-11-05T19:45:00Z",
            }
        ]
    }


def _book(yes="0.3900", no="0.6000"):
    return {"orderbook_fp": {"yes_dollars": [["0.01", "5"], [yes, "30"]], "no_dollars": [["0.01", "5"], [no, "30"]]}}


class Fake:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_json(self, path, query=None):
        query = query or {}
        if path.endswith("/orderbook"):
            return self.mapping["book"]
        if path.startswith("/markets/trades"):
            return self.mapping.get("trades") or {"trades": []}
        if path == "/markets" and query.get("status") == "settled":
            return self.mapping["settled"]
        if path == "/markets":
            return self.mapping["open"]
        if path.startswith("/markets/"):
            if "one" in self.mapping:
                return self.mapping["one"]
            opens = (self.mapping.get("open") or {}).get("markets") or []
            return {"market": opens[0]} if opens else {"market": {}}
        raise AssertionError(path)


class TickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = OpenExitLedger(Path(self.tmp.name) / "openexit.sqlite")

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_enters_near_open_last10_yes(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        client = Fake({"settled": _hist(), "open": _open(), "book": _book()})
        out = run_tick(client, self.ledger, now)
        self.assertEqual(out["action"], "entry")
        self.assertEqual(out["side"], "yes")
        self.assertEqual(out["observed_at"], "2026-11-05T19:31:00Z")
        self.assertNotEqual(out["observed_at"], "2026-11-05T19:45:00Z")
        self.assertEqual(self.ledger.pending_count(), 1)
        self.assertLess(self.ledger.cash_cents(), 10000)

    def test_duplicate_tick_no_second_debit(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        client = Fake({"settled": _hist(), "open": _open(), "book": _book()})
        run_tick(client, self.ledger, now)
        cash = self.ledger.cash_cents()
        again = run_tick(client, self.ledger, now)
        self.assertEqual(again["action"], "hold")
        self.assertEqual(self.ledger.cash_cents(), cash)

    def test_missed_open_after_three_minutes(self):
        now = datetime(2026, 11, 5, 19, 34, 0, tzinfo=timezone.utc)
        out = run_tick(Fake({"settled": _hist(), "open": _open(), "book": _book()}), self.ledger, now)
        self.assertEqual(out["skip_reason"], "missed_open")
        self.assertEqual(self.ledger.pending_count(), 0)

    def test_official_result_uses_wrapped_market(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        client = Fake({"settled": _hist(), "open": _open(), "book": _book()})
        run_tick(client, self.ledger, now)
        later = datetime(2026, 11, 5, 19, 46, 0, tzinfo=timezone.utc)
        wrapped = {
            "market": {
                "ticker": "KXBTC15M-NOW",
                "status": "finalized",
                "result": "yes",
                "close_time": "2026-11-05T19:45:00Z",
            }
        }
        client.mapping["one"] = wrapped
        client.mapping["open"] = {"markets": []}
        out = run_tick(client, self.ledger, later)
        self.assertEqual(out["action"], "official_settlement")
        self.assertEqual(out["win_loss"], "win")
        self.assertEqual(self.ledger.pending_count(), 0)
        # leftover unused exit-fee reserve is returned; settlement is not a sale
        self.assertEqual(self.ledger.cash_cents(), 10116)
        self.assertEqual(self.ledger.realized_pnl_cents(), 116)

    def test_target_exit_on_observed_bid(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        client = Fake({"settled": _hist(), "open": _open(), "book": _book()})
        run_tick(client, self.ledger, now)
        later = datetime(2026, 11, 5, 19, 32, 10, tzinfo=timezone.utc)
        client.mapping["open"] = _open(ask="0.5000", bid="0.4900")
        client.mapping["book"] = _book(yes="0.4900", no="0.5000")
        out = run_tick(client, self.ledger, later)
        self.assertEqual(out["action"], "exit_target")
        self.assertNotEqual(out["exit"], "official_settlement")

    def test_ambiguous_tape_does_not_force_exit(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        client = Fake(
            {
                "settled": _hist(),
                "open": _open(),
                "book": _book(),
                "trades": {
                    "trades": [
                        {"taker_outcome_side": "no", "taker_side": "yes", "created_time": "2026-11-05T19:31:10Z"},
                        {"taker_outcome_side": "", "taker_side": "no", "created_time": "2026-11-05T19:31:11Z"},
                        {"taker_outcome_side": "no", "taker_side": "yes", "created_time": "2026-11-05T19:31:12Z"},
                        {"taker_outcome_side": "no", "taker_side": "yes", "created_time": "2026-11-05T19:31:13Z"},
                        {"taker_outcome_side": "no", "taker_side": "yes", "created_time": "2026-11-05T19:31:14Z"},
                    ]
                },
            }
        )
        run_tick(client, self.ledger, now)
        later = datetime(2026, 11, 5, 19, 31, 20, tzinfo=timezone.utc)
        out = run_tick(client, self.ledger, later)
        self.assertEqual(out["action"], "hold")
        self.assertEqual(self.ledger.pending_count(), 1)

    def test_known_opposite_prints_exit(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        client = Fake({"settled": _hist(), "open": _open(), "book": _book()})
        run_tick(client, self.ledger, now)
        client.mapping["trades"] = {
            "trades": [
                {"taker_outcome_side": "no", "taker_side": "no", "created_time": f"2026-11-05T19:31:{10+i:02d}Z"}
                for i in range(5)
            ]
        }
        later = datetime(2026, 11, 5, 19, 31, 20, tzinfo=timezone.utc)
        out = run_tick(client, self.ledger, later)
        self.assertEqual(out["action"], "exit_adverse_tape")

    def test_gap_does_not_invent_fill(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        client = Fake({"settled": _hist(), "open": _open(), "book": _book()})
        run_tick(client, self.ledger, now)
        later = datetime(2026, 11, 5, 19, 32, 30, tzinfo=timezone.utc)
        out = run_tick(client, self.ledger, later)
        self.assertEqual(out["action"], "hold")
        self.assertEqual(self.ledger.pending_count(), 1)
        events = list(self.ledger.conn.execute("SELECT kind FROM events"))
        self.assertIn("gap", [row["kind"] for row in events])

    def test_ignores_still_active_market_past_close(self):
        now = datetime(2026, 11, 5, 19, 45, 10, tzinfo=timezone.utc)
        stale = {
            "ticker": "KXBTC15M-OLD",
            "status": "active",
            "result": "",
            "yes_ask_dollars": "0.4000",
            "no_ask_dollars": "0.6200",
            "yes_bid_dollars": "0.3900",
            "no_bid_dollars": "0.6000",
            "open_time": "2026-11-05T19:30:00Z",
            "close_time": "2026-11-05T19:45:00Z",
        }
        fresh = {
            "ticker": "KXBTC15M-NEW",
            "status": "active",
            "result": "",
            "yes_ask_dollars": "0.4000",
            "no_ask_dollars": "0.6200",
            "yes_bid_dollars": "0.3900",
            "no_bid_dollars": "0.6000",
            "open_time": "2026-11-05T19:45:00Z",
            "close_time": "2026-11-05T20:00:00Z",
        }
        client = Fake(
            {
                "settled": {
                    "markets": _hist()["markets"]
                    + [
                        {
                            "ticker": "OLD-X",
                            "status": "finalized",
                            "result": "yes",
                            "close_time": "2026-11-05T19:30:00Z",
                        }
                    ]
                },
                "open": {"markets": [stale, fresh]},
                "book": _book(),
            }
        )
        out = run_tick(client, self.ledger, now)
        self.assertEqual(out["market_ticker"], "KXBTC15M-NEW")
        self.assertEqual(out["action"], "entry")

    def test_before_open_does_not_enter(self):
        now = datetime(2026, 11, 5, 19, 29, 50, tzinfo=timezone.utc)
        out = run_tick(Fake({"settled": _hist(), "open": _open(), "book": _book()}), self.ledger, now)
        self.assertEqual(out["skip_reason"], "market_not_open")
        self.assertEqual(self.ledger.pending_count(), 0)

    def test_trail_then_stop_precedence_uses_live_bid(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        client = Fake({"settled": _hist(), "open": _open(), "book": _book()})
        run_tick(client, self.ledger, now)
        armed = datetime(2026, 11, 5, 19, 31, 20, tzinfo=timezone.utc)
        client.mapping["open"] = _open(ask="0.4700", bid="0.4600")
        client.mapping["book"] = _book(yes="0.4600", no="0.5300")
        self.assertEqual(run_tick(client, self.ledger, armed)["action"], "hold")
        trail = datetime(2026, 11, 5, 19, 31, 40, tzinfo=timezone.utc)
        client.mapping["open"] = _open(ask="0.4400", bid="0.4200")
        client.mapping["book"] = _book(yes="0.4200", no="0.5700")
        self.assertEqual(run_tick(client, self.ledger, trail)["action"], "exit_trail")

    def test_book_stop_uses_observed_bid(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        client = Fake({"settled": _hist(), "open": _open(), "book": _book()})
        run_tick(client, self.ledger, now)
        later = datetime(2026, 11, 5, 19, 31, 20, tzinfo=timezone.utc)
        client.mapping["open"] = _open(ask="0.3200", bid="0.2900")
        client.mapping["book"] = _book(yes="0.2900", no="0.7000")
        self.assertEqual(run_tick(client, self.ledger, later)["action"], "exit_adverse_book")

    def test_quantity_follows_book_depth(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        thin = {"orderbook_fp": {"yes_dollars": [["0.01", "1"], ["0.3900", "1"]], "no_dollars": [["0.01", "1"], ["0.6000", "1"]]}}
        out = run_tick(Fake({"settled": _hist(), "open": _open(), "book": thin}), self.ledger, now)
        self.assertEqual(out["action"], "entry")
        self.assertEqual(out["contracts"], 1)

    def test_thin_book_skips_without_debit(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        empty = {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}
        cash = self.ledger.cash_cents()
        out = run_tick(Fake({"settled": _hist(), "open": _open(), "book": empty}), self.ledger, now)
        self.assertEqual(out["skip_reason"], "thin_book")
        self.assertEqual(self.ledger.cash_cents(), cash)

    def test_restart_keeps_pending(self):
        now = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
        run_tick(Fake({"settled": _hist(), "open": _open(), "book": _book()}), self.ledger, now)
        path = self.ledger.path
        cash = self.ledger.cash_cents()
        self.ledger.close()
        again = OpenExitLedger(path)
        self.assertEqual(again.cash_cents(), cash)
        self.assertEqual(again.pending_count(), 1)
        again.close()
        self.ledger = OpenExitLedger(path)


if __name__ == "__main__":
    unittest.main()
