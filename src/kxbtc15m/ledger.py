"""SQLite paper ledger: idempotent, restart-safe, integer cents."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from kxbtc15m.clock import denver_day

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
    cycle_id TEXT NOT NULL,
    market_ticker TEXT NOT NULL,
    predicted_at TEXT NOT NULL,
    close_time TEXT NOT NULL,
    side TEXT NOT NULL,
    model_version TEXT NOT NULL,
    entry_class TEXT NOT NULL,
    rule TEXT NOT NULL,
    inputs_hash TEXT NOT NULL,
    p_hat TEXT,
    PRIMARY KEY (cycle_id, market_ticker)
);
CREATE TABLE IF NOT EXISTS skips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL,
    market_ticker TEXT,
    reason TEXT NOT NULL,
    skipped_at TEXT NOT NULL,
    UNIQUE (cycle_id, market_ticker)
);
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id TEXT NOT NULL,
    market_ticker TEXT NOT NULL UNIQUE,
    side TEXT NOT NULL,
    contracts INTEGER NOT NULL,
    cost_cents INTEGER NOT NULL,
    fee_cents INTEGER NOT NULL,
    debit_cents INTEGER NOT NULL,
    ask_dollars TEXT NOT NULL,
    model_version TEXT NOT NULL,
    entry_class TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    status TEXT NOT NULL,
    UNIQUE (cycle_id, market_ticker)
);
CREATE TABLE IF NOT EXISTS settlements (
    market_ticker TEXT PRIMARY KEY,
    result TEXT NOT NULL,
    settled_at TEXT NOT NULL,
    credit_cents INTEGER NOT NULL,
    pnl_cents INTEGER NOT NULL,
    denver_day TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class OpenResult:
    opened: bool


@dataclass(frozen=True)
class SettleResult:
    settled: bool
    reason: str | None = None
    pnl_cents: int = 0


class Ledger:
    def __init__(self, path: Path | str, starting_cash_cents: int = 10000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.starting_cash_cents = starting_cash_cents
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._init_meta()

    def close(self) -> None:
        self.conn.close()

    def _init_meta(self) -> None:
        if self._meta("starting_cash_cents") is None:
            self._set_meta("starting_cash_cents", str(self.starting_cash_cents))
            self._set_meta("cash_cents", str(self.starting_cash_cents))
            self._set_meta("peak_equity_cents", str(self.starting_cash_cents))
            self._set_meta("max_drawdown_cents", "0")
        self.conn.commit()

    def _meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else row["value"]

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def _cash(self) -> int:
        return int(self._meta("cash_cents") or 0)

    def _set_cash(self, cents: int) -> None:
        if cents < 0:
            raise RuntimeError("paper cash would go negative; halt")
        self._set_meta("cash_cents", str(cents))

    def _log(self, at: str, kind: str, payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO events(at, kind, payload) VALUES (?, ?, ?)",
            (at, kind, json.dumps(payload, sort_keys=True)),
        )

    def cash_cents(self) -> int:
        return self._cash()

    def pending_rows(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM positions WHERE status = 'pending'"))

    def pending_count(self) -> int:
        return len(self.pending_rows())

    def pending_exposure_cents(self) -> int:
        return sum(int(row["debit_cents"]) for row in self.pending_rows())

    def pending_cost_cents(self) -> int:
        return self.pending_exposure_cents()

    def equity_cents(self) -> int:
        return self.cash_cents() + self.pending_cost_cents()

    def realized_pnl_cents(self) -> int:
        row = self.conn.execute("SELECT COALESCE(SUM(pnl_cents), 0) AS s FROM settlements").fetchone()
        return int(row["s"])

    def wins(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS c FROM settlements WHERE pnl_cents > 0").fetchone()
        return int(row["c"])

    def losses(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS c FROM settlements WHERE pnl_cents < 0").fetchone()
        return int(row["c"])

    def skips(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS c FROM skips").fetchone()
        return int(row["c"])

    def fees_paid_cents(self) -> int:
        row = self.conn.execute("SELECT COALESCE(SUM(fee_cents), 0) AS s FROM positions").fetchone()
        return int(row["s"])

    def max_drawdown_cents(self) -> int:
        return int(self._meta("max_drawdown_cents") or 0)

    def used_downside_cents(self, denver_day: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN pnl_cents < 0 THEN -pnl_cents ELSE 0 END), 0) AS s "
            "FROM settlements WHERE denver_day = ?",
            (denver_day,),
        ).fetchone()
        return int(row["s"]) + self.pending_exposure_cents()

    def prediction(self, market_ticker: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM predictions WHERE market_ticker = ?",
            (market_ticker,),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        if data.get("p_hat") == "":
            data["p_hat"] = None
        return data

    def record_prediction(
        self,
        cycle_id: str,
        market_ticker: str,
        predicted_at: str,
        close_time: str,
        side: str,
        model_version: str,
        entry_class: str,
        rule: str,
        inputs_hash: str,
        p_hat: float | None,
    ) -> bool:
        try:
            self.conn.execute(
                """
                INSERT INTO predictions(
                    cycle_id, market_ticker, predicted_at, close_time, side,
                    model_version, entry_class, rule, inputs_hash, p_hat
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle_id,
                    market_ticker,
                    predicted_at,
                    close_time,
                    side,
                    model_version,
                    entry_class,
                    rule,
                    inputs_hash,
                    None if p_hat is None else str(p_hat),
                ),
            )
        except sqlite3.IntegrityError:
            return False
        self._log(predicted_at, "prediction", {"ticker": market_ticker, "side": side, "rule": rule})
        self.conn.commit()
        return True

    def record_skip(self, cycle_id: str, market_ticker: str | None, reason: str, skipped_at: str) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO skips(cycle_id, market_ticker, reason, skipped_at) VALUES (?, ?, ?, ?)",
                (cycle_id, market_ticker, reason, skipped_at),
            )
        except sqlite3.IntegrityError:
            return False
        self._log(skipped_at, "skip", {"ticker": market_ticker, "reason": reason, "cycle_id": cycle_id})
        self.conn.commit()
        return True

    def open_position(
        self,
        cycle_id: str,
        market_ticker: str,
        side: str,
        contracts: int,
        cost_cents: int,
        fee_cents: int,
        debit_cents: int,
        ask_dollars: str,
        model_version: str,
        entry_class: str,
        opened_at: str,
    ) -> OpenResult:
        existing = self.conn.execute(
            "SELECT 1 FROM positions WHERE market_ticker = ? OR (cycle_id = ? AND market_ticker = ?)",
            (market_ticker, cycle_id, market_ticker),
        ).fetchone()
        if existing:
            return OpenResult(False)
        cash = self._cash()
        if debit_cents > cash:
            raise RuntimeError("paper cash would go negative; halt")
        try:
            self.conn.execute(
                """
                INSERT INTO positions(
                    cycle_id, market_ticker, side, contracts, cost_cents, fee_cents,
                    debit_cents, ask_dollars, model_version, entry_class, opened_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    cycle_id,
                    market_ticker,
                    side,
                    contracts,
                    cost_cents,
                    fee_cents,
                    debit_cents,
                    ask_dollars,
                    model_version,
                    entry_class,
                    opened_at,
                ),
            )
        except sqlite3.IntegrityError:
            return OpenResult(False)
        self._set_cash(cash - debit_cents)
        self._log(
            opened_at,
            "open",
            {"ticker": market_ticker, "debit_cents": debit_cents, "side": side, "contracts": contracts},
        )
        self.conn.commit()
        return OpenResult(True)

    def settle(self, market_ticker: str, result: str, settled_at: str) -> SettleResult:
        normalized = (result or "").strip().lower()
        if normalized not in {"yes", "no"}:
            return SettleResult(False, "result_not_ready")
        already = self.conn.execute(
            "SELECT 1 FROM settlements WHERE market_ticker = ?",
            (market_ticker,),
        ).fetchone()
        if already:
            return SettleResult(False, "already_settled")
        pos = self.conn.execute(
            "SELECT * FROM positions WHERE market_ticker = ? AND status = 'pending'",
            (market_ticker,),
        ).fetchone()
        if pos is None:
            return SettleResult(False, "no_pending")
        contracts = int(pos["contracts"])
        debit = int(pos["debit_cents"])
        credit = 100 * contracts if normalized == pos["side"] else 0
        pnl = credit - debit
        day = str(denver_day(settled_at))
        try:
            self.conn.execute(
                """
                INSERT INTO settlements(market_ticker, result, settled_at, credit_cents, pnl_cents, denver_day)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (market_ticker, normalized, settled_at, credit, pnl, day),
            )
        except sqlite3.IntegrityError:
            return SettleResult(False, "already_settled")
        self.conn.execute(
            "UPDATE positions SET status = 'settled' WHERE market_ticker = ?",
            (market_ticker,),
        )
        self._set_cash(self._cash() + credit)
        equity = self.equity_cents()
        peak = int(self._meta("peak_equity_cents") or equity)
        if equity > peak:
            peak = equity
            self._set_meta("peak_equity_cents", str(peak))
        draw = peak - equity
        prior = int(self._meta("max_drawdown_cents") or 0)
        if draw > prior:
            self._set_meta("max_drawdown_cents", str(draw))
        self._log(
            settled_at,
            "settle",
            {"ticker": market_ticker, "result": normalized, "pnl_cents": pnl, "credit_cents": credit},
        )
        self.conn.commit()
        return SettleResult(True, None, pnl)

    def position_for_cycle(self, cycle_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM positions WHERE cycle_id = ?", (cycle_id,)).fetchone()

    def skip_for_cycle(self, cycle_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM skips WHERE cycle_id = ?", (cycle_id,)).fetchone()
