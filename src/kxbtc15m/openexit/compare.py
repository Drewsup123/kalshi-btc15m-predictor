"""15-minute compare. observed_at is the run clock, not close_time."""

from __future__ import annotations

import json
import os
from pathlib import Path

from kxbtc15m.clock import iso_utc, utc_now
from kxbtc15m.ledger import Ledger
from kxbtc15m.openexit import MODEL_VERSION
from kxbtc15m.openexit.ledger import OpenExitLedger
from kxbtc15m.signal import MODEL_VERSION as BASELINE_MODEL


def _baseline_block(path: Path) -> dict:
    if not path.is_file():
        return {
            "running": False,
            "status": "ledger_not_in_this_environment",
            "path": str(path),
            "detail": "original ledger was not opened or created here; do not reset the parent book",
        }
    ledger = Ledger(path, readonly=True)
    try:
        pending = ledger.pending_rows()
        return {
            "running": True,
            "model_version": BASELINE_MODEL,
            "cash_cents": ledger.cash_cents(),
            "pending_exposure_cents": ledger.pending_exposure_cents(),
            "realized_pnl_cents": ledger.realized_pnl_cents(),
            "wins": ledger.wins(),
            "losses": ledger.losses(),
            "skips": ledger.skips(),
            "pending_count": ledger.pending_count(),
            "pending_tickers": [row["market_ticker"] for row in pending],
        }
    finally:
        ledger.close()


def _pid_alive(watch_pid: Path) -> bool:
    if not watch_pid.is_file():
        return False
    try:
        pid = int(watch_pid.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _openexit_block(path: Path, watch_pid: Path) -> dict:
    running = _pid_alive(watch_pid)
    if not path.is_file():
        return {
            "running": False,
            "status": "not_running",
            "detail": "no openexit.sqlite yet" if not running else "watch pid present but ledger missing",
        }
    ledger = OpenExitLedger(path)
    try:
        pending = ledger.pending_rows()
        events = list(ledger.conn.execute("SELECT at,kind,payload FROM events ORDER BY id DESC LIMIT 8"))
        return {
            "running": running,
            "status": "running" if running else "ledger_only",
            "model_version": MODEL_VERSION,
            "cash_cents": ledger.cash_cents(),
            "pending_exposure_cents": ledger.pending_exposure_cents(),
            "realized_pnl_cents": ledger.realized_pnl_cents(),
            "wins": ledger.wins(),
            "losses": ledger.losses(),
            "skips": ledger.skips(),
            "pending_count": ledger.pending_count(),
            "pending_tickers": [row["market_ticker"] for row in pending],
            "fees_paid_cents": ledger.fees_paid_cents(),
            "last_event_at": ledger.last_event_at(),
            "recent_actions": [{"at": row["at"], "kind": row["kind"], "payload": json.loads(row["payload"])} for row in events],
        }
    finally:
        ledger.close()


def build_compare(baseline_ledger: Path, openexit_dir: Path) -> dict:
    now = utc_now()
    observed = iso_utc(now)
    return {
        "report_kind": "kxbtc15m_15min",
        "schema_version": "2026-11-05.report.v2",
        "observed_at": observed,
        "observed_at_denver": now.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "note": "observed_at is this run, not the market close_time",
        "baseline": _baseline_block(baseline_ledger),
        "open_exit": _openexit_block(openexit_dir / "openexit.sqlite", openexit_dir / "watch.pid"),
        "loss_analysis": {
            "cause": "unknown",
            "label": "hypothesis_only",
            "hypotheses": [
                {
                    "id": "H-envelope",
                    "status": "observed_envelope_unproven_as_parent_runtime_cause",
                    "evidence": "Official GET /markets/KXBTC15M-26NOV051445-45 returns {market:{...}} with result=yes, status=finalized, settlement_ts=2026-11-05T19:45:02.127035Z. A top-level result reader would miss YES.",
                },
                {
                    "id": "H-inconsistent_book",
                    "status": "plausible_unproven",
                    "evidence": "Baseline skips when market ask and 1-opposite bid differ by >2c. Open-exit uses conservative complements instead. Baseline code was not changed this pass.",
                },
            ],
            "parent_pending_note": "This environment does not contain /workspace/personal-finance/kalshi-paper/state/ledger.sqlite. That book was not opened, copied, or reset.",
        },
        "disclaimer": "Simulated paper only. No calibrated edge. Settlement is not a sale.",
    }


def format_compare_text(payload: dict) -> str:
    b = payload["baseline"]
    o = payload["open_exit"]
    lines = [
        "KXBTC15M 15-minute compare",
        f"observed_at: {payload['observed_at']} ({payload.get('observed_at_denver')})",
        f"Baseline: {b.get('status') or ('running' if b.get('running') else 'not available')} cash={b.get('cash_cents')} pending={b.get('pending_exposure_cents')} realized={b.get('realized_pnl_cents')}",
        f"Open-exit: {o.get('status')} cash={o.get('cash_cents')} pending={o.get('pending_exposure_cents')} realized={o.get('realized_pnl_cents')} last_event={o.get('last_event_at')}",
        f"Loss analysis cause={payload['loss_analysis']['cause']} ({payload['loss_analysis'].get('label')})",
        payload["disclaimer"],
    ]
    return "\n".join(lines)
