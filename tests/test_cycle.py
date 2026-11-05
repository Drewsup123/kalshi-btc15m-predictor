import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kxbtc15m.client import FeedError
from kxbtc15m.config import AppConfig
from kxbtc15m.cycle import run_cycle
from kxbtc15m.ledger import Ledger
from kxbtc15m.report import format_json, format_text

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 5, 19, 16, 0, tzinfo=timezone.utc)


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeClient:
    def __init__(self, mapping=None, error=None):
        self.mapping = mapping or {}
        self.error = error
        self.calls: list[str] = []

    def get_json(self, path: str, query=None):
        query = query or {}
        self.calls.append(path if not query else f"{path}?{query}")
        if self.error:
            raise self.error
        if path == "/markets":
            if query.get("status") == "settled":
                return self.mapping["settled"]
            return self.mapping["/markets"]
        if path in self.mapping:
            return self.mapping[path]
        if path.startswith("/markets/") and path.endswith("/orderbook"):
            return self.mapping.get("orderbook")
        if path.startswith("/markets/"):
            ticker = path.rsplit("/", 1)[-1]
            if ticker in self.mapping:
                return self.mapping[ticker]
            return {"ticker": ticker, "status": "active", "result": ""}
        raise FeedError(f"unexpected path {path}", status=404)


def _client(**over):
    mapping = {
        "/series/KXBTC15M": _load("series.json"),
        "/markets": _load("open_market.json"),
        "orderbook": _load("orderbook.json"),
        "settled": _load("settled_list.json"),
        "KXBTC15M-26NOV051415-15": _load("settled_yes.json"),
        "KXBTC15M-26NOV051400-00": _load("settled_no.json"),
    }
    mapping.update(over)
    return FakeClient(mapping)


def _cfg(state_dir: Path) -> AppConfig:
    return AppConfig(state_dir=state_dir)


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.intended_live = Path("/tmp/kxbtc15m-intended-live-ledger")
        self.assertFalse(str(self.state).startswith(str(self.intended_live)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_failed_feed_skips_without_debit(self):
        ledger = Ledger(self.state / "ledger.sqlite")
        client = FakeClient(error=FeedError("403 unknown", status=403))
        report = run_cycle(_cfg(self.state), client, ledger, NOW)
        self.assertEqual(report.skip_reason, "failed_feed")
        self.assertEqual(ledger.cash_cents(), 10000)
        self.assertEqual(ledger.pending_count(), 0)

    def test_cycle_makes_experimental_entry(self):
        ledger = Ledger(self.state / "ledger.sqlite")
        report = run_cycle(_cfg(self.state), _client(), ledger, NOW)
        self.assertEqual(report.action, "entry")
        self.assertEqual(report.entry_class, "experimental")
        self.assertIsNone(report.p_hat)
        self.assertEqual(ledger.pending_count(), 1)
        self.assertLess(ledger.cash_cents(), 10000)
        self.assertEqual(ledger.realized_pnl_cents(), 0)
        pred = ledger.prediction("KXBTC15M-26NOV051430-30")
        self.assertLessEqual(pred["predicted_at"], pred["close_time"])
        self.assertEqual(pred["predicted_at"], "2026-11-05T19:16:00Z")

    def test_duplicate_cycle_does_not_debit_again(self):
        ledger = Ledger(self.state / "ledger.sqlite")
        first = run_cycle(_cfg(self.state), _client(), ledger, NOW)
        cash = ledger.cash_cents()
        second = run_cycle(_cfg(self.state), _client(), ledger, NOW)
        self.assertEqual(first.action, "entry")
        self.assertEqual(second.action, "already_done")
        self.assertEqual(ledger.cash_cents(), cash)
        self.assertEqual(ledger.pending_count(), 1)

    def test_settles_official_result_then_can_enter_next(self):
        ledger = Ledger(self.state / "ledger.sqlite")
        ledger.open_position(
            cycle_id="2026-11-05T19:15:00Z",
            market_ticker="KXBTC15M-26NOV051415-15",
            side="yes",
            contracts=1,
            cost_cents=67,
            fee_cents=2,
            debit_cents=69,
            ask_dollars="0.6700",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T19:01:00Z",
        )
        report = run_cycle(_cfg(self.state), _client(), ledger, NOW)
        self.assertEqual(ledger.wins(), 1)
        self.assertEqual(ledger.realized_pnl_cents(), 31)
        self.assertEqual(report.action, "entry")
        self.assertEqual(ledger.pending_count(), 1)
        self.assertNotEqual(ledger.pending_rows()[0]["market_ticker"], "KXBTC15M-26NOV051415-15")

    def test_missing_result_keeps_pending_and_blocks_new_entry(self):
        ledger = Ledger(self.state / "ledger.sqlite")
        ledger.open_position(
            cycle_id="2026-11-05T19:15:00Z",
            market_ticker="KXBTC15M-26NOV051415-15",
            side="yes",
            contracts=1,
            cost_cents=67,
            fee_cents=2,
            debit_cents=69,
            ask_dollars="0.6700",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T19:01:00Z",
        )
        unsettled = _load("settled_yes.json")
        unsettled = {**unsettled, "result": "", "status": "active"}
        client = _client(**{"KXBTC15M-26NOV051415-15": unsettled})
        report = run_cycle(_cfg(self.state), client, ledger, NOW)
        self.assertEqual(ledger.pending_count(), 1)
        self.assertEqual(ledger.realized_pnl_cents(), 0)
        self.assertEqual(report.action, "skip")
        self.assertEqual(report.skip_reason, "pending_open")

    def test_report_separates_cash_pending_and_realized(self):
        ledger = Ledger(self.state / "ledger.sqlite")
        report = run_cycle(_cfg(self.state), _client(), ledger, NOW)
        self.assertEqual(report.realized_pnl_cents, 0)
        self.assertGreater(report.pending_exposure_cents, 0)
        self.assertEqual(report.equity_cents, 10000)
        text = format_text(report)
        payload = format_json(report)
        self.assertIn("simulated", text.lower())
        self.assertIn("slippage", text.lower())
        self.assertIn("pending_exposure_cents", payload)
        self.assertNotIn("75%", text)

    def test_no_lookahead_prediction_before_close(self):
        ledger = Ledger(self.state / "ledger.sqlite")
        run_cycle(_cfg(self.state), _client(), ledger, NOW)
        pred = ledger.prediction("KXBTC15M-26NOV051430-30")
        self.assertLessEqual(pred["predicted_at"], pred["close_time"])

    def test_malformed_series_skips(self):
        ledger = Ledger(self.state / "ledger.sqlite")
        client = _client(**{"/series/KXBTC15M": {"series": {"fee_type": "flat", "fee_multiplier": 1}}})
        report = run_cycle(_cfg(self.state), client, ledger, NOW)
        self.assertEqual(report.skip_reason, "unsupported_fee_type")
        self.assertEqual(ledger.pending_count(), 0)


if __name__ == "__main__":
    unittest.main()
