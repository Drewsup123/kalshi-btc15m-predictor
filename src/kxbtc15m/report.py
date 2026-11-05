"""JSON and readable paper reports. Pending cost is never treated as profit."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from kxbtc15m.clock import denver_day, iso_utc
from kxbtc15m.ledger import Ledger
from kxbtc15m.money import cents_to_dollars

SLIPPAGE_ASSUMPTION = (
    "Fill at conservative executable ask (max of market ask and book-implied ask); "
    "no extra adverse tick. Optimistic versus live latency."
)
DISCLAIMER = (
    "Simulated paper results only. Not a licensed advisor. "
    "Past paper P&L is not future results. Experimental baseline claims no calibrated edge."
)


@dataclass
class Report:
    action: str
    skip_reason: str | None
    cycle_id: str | None
    market_ticker: str | None
    side: str | None
    rule: str | None
    model_version: str
    entry_class: str | None
    p_hat: None
    contracts: int
    debit_cents: int
    cash_cents: int
    pending_exposure_cents: int
    pending_cost_cents: int
    equity_cents: int
    realized_pnl_cents: int
    wins: int
    losses: int
    skips: int
    pending_count: int
    fees_paid_cents: int
    max_drawdown_cents: int
    used_downside_cents: int
    denver_day: str
    settled_this_cycle: int
    data_health: str
    slippage_assumption: str = SLIPPAGE_ASSUMPTION
    disclaimer: str = DISCLAIMER
    extras: dict = field(default_factory=dict)

    def as_public_dict(self) -> dict:
        payload = asdict(self)
        extras = payload.pop("extras") or {}
        payload.update(extras)
        payload["cash"] = cents_to_dollars(self.cash_cents)
        payload["pending_exposure"] = cents_to_dollars(self.pending_exposure_cents)
        payload["equity"] = cents_to_dollars(self.equity_cents)
        payload["realized_pnl"] = _signed_dollars(self.realized_pnl_cents)
        payload["win_rate_settled_picks_only"] = _win_rate(self.wins, self.losses)
        return payload


def _signed_dollars(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{cents_to_dollars(abs(cents))}"


def _win_rate(wins: int, losses: int) -> str:
    settled = wins + losses
    if settled == 0:
        return "n/a (0 settled picks; skips excluded)"
    return f"{wins}/{settled} = {wins / settled:.1%} (settled picks only; skips excluded)"


def ledger_snapshot(ledger: Ledger, now, model_version: str) -> dict:
    day = str(denver_day(now))
    return {
        "cash_cents": ledger.cash_cents(),
        "pending_exposure_cents": ledger.pending_exposure_cents(),
        "pending_cost_cents": ledger.pending_cost_cents(),
        "equity_cents": ledger.equity_cents(),
        "realized_pnl_cents": ledger.realized_pnl_cents(),
        "wins": ledger.wins(),
        "losses": ledger.losses(),
        "skips": ledger.skips(),
        "pending_count": ledger.pending_count(),
        "fees_paid_cents": ledger.fees_paid_cents(),
        "max_drawdown_cents": ledger.max_drawdown_cents(),
        "used_downside_cents": ledger.used_downside_cents(day),
        "denver_day": day,
        "model_version": model_version,
        "as_of": iso_utc(now),
    }


def build_report(ledger: Ledger, now, model_version: str, **fields) -> Report:
    snap = ledger_snapshot(ledger, now, model_version)
    return Report(
        action=fields.get("action", "status"),
        skip_reason=fields.get("skip_reason"),
        cycle_id=fields.get("cycle_id"),
        market_ticker=fields.get("market_ticker"),
        side=fields.get("side"),
        rule=fields.get("rule"),
        model_version=model_version,
        entry_class=fields.get("entry_class"),
        p_hat=None,
        contracts=fields.get("contracts", 0),
        debit_cents=fields.get("debit_cents", 0),
        settled_this_cycle=fields.get("settled_this_cycle", 0),
        data_health=fields.get("data_health", "ok"),
        **{k: snap[k] for k in (
            "cash_cents",
            "pending_exposure_cents",
            "pending_cost_cents",
            "equity_cents",
            "realized_pnl_cents",
            "wins",
            "losses",
            "skips",
            "pending_count",
            "fees_paid_cents",
            "max_drawdown_cents",
            "used_downside_cents",
            "denver_day",
        )},
    )


def format_json(report: Report) -> str:
    return json.dumps(report.as_public_dict(), indent=2, sort_keys=True)


def format_text(report: Report) -> str:
    rate = _win_rate(report.wins, report.losses)
    action = report.action
    if report.skip_reason:
        action = f"{report.action} ({report.skip_reason})"
    lines = [
        "KXBTC15M personal paper cycle",
        f"Action: {action}",
        f"Denver day: {report.denver_day}  cycle: {report.cycle_id or '—'}  market: {report.market_ticker or '—'}",
        f"Model: {report.model_version}  class: {report.entry_class or '—'}  rule: {report.rule or '—'}  p_hat: none",
        f"Cash: ${cents_to_dollars(report.cash_cents)}  pending exposure: ${cents_to_dollars(report.pending_exposure_cents)}  equity at cost: ${cents_to_dollars(report.equity_cents)}",
        f"Realized P&L: {_signed_dollars(report.realized_pnl_cents)}  (pending is not realized profit)",
        f"Wins/losses/skips/pending: {report.wins}/{report.losses}/{report.skips}/{report.pending_count}",
        f"Win rate: {rate}",
        f"Fees paid: ${cents_to_dollars(report.fees_paid_cents)}  used daily downside: ${cents_to_dollars(report.used_downside_cents)}  max drawdown: ${cents_to_dollars(report.max_drawdown_cents)}",
        f"Data health: {report.data_health}",
        f"Slippage assumption: {report.slippage_assumption}",
        report.disclaimer,
    ]
    return "\n".join(lines)
