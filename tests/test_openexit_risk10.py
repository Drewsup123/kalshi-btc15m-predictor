"""Open-exit $10 inclusive / no daily cap. Isolated fixtures only."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from kxbtc15m.openexit import MODEL_VERSION, PRIOR_MODEL_VERSION, RISK_REGIME
from kxbtc15m.openexit.ledger import OpenExitLedger
from kxbtc15m.openexit.risk import OpenExitRisk, size_entry
from kxbtc15m.signal import MODEL_VERSION as BASELINE_MODEL
from tests.isolation import assert_parent_ledger_untouched, snapshot_parent_ledger


CFG = OpenExitRisk()


def _seed_history(path: Path) -> None:
    """Reproduce parent-reported open-exit book: cash 9965, realized -35, flat."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS positions (
            market_ticker TEXT PRIMARY KEY, cycle_id TEXT, side TEXT, contracts INTEGER,
            entry_ask TEXT, cost_cents INTEGER, entry_fee_cents INTEGER,
            exit_fee_reserve_cents INTEGER, reserve_cents INTEGER, hold_high TEXT,
            opened_at TEXT, last_tick_at TEXT, status TEXT
        );
        CREATE TABLE IF NOT EXISTS settlements (
            market_ticker TEXT PRIMARY KEY, kind TEXT, result TEXT, exit_reason TEXT,
            exit_bid TEXT, exit_fee_cents INTEGER, credit_cents INTEGER, pnl_cents INTEGER,
            settled_at TEXT, denver_day TEXT
        );
        CREATE TABLE IF NOT EXISTS skips (
            cycle_id TEXT, market_ticker TEXT, reason TEXT, skipped_at TEXT,
            UNIQUE (cycle_id, market_ticker)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, payload TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO meta(key,value) VALUES(?,?)",
        [
            ("starting_cash_cents", "10000"),
            ("cash_cents", "9965"),
            ("peak_equity_cents", "10000"),
            ("max_drawdown_cents", "35"),
            ("model_version", "exp-open-exit-v1@2026-11-05"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO settlements(market_ticker,kind,result,exit_reason,exit_bid,exit_fee_cents,credit_cents,pnl_cents,settled_at,denver_day)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        [
            ("KXBTC15M-26NOV051630-30", "early_exit", None, "exit_adverse_tape", "0.50", 2, 50, -17, "2026-11-05T21:16:00Z", "2026-11-05"),
            ("KXBTC15M-26NOV051645-45", "early_exit", None, "exit_adverse_tape", "0.36", 3, 72, -18, "2026-11-05T21:30:58Z", "2026-11-05"),
        ],
    )
    conn.execute(
        "INSERT INTO events(at,kind,payload) VALUES(?,?,?)",
        ("2026-11-05T21:16:00Z", "exit_adverse_tape", '{"pnl_cents": -17}'),
    )
    conn.commit()
    conn.close()


class Risk10Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.before = snapshot_parent_ledger()

    def tearDown(self):
        self.tmp.cleanup()
        assert_parent_ledger_untouched(self, self.before)

    def test_defaults_are_ten_dollars_no_daily_cap(self):
        self.assertEqual(CFG.max_debit_cents, 1000)
        self.assertIsNone(CFG.max_daily_downside_cents)
        self.assertEqual(CFG.max_pending, 1)
        self.assertEqual(MODEL_VERSION, "exp-open-exit-v1-risk10@2026-11-05")
        self.assertEqual(PRIOR_MODEL_VERSION, "exp-open-exit-v1@2026-11-05")
        self.assertEqual(BASELINE_MODEL, "exp-baseline-v1@2026-11-05")

    def test_entry_inclusive_at_or_under_1000(self):
        d = size_entry(Decimal("0.40"), Decimal("100"), 10000, 9999, 0, CFG)
        self.assertTrue(d.ok)
        self.assertLessEqual(d.reserve_cents, 1000)
        self.assertGreater(d.reserve_cents, 500)

    def test_over_1000_inclusive_is_per_pick_cap(self):
        # 0.99 * 11 ≈ 1089 + fees exceeds $10
        d = size_entry(Decimal("0.99"), Decimal("20"), 10000, 0, 0, CFG)
        self.assertTrue(d.ok)
        self.assertLessEqual(d.reserve_cents, 1000)
        blocked = size_entry(Decimal("0.99"), Decimal("20"), 50, 0, 0, CFG)
        self.assertFalse(blocked.ok)
        self.assertEqual(blocked.skip_reason, "insufficient_cash")

    def test_no_daily_gate_even_after_large_marked_downside(self):
        d = size_entry(Decimal("0.40"), Decimal("20"), 10000, 800, 0, CFG)
        self.assertTrue(d.ok)
        self.assertNotEqual(d.skip_reason, "daily_downside_cap")
        self.assertGreater(d.reserve_cents, 0)

    def test_more_than_five_dollars_across_sequential_entries(self):
        ledger = OpenExitLedger(self.dir / "openexit.sqlite")
        spent = 0
        for i in range(2):
            sized = size_entry(Decimal("0.40"), Decimal("20"), ledger.cash_cents(), 800, ledger.pending_count(), CFG)
            self.assertTrue(sized.ok)
            self.assertGreater(sized.reserve_cents, 400)
            opened = ledger.open_position(
                market_ticker=f"T{i}",
                cycle_id=f"c{i}",
                side="yes",
                contracts=sized.contracts,
                entry_ask=sized.ask,
                cost_cents=sized.cost_cents,
                entry_fee_cents=sized.entry_fee_cents,
                exit_fee_reserve_cents=sized.exit_fee_reserve_cents,
                reserve_cents=sized.reserve_cents,
                opened_at=f"2026-11-05T22:0{i}:00Z",
            )
            self.assertTrue(opened.ok)
            spent += sized.reserve_cents
            self.assertEqual(ledger.pending_count(), 1)
            ledger.official_settle(f"T{i}", "no", f"2026-11-05T22:0{i}:30Z")
            self.assertEqual(ledger.pending_count(), 0)
        self.assertGreater(spent, 500)
        self.assertLess(ledger.cash_cents(), 10000)
        ledger.close()

    def test_insufficient_cash_no_borrow(self):
        d = size_entry(Decimal("0.40"), Decimal("20"), 10, 0, 0, CFG)
        self.assertFalse(d.ok)
        self.assertEqual(d.skip_reason, "insufficient_cash")
        ledger = OpenExitLedger(self.dir / "openexit.sqlite")
        ledger._set_cash(20)
        ledger.conn.commit()
        sized = size_entry(Decimal("0.40"), Decimal("20"), ledger.cash_cents(), 0, 0, CFG)
        self.assertFalse(sized.ok)
        flag = ledger.open_position(
            market_ticker="X",
            cycle_id="c",
            side="yes",
            contracts=2,
            entry_ask=Decimal("0.40"),
            cost_cents=80,
            entry_fee_cents=4,
            exit_fee_reserve_cents=4,
            reserve_cents=88,
            opened_at="2026-11-05T22:00:00Z",
        )
        self.assertFalse(flag.ok)
        self.assertEqual(flag.reason, "insufficient_cash")
        self.assertEqual(ledger.cash_cents(), 20)
        ledger.close()

    def test_migration_preserves_9965_and_minus_35(self):
        path = self.dir / "openexit.sqlite"
        _seed_history(path)
        ledger = OpenExitLedger(path)
        self.assertEqual(ledger.cash_cents(), 9965)
        self.assertEqual(ledger.realized_pnl_cents(), -35)
        self.assertEqual(ledger.pending_count(), 0)
        self.assertEqual(ledger.risk_regime(), RISK_REGIME)
        self.assertEqual(ledger.model_version(), MODEL_VERSION)
        self.assertEqual(ledger.prior_model_version(), PRIOR_MODEL_VERSION)
        kinds = [row["kind"] for row in ledger.conn.execute("SELECT kind FROM events")]
        self.assertIn("risk_migration", kinds)
        cash = ledger.cash_cents()
        ledger.close()
        again = OpenExitLedger(path)
        self.assertEqual(again.cash_cents(), cash)
        self.assertEqual(again.realized_pnl_cents(), -35)
        migs = list(again.conn.execute("SELECT COUNT(*) c FROM events WHERE kind='risk_migration'"))
        self.assertEqual(migs[0]["c"], 1)
        again.close()


if __name__ == "__main__":
    unittest.main()
