"""Isolated open-exit paper ledger. Never the baseline file."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from kxbtc15m.clock import denver_day, iso_utc, utc_now
from kxbtc15m.fees import taker_fee_cents
from kxbtc15m.openexit import MODEL_VERSION, PRIOR_MODEL_VERSION, RISK_REGIME
from kxbtc15m.openexit.paths import assert_safe_openexit_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS positions (
    market_ticker TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    side TEXT NOT NULL,
    contracts INTEGER NOT NULL,
    entry_ask TEXT NOT NULL,
    cost_cents INTEGER NOT NULL,
    entry_fee_cents INTEGER NOT NULL,
    exit_fee_reserve_cents INTEGER NOT NULL,
    reserve_cents INTEGER NOT NULL,
    hold_high TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    last_tick_at TEXT,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settlements (
    market_ticker TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    result TEXT,
    exit_reason TEXT,
    exit_bid TEXT,
    exit_fee_cents INTEGER NOT NULL,
    credit_cents INTEGER NOT NULL,
    pnl_cents INTEGER NOT NULL,
    settled_at TEXT NOT NULL,
    denver_day TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skips (
    cycle_id TEXT NOT NULL,
    market_ticker TEXT,
    reason TEXT NOT NULL,
    skipped_at TEXT NOT NULL,
    UNIQUE (cycle_id, market_ticker)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Flag:
    ok: bool
    reason: str | None = None
    pnl_cents: int = 0


class OpenExitLedger:
    def __init__(self, path: Path | str, starting_cash_cents: int = 10000):
        self.path = Path(assert_safe_openexit_dir(Path(path).parent)) / Path(path).name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        existed = self._meta("cash_cents") is not None
        if not existed:
            self._set("starting_cash_cents", str(starting_cash_cents))
            self._set("cash_cents", str(starting_cash_cents))
            self._set("peak_equity_cents", str(starting_cash_cents))
            self._set("max_drawdown_cents", "0")
            self.conn.commit()
        self._migrate_risk_regime(existed)

    def _migrate_risk_regime(self, existed: bool) -> None:
        if self._meta("risk_regime") == RISK_REGIME:
            if self._meta("model_version") != MODEL_VERSION:
                self._set("model_version", MODEL_VERSION)
                self.conn.commit()
            return
        prior = self._meta("model_version") or (PRIOR_MODEL_VERSION if existed else MODEL_VERSION)
        self._set("prior_model_version", prior)
        self._set("model_version", MODEL_VERSION)
        self._set("risk_regime", RISK_REGIME)
        self._set("risk_max_debit_cents", "1000")
        self._set("risk_daily_downside", "none")
        if existed:
            self._log(
                iso_utc(utc_now()),
                "risk_migration",
                {
                    "from": prior,
                    "to": MODEL_VERSION,
                    "regime": RISK_REGIME,
                    "max_debit_cents": 1000,
                    "daily_downside": "none",
                    "cash_cents": self.cash_cents(),
                    "realized_pnl_cents": self.realized_pnl_cents(),
                    "pending_count": self.pending_count(),
                },
            )
        self.conn.commit()

    def risk_regime(self) -> str:
        return self._meta("risk_regime") or RISK_REGIME

    def model_version(self) -> str:
        return self._meta("model_version") or MODEL_VERSION

    def prior_model_version(self) -> str | None:
        return self._meta("prior_model_version")

    def close(self) -> None:
        self.conn.close()

    def _meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else row["value"]

    def _set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def cash_cents(self) -> int:
        return int(self._meta("cash_cents") or 0)

    def _set_cash(self, cents: int) -> None:
        if cents < 0:
            raise RuntimeError("paper cash would go negative; halt")
        self._set("cash_cents", str(cents))

    def _log(self, at: str, kind: str, payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO events(at,kind,payload) VALUES(?,?,?)",
            (at, kind, json.dumps(payload, sort_keys=True)),
        )

    def pending_rows(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM positions WHERE status='pending'"))

    def pending_count(self) -> int:
        return len(self.pending_rows())

    def pending_exposure_cents(self) -> int:
        return sum(int(row["reserve_cents"]) for row in self.pending_rows())

    def equity_cents(self) -> int:
        return self.cash_cents() + sum(int(row["cost_cents"]) + int(row["entry_fee_cents"]) for row in self.pending_rows())

    def realized_pnl_cents(self) -> int:
        row = self.conn.execute("SELECT COALESCE(SUM(pnl_cents),0) s FROM settlements").fetchone()
        return int(row["s"])

    def wins(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) c FROM settlements WHERE pnl_cents>0").fetchone()["c"])

    def losses(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) c FROM settlements WHERE pnl_cents<0").fetchone()["c"])

    def skips(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) c FROM skips").fetchone()["c"])

    def fees_paid_cents(self) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(entry_fee_cents),0) s FROM positions"
        ).fetchone()
        extra = self.conn.execute("SELECT COALESCE(SUM(exit_fee_cents),0) s FROM settlements").fetchone()
        return int(row["s"]) + int(extra["s"])

    def used_downside_cents(self, day: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN pnl_cents<0 THEN -pnl_cents ELSE 0 END),0) s "
            "FROM settlements WHERE denver_day=?",
            (day,),
        ).fetchone()
        return int(row["s"]) + self.pending_exposure_cents()

    def max_drawdown_cents(self) -> int:
        return int(self._meta("max_drawdown_cents") or 0)

    def position(self, ticker: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM positions WHERE market_ticker=?", (ticker,)).fetchone()

    def skip_for(self, cycle_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM skips WHERE cycle_id=?", (cycle_id,)).fetchone()

    def record_skip(self, cycle_id: str, ticker: str | None, reason: str, at: str) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO skips(cycle_id,market_ticker,reason,skipped_at) VALUES(?,?,?,?)",
                (cycle_id, ticker, reason, at),
            )
        except sqlite3.IntegrityError:
            return False
        self._log(at, "skip", {"cycle_id": cycle_id, "ticker": ticker, "reason": reason})
        self.conn.commit()
        return True

    def open_position(self, **kwargs) -> Flag:
        if self.position(kwargs["market_ticker"]) is not None:
            return Flag(False, "already_open")
        reserve = int(kwargs["reserve_cents"])
        cash = self.cash_cents()
        if reserve > cash:
            return Flag(False, "insufficient_cash")
        try:
            self.conn.execute(
                """
                INSERT INTO positions(
                    market_ticker,cycle_id,side,contracts,entry_ask,cost_cents,entry_fee_cents,
                    exit_fee_reserve_cents,reserve_cents,hold_high,opened_at,last_tick_at,status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'pending')
                """,
                (
                    kwargs["market_ticker"],
                    kwargs["cycle_id"],
                    kwargs["side"],
                    kwargs["contracts"],
                    str(kwargs["entry_ask"]),
                    kwargs["cost_cents"],
                    kwargs["entry_fee_cents"],
                    kwargs["exit_fee_reserve_cents"],
                    reserve,
                    str(kwargs["entry_ask"]),
                    kwargs["opened_at"],
                    kwargs["opened_at"],
                ),
            )
        except sqlite3.IntegrityError:
            return Flag(False, "already_open")
        self._set_cash(cash - reserve)
        self._log(kwargs["opened_at"], "entry", {"ticker": kwargs["market_ticker"], "side": kwargs["side"]})
        self.conn.commit()
        return Flag(True)

    def touch_tick(self, ticker: str, at: str, hold_high: str) -> None:
        self.conn.execute(
            "UPDATE positions SET last_tick_at=?, hold_high=? WHERE market_ticker=? AND status='pending'",
            (at, hold_high, ticker),
        )
        self.conn.commit()

    def last_event_at(self) -> str | None:
        row = self.conn.execute("SELECT at FROM events ORDER BY id DESC LIMIT 1").fetchone()
        return None if row is None else row["at"]

    def _mark_drawdown(self) -> None:
        equity = self.equity_cents()
        peak = int(self._meta("peak_equity_cents") or equity)
        if equity > peak:
            peak = equity
            self._set("peak_equity_cents", str(peak))
        draw = peak - equity
        if draw > int(self._meta("max_drawdown_cents") or 0):
            self._set("max_drawdown_cents", str(draw))

    def exit_at_bid(self, ticker: str, bid: Decimal, reason: str, at: str) -> Flag:
        pos = self.conn.execute(
            "SELECT * FROM positions WHERE market_ticker=? AND status='pending'", (ticker,)
        ).fetchone()
        if pos is None:
            return Flag(False, "no_pending")
        already = self.conn.execute("SELECT 1 FROM settlements WHERE market_ticker=?", (ticker,)).fetchone()
        if already:
            return Flag(False, "already_settled")
        contracts = int(pos["contracts"])
        try:
            exit_fee = taker_fee_cents(contracts, bid)
        except ValueError:
            return Flag(False, "invalid_bid")
        credit = dollars_to_cents_floor(Decimal(str(bid)) * contracts)
        reserved = int(pos["reserve_cents"])
        spent = int(pos["cost_cents"]) + int(pos["entry_fee_cents"])
        pnl = credit - spent - exit_fee
        leftover_reserve = reserved - spent
        self.conn.execute(
            """
            INSERT INTO settlements(market_ticker,kind,result,exit_reason,exit_bid,exit_fee_cents,credit_cents,pnl_cents,settled_at,denver_day)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (ticker, "early_exit", None, reason, str(bid), exit_fee, credit, pnl, at, str(denver_day(at))),
        )
        self.conn.execute("UPDATE positions SET status='exited' WHERE market_ticker=?", (ticker,))
        self._set_cash(self.cash_cents() + leftover_reserve + credit - exit_fee)
        self._log(at, reason, {"ticker": ticker, "bid": str(bid), "pnl_cents": pnl})
        self._mark_drawdown()
        self.conn.commit()
        return Flag(True, reason, pnl)

    def official_settle(self, ticker: str, result: str, at: str) -> Flag:
        normalized = (result or "").strip().lower()
        if normalized not in {"yes", "no"}:
            return Flag(False, "result_not_ready")
        already = self.conn.execute("SELECT 1 FROM settlements WHERE market_ticker=?", (ticker,)).fetchone()
        if already:
            return Flag(False, "already_settled")
        pos = self.conn.execute(
            "SELECT * FROM positions WHERE market_ticker=? AND status='pending'", (ticker,)
        ).fetchone()
        if pos is None:
            return Flag(False, "no_pending")
        contracts = int(pos["contracts"])
        reserved = int(pos["reserve_cents"])
        spent = int(pos["cost_cents"]) + int(pos["entry_fee_cents"])
        credit = 100 * contracts if normalized == pos["side"] else 0
        pnl = credit - spent
        leftover = reserved - spent
        self.conn.execute(
            """
            INSERT INTO settlements(market_ticker,kind,result,exit_reason,exit_bid,exit_fee_cents,credit_cents,pnl_cents,settled_at,denver_day)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (ticker, "official_settlement", normalized, "official_settlement", None, 0, credit, pnl, at, str(denver_day(at))),
        )
        self.conn.execute("UPDATE positions SET status='settled' WHERE market_ticker=?", (ticker,))
        self._set_cash(self.cash_cents() + leftover + credit)
        self._log(at, "official_settlement", {"ticker": ticker, "result": normalized, "pnl_cents": pnl})
        self._mark_drawdown()
        self.conn.commit()
        return Flag(True, "official_settlement", pnl)


def dollars_to_cents_floor(value: Decimal) -> int:
    from decimal import ROUND_FLOOR

    cents = (Decimal(str(value)) / Decimal("0.01")).to_integral_value(rounding=ROUND_FLOOR)
    return int(cents)
