"""Regression: official GET /markets/{ticker} wraps result under market."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kxbtc15m.clock import iso_utc
from kxbtc15m.cycle import run_cycle
from kxbtc15m.ledger import Ledger
from kxbtc15m.report import format_json
from kxbtc15m.schema import unwrap_market
from kxbtc15m.signal import MODEL_VERSION
from tests.test_cycle import NOW, _cfg, _client

PARENT = Path("/workspace/personal-finance/kalshi-paper/state/ledger.sqlite")
TICKER = "KXBTC15M-26NOV051445-45"

# Exact official envelope observed 2026-11-05 on elections host (fields required for settle).
OFFICIAL_NESTED_YES = {
    "market": {
        "ticker": TICKER,
        "event_ticker": "KXBTC15M-26NOV051445",
        "status": "finalized",
        "result": "yes",
        "yes_sub_title": "Yes",
        "no_sub_title": "No",
        "close_time": "2026-11-05T19:45:00Z",
        "settlement_ts": "2026-11-05T19:45:02.127035Z",
        "settlement_value_dollars": "1.0000",
        "expiration_value": "76263.33",
    }
}


class SettleUnwrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.ledger = None
        self.assertFalse(PARENT.exists())

    def tearDown(self):
        if self.ledger is not None:
            self.ledger.close()
        self.tmp.cleanup()
        self.assertFalse(PARENT.exists())

    def _pending_no_99(self) -> Ledger:
        ledger = Ledger(self.state / "ledger.sqlite")
        ledger.open_position(
            cycle_id="2026-11-05T19:45:00Z",
            market_ticker=TICKER,
            side="no",
            contracts=15,
            cost_cents=92,
            fee_cents=7,
            debit_cents=99,
            ask_dollars="0.0613",
            model_version=MODEL_VERSION,
            entry_class="experimental",
            opened_at="2026-11-05T19:39:00Z",
        )
        self.ledger = ledger
        return ledger

    def test_nested_official_yes_closes_pending_no_as_99c_loss(self):
        ledger = self._pending_no_99()
        self.assertEqual(ledger.cash_cents(), 10000 - 99)
        self.assertEqual(ledger.pending_count(), 1)
        # Top-level result is absent — this is the official envelope.
        self.assertNotIn("result", OFFICIAL_NESTED_YES)
        self.assertEqual(OFFICIAL_NESTED_YES["market"]["result"], "yes")
        self.assertEqual(OFFICIAL_NESTED_YES["market"]["status"], "finalized")
        inner = unwrap_market(OFFICIAL_NESTED_YES)
        self.assertEqual(inner["result"], "yes")

        later = datetime(2026, 11, 5, 20, 35, 0, tzinfo=timezone.utc)
        client = _client(**{TICKER: OFFICIAL_NESTED_YES})
        report = run_cycle(_cfg(self.state), client, ledger, later)
        self.assertEqual(ledger.pending_count(), 0)
        self.assertEqual(ledger.losses(), 1)
        self.assertEqual(ledger.wins(), 0)
        self.assertEqual(ledger.realized_pnl_cents(), -99)
        self.assertEqual(ledger.cash_cents(), 10000 - 99)
        self.assertGreaterEqual(report.settled_this_cycle, 1)
        self.assertEqual(report.model_version, MODEL_VERSION)
        payload = json.loads(format_json(report))
        self.assertEqual(payload["observed_at"], iso_utc(later))
        self.assertNotEqual(payload["observed_at"], "2026-11-05T19:45:00Z")
        self.assertIn("observed_at_denver", payload)
        self.assertNotEqual(payload["observed_at_denver"], payload["observed_at"])
        self.assertFalse(PARENT.exists())

    def test_double_settle_is_idempotent(self):
        ledger = self._pending_no_99()
        later = datetime(2026, 11, 5, 20, 36, 0, tzinfo=timezone.utc)
        client = _client(**{TICKER: OFFICIAL_NESTED_YES})
        first = run_cycle(_cfg(self.state), client, ledger, later)
        cash = ledger.cash_cents()
        pnl = ledger.realized_pnl_cents()
        second = run_cycle(_cfg(self.state), client, ledger, later)
        self.assertEqual(ledger.pending_count(), 0)
        self.assertEqual(ledger.cash_cents(), cash)
        self.assertEqual(ledger.realized_pnl_cents(), pnl)
        self.assertEqual(ledger.losses(), 1)
        self.assertEqual(first.settled_this_cycle, 1)
        self.assertEqual(second.settled_this_cycle, 0)

    def test_top_level_empty_result_without_unwrap_is_the_bug_shape(self):
        # Documents the official body: result lives only under market.
        self.assertIsNone(OFFICIAL_NESTED_YES.get("result"))
        self.assertEqual(str(OFFICIAL_NESTED_YES.get("result") or ""), "")
        self.assertEqual(unwrap_market(OFFICIAL_NESTED_YES)["result"], "yes")


if __name__ == "__main__":
    unittest.main()
