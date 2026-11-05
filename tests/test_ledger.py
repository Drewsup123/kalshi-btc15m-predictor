import tempfile
import unittest
from pathlib import Path

from kxbtc15m.ledger import Ledger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.sqlite"
        self.live_default = Path("/tmp/kxbtc15m-MUST-NOT-TOUCH-live.sqlite")
        self.assertNotEqual(self.path, self.live_default)

    def tearDown(self):
        self.tmp.cleanup()

    def _open(self) -> Ledger:
        return Ledger(self.path, starting_cash_cents=10000)

    def test_starts_at_one_hundred_dollars(self):
        ledger = self._open()
        self.assertEqual(ledger.cash_cents(), 10000)
        self.assertEqual(ledger.realized_pnl_cents(), 0)
        self.assertEqual(ledger.pending_count(), 0)

    def test_open_position_debits_cash_not_realized(self):
        ledger = self._open()
        ledger.record_prediction(
            cycle_id="2026-11-05T19:30:00Z",
            market_ticker="KXBTC15M-A",
            predicted_at="2026-11-05T19:16:00Z",
            close_time="2026-11-05T19:30:00Z",
            side="yes",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            rule="seeded_control",
            inputs_hash="abc",
            p_hat=None,
        )
        pos = ledger.open_position(
            cycle_id="2026-11-05T19:30:00Z",
            market_ticker="KXBTC15M-A",
            side="yes",
            contracts=1,
            cost_cents=67,
            fee_cents=2,
            debit_cents=69,
            ask_dollars="0.6700",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T19:16:00Z",
        )
        self.assertTrue(pos.opened)
        self.assertEqual(ledger.cash_cents(), 10000 - 69)
        self.assertEqual(ledger.realized_pnl_cents(), 0)
        self.assertEqual(ledger.pending_count(), 1)
        self.assertEqual(ledger.pending_exposure_cents(), 69)
        self.assertEqual(ledger.pending_cost_cents(), 69)
        self.assertEqual(ledger.equity_cents(), 10000)

    def test_duplicate_open_is_noop(self):
        ledger = self._open()
        kwargs = dict(
            cycle_id="2026-11-05T19:30:00Z",
            market_ticker="KXBTC15M-A",
            side="yes",
            contracts=1,
            cost_cents=67,
            fee_cents=2,
            debit_cents=69,
            ask_dollars="0.6700",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T19:16:00Z",
        )
        ledger.open_position(**kwargs)
        again = ledger.open_position(**kwargs)
        self.assertFalse(again.opened)
        self.assertEqual(ledger.cash_cents(), 10000 - 69)
        self.assertEqual(ledger.pending_count(), 1)

    def test_settle_win_updates_realized_only_once(self):
        ledger = self._open()
        ledger.open_position(
            cycle_id="2026-11-05T19:30:00Z",
            market_ticker="KXBTC15M-A",
            side="yes",
            contracts=1,
            cost_cents=67,
            fee_cents=2,
            debit_cents=69,
            ask_dollars="0.6700",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T19:16:00Z",
        )
        first = ledger.settle(
            market_ticker="KXBTC15M-A",
            result="yes",
            settled_at="2026-11-05T19:31:00Z",
        )
        second = ledger.settle(
            market_ticker="KXBTC15M-A",
            result="yes",
            settled_at="2026-11-05T19:32:00Z",
        )
        self.assertTrue(first.settled)
        self.assertFalse(second.settled)
        self.assertEqual(ledger.pending_count(), 0)
        # credit 100, spent 69, net +31; cash = 9931 + 100 = 10031
        self.assertEqual(ledger.cash_cents(), 10031)
        self.assertEqual(ledger.realized_pnl_cents(), 31)
        self.assertEqual(ledger.wins(), 1)
        self.assertEqual(ledger.losses(), 0)

    def test_settle_loss_is_negative_realized(self):
        ledger = self._open()
        ledger.open_position(
            cycle_id="2026-11-05T19:15:00Z",
            market_ticker="KXBTC15M-B",
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
        ledger.settle(market_ticker="KXBTC15M-B", result="no", settled_at="2026-11-05T19:16:00Z")
        self.assertEqual(ledger.cash_cents(), 10000 - 69)
        self.assertEqual(ledger.realized_pnl_cents(), -69)
        self.assertEqual(ledger.losses(), 1)
        self.assertEqual(ledger.fees_paid_cents(), 2)

    def test_missing_result_stays_pending(self):
        ledger = self._open()
        ledger.open_position(
            cycle_id="2026-11-05T19:30:00Z",
            market_ticker="KXBTC15M-C",
            side="no",
            contracts=1,
            cost_cents=40,
            fee_cents=2,
            debit_cents=42,
            ask_dollars="0.4000",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T19:16:00Z",
        )
        kept = ledger.settle(market_ticker="KXBTC15M-C", result="", settled_at="2026-11-05T19:31:00Z")
        self.assertFalse(kept.settled)
        self.assertEqual(kept.reason, "result_not_ready")
        self.assertEqual(ledger.pending_count(), 1)
        self.assertEqual(ledger.realized_pnl_cents(), 0)

    def test_restart_restores_cash_and_pending(self):
        ledger = self._open()
        ledger.record_skip(
            cycle_id="2026-11-05T19:00:00Z",
            market_ticker="KXBTC15M-SKIP",
            reason="thin_book",
            skipped_at="2026-11-05T18:50:00Z",
        )
        ledger.open_position(
            cycle_id="2026-11-05T19:30:00Z",
            market_ticker="KXBTC15M-D",
            side="yes",
            contracts=1,
            cost_cents=50,
            fee_cents=2,
            debit_cents=52,
            ask_dollars="0.5000",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T19:16:00Z",
        )
        ledger.close()
        again = Ledger(self.path, starting_cash_cents=10000)
        self.assertEqual(again.cash_cents(), 10000 - 52)
        self.assertEqual(again.pending_count(), 1)
        self.assertEqual(again.skips(), 1)
        self.assertEqual(again.realized_pnl_cents(), 0)

    def test_prediction_not_rewritten_on_settle(self):
        ledger = self._open()
        ledger.record_prediction(
            cycle_id="2026-11-05T19:30:00Z",
            market_ticker="KXBTC15M-E",
            predicted_at="2026-11-05T19:16:00Z",
            close_time="2026-11-05T19:30:00Z",
            side="yes",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            rule="momentum",
            inputs_hash="hash-e",
            p_hat=None,
        )
        ledger.open_position(
            cycle_id="2026-11-05T19:30:00Z",
            market_ticker="KXBTC15M-E",
            side="yes",
            contracts=1,
            cost_cents=50,
            fee_cents=2,
            debit_cents=52,
            ask_dollars="0.5000",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T19:16:00Z",
        )
        ledger.settle(market_ticker="KXBTC15M-E", result="yes", settled_at="2026-11-05T19:31:00Z")
        pred = ledger.prediction("KXBTC15M-E")
        self.assertEqual(pred["predicted_at"], "2026-11-05T19:16:00Z")
        self.assertEqual(pred["inputs_hash"], "hash-e")
        self.assertIsNone(pred["p_hat"])
        rewritten = ledger.record_prediction(
            cycle_id="2026-11-05T19:30:00Z",
            market_ticker="KXBTC15M-E",
            predicted_at="2026-11-05T19:40:00Z",
            close_time="2026-11-05T19:30:00Z",
            side="no",
            model_version="tamper",
            entry_class="model_gated",
            rule="tamper",
            inputs_hash="nope",
            p_hat=0.75,
        )
        self.assertFalse(rewritten)
        pred = ledger.prediction("KXBTC15M-E")
        self.assertEqual(pred["predicted_at"], "2026-11-05T19:16:00Z")
        self.assertEqual(pred["side"], "yes")
        self.assertIsNone(pred["p_hat"])

    def test_daily_used_downside_excludes_wins(self):
        ledger = self._open()
        ledger.open_position(
            cycle_id="2026-11-05T18:00:00Z",
            market_ticker="WIN",
            side="yes",
            contracts=1,
            cost_cents=50,
            fee_cents=2,
            debit_cents=52,
            ask_dollars="0.5000",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T17:50:00Z",
        )
        ledger.settle(market_ticker="WIN", result="yes", settled_at="2026-11-05T18:01:00Z")
        ledger.open_position(
            cycle_id="2026-11-05T18:15:00Z",
            market_ticker="LOSS",
            side="yes",
            contracts=1,
            cost_cents=60,
            fee_cents=2,
            debit_cents=62,
            ask_dollars="0.6000",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T18:05:00Z",
        )
        ledger.settle(market_ticker="LOSS", result="no", settled_at="2026-11-05T18:16:00Z")
        ledger.open_position(
            cycle_id="2026-11-05T18:30:00Z",
            market_ticker="PEND",
            side="no",
            contracts=1,
            cost_cents=40,
            fee_cents=2,
            debit_cents=42,
            ask_dollars="0.4000",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T18:20:00Z",
        )
        used = ledger.used_downside_cents(denver_day="2026-11-05")
        self.assertEqual(used, 62 + 42)

    def test_drawdown_from_equity_not_pending_mark(self):
        ledger = self._open()
        ledger.open_position(
            cycle_id="2026-11-05T19:00:00Z",
            market_ticker="DD",
            side="yes",
            contracts=1,
            cost_cents=80,
            fee_cents=2,
            debit_cents=82,
            ask_dollars="0.8000",
            model_version="exp-baseline-v1@2026-11-05",
            entry_class="experimental",
            opened_at="2026-11-05T18:50:00Z",
        )
        # Pending must not look like a $1 mark profit.
        self.assertEqual(ledger.equity_cents(), 10000)
        self.assertEqual(ledger.max_drawdown_cents(), 0)
        ledger.settle(market_ticker="DD", result="no", settled_at="2026-11-05T19:01:00Z")
        self.assertEqual(ledger.equity_cents(), 10000 - 82)
        self.assertEqual(ledger.max_drawdown_cents(), 82)


if __name__ == "__main__":
    unittest.main()
