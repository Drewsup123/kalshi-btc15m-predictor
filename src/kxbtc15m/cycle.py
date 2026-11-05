"""One paper cycle: settle, discover, snapshot, signal, risk, simulate."""

from __future__ import annotations

import json
from decimal import Decimal

from kxbtc15m.clock import bucket_id, denver_day, iso_utc, parse_utc
from kxbtc15m.config import AppConfig
from kxbtc15m.fees import assert_fee_source_ok, load_official_excerpt
from kxbtc15m.ledger import Ledger
from kxbtc15m.quotes import ask_and_size, evaluate_quote
from kxbtc15m.report import Report, build_report
from kxbtc15m.risk import size_and_gate
from kxbtc15m.signal import LastPrint, choose_side
from kxbtc15m.client import FeedError, PublicClient
from kxbtc15m.schema import unwrap_market

TERMINAL_SKIPS = frozenset(
    {
        "thin_book",
        "invalid_ask",
        "invalid_quote",
        "inconsistent_book",
        "stale_quote",
        "near_close",
        "unsupported_fee_type",
        "per_pick_cap",
        "daily_downside_cap",
        "insufficient_cash",
    }
)


def _save_snapshot(cfg: AppConfig, cycle_id: str, ticker: str, payload: dict) -> None:
    cfg.snapshot_dir.mkdir(parents=True, exist_ok=True)
    safe_cycle = cycle_id.replace(":", "")
    path = cfg.snapshot_dir / f"{safe_cycle}_{ticker}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _pick_open_market(markets: list[dict], now) -> dict | None:
    candidates = []
    for market in markets:
        status = str(market.get("status") or "").lower()
        if status not in {"active", "open"}:
            continue
        close = market.get("close_time")
        if not close:
            continue
        if parse_utc(close) <= now:
            continue
        candidates.append(market)
    if not candidates:
        return None
    return min(candidates, key=lambda item: parse_utc(item["close_time"]))


def _last_print(client: PublicClient, series_ticker: str) -> LastPrint | None:
    try:
        payload = client.get_json(
            "/markets",
            {"series_ticker": series_ticker, "status": "settled", "limit": "8"},
        )
    except FeedError:
        return None
    for market in payload.get("markets") or []:
        floor = market.get("floor_strike")
        expiration = market.get("expiration_value")
        if floor in (None, "") or expiration in (None, ""):
            continue
        try:
            return LastPrint(floor=Decimal(str(floor)), expiration=Decimal(str(expiration)))
        except Exception:
            continue
    return None


def _settle_pending(client: PublicClient, ledger: Ledger, now_iso: str) -> tuple[int, str]:
    settled = 0
    health = "ok"
    for row in list(ledger.pending_rows()):
        ticker = row["market_ticker"]
        try:
            raw = client.get_json(f"/markets/{ticker}")
        except FeedError as exc:
            health = f"failed_feed:{exc.status or 'network'}"
            continue
        market = unwrap_market(raw)
        if not market:
            health = "failed_feed:malformed"
            continue
        result = ledger.settle(ticker, str(market.get("result") or ""), now_iso)
        if result.settled:
            settled += 1
    return settled, health


def run_cycle(cfg: AppConfig, client: PublicClient, ledger: Ledger, now) -> Report:
    now = parse_utc(now)
    now_iso = iso_utc(now)
    model_version = cfg.model_version

    try:
        assert_fee_source_ok(load_official_excerpt())
    except ValueError:
        return build_report(
            ledger,
            now,
            model_version,
            action="skip",
            skip_reason="failed_fee_source",
            data_health="fee_source_missing",
        )

    settled_n, health = _settle_pending(client, ledger, now_iso)

    try:
        series_payload = client.get_json(f"/series/{cfg.series_ticker}")
        open_payload = client.get_json(
            "/markets",
            {"series_ticker": cfg.series_ticker, "status": "open", "limit": "10"},
        )
    except FeedError as exc:
        return build_report(
            ledger,
            now,
            model_version,
            action="skip",
            skip_reason="failed_feed",
            settled_this_cycle=settled_n,
            data_health=f"failed_feed:{exc.status or 'network'}",
        )

    series = series_payload.get("series") or {}
    if str(series.get("fee_type") or "") != "quadratic":
        cycle_id = bucket_id(now)
        ledger.record_skip(cycle_id, cfg.series_ticker, "unsupported_fee_type", now_iso)
        return build_report(
            ledger,
            now,
            model_version,
            action="skip",
            skip_reason="unsupported_fee_type",
            cycle_id=cycle_id,
            settled_this_cycle=settled_n,
            data_health=health,
        )

    market = _pick_open_market(list(open_payload.get("markets") or []), now)
    if market is None:
        return build_report(
            ledger,
            now,
            model_version,
            action="skip",
            skip_reason="market_not_open",
            cycle_id=bucket_id(now),
            settled_this_cycle=settled_n,
            data_health=health,
        )

    ticker = market["ticker"]
    cycle_id = bucket_id(market["close_time"])
    existing = ledger.position_for_cycle(cycle_id)
    prior_skip = ledger.skip_for_cycle(cycle_id)
    if existing is not None or (prior_skip is not None and prior_skip["reason"] in TERMINAL_SKIPS):
        return build_report(
            ledger,
            now,
            model_version,
            action="already_done",
            cycle_id=cycle_id,
            market_ticker=ticker,
            settled_this_cycle=settled_n,
            data_health=health,
            side=existing["side"] if existing else None,
        )

    try:
        book = client.get_json(f"/markets/{ticker}/orderbook")
    except FeedError as exc:
        return build_report(
            ledger,
            now,
            model_version,
            action="skip",
            skip_reason="failed_feed",
            cycle_id=cycle_id,
            market_ticker=ticker,
            settled_this_cycle=settled_n,
            data_health=f"failed_feed:{exc.status or 'network'}",
        )

    _save_snapshot(
        cfg,
        cycle_id,
        ticker,
        {"captured_at": now_iso, "market": market, "orderbook": book, "series": series},
    )

    quote = evaluate_quote(market, book, now, now, cfg.quote())
    if not quote.ok:
        ledger.record_skip(cycle_id, ticker, quote.skip_reason or "invalid_quote", now_iso)
        return build_report(
            ledger,
            now,
            model_version,
            action="skip",
            skip_reason=quote.skip_reason,
            cycle_id=cycle_id,
            market_ticker=ticker,
            settled_this_cycle=settled_n,
            data_health=health,
        )

    signal = choose_side(
        ticker,
        _last_print(client, cfg.series_ticker),
        seed=cfg.seed,
        threshold_dollars=cfg.momentum_threshold_dollars,
        model_version=model_version,
    )
    if parse_utc(now_iso) > parse_utc(market["close_time"]):
        ledger.record_skip(cycle_id, ticker, "near_close", now_iso)
        return build_report(
            ledger,
            now,
            model_version,
            action="skip",
            skip_reason="near_close",
            cycle_id=cycle_id,
            market_ticker=ticker,
            settled_this_cycle=settled_n,
            data_health=health,
        )

    ledger.record_prediction(
        cycle_id=cycle_id,
        market_ticker=ticker,
        predicted_at=now_iso,
        close_time=market["close_time"],
        side=signal.side,
        model_version=signal.model_version,
        entry_class=signal.entry_class,
        rule=signal.rule,
        inputs_hash=signal.inputs_hash,
        p_hat=signal.p_hat,
    )

    ask, size = ask_and_size(quote, signal.side)
    day = str(denver_day(now))
    risk = size_and_gate(
        ask=ask,
        book_size=size,
        cash_cents=ledger.cash_cents(),
        used_downside_cents=ledger.used_downside_cents(day),
        pending_count=ledger.pending_count(),
        cfg=cfg.risk(),
    )
    if not risk.ok:
        ledger.record_skip(cycle_id, ticker, risk.skip_reason or "per_pick_cap", now_iso)
        return build_report(
            ledger,
            now,
            model_version,
            action="skip",
            skip_reason=risk.skip_reason,
            cycle_id=cycle_id,
            market_ticker=ticker,
            side=signal.side,
            rule=signal.rule,
            entry_class=signal.entry_class,
            settled_this_cycle=settled_n,
            data_health=health,
        )

    ledger.open_position(
        cycle_id=cycle_id,
        market_ticker=ticker,
        side=signal.side,
        contracts=risk.contracts,
        cost_cents=risk.cost_cents,
        fee_cents=risk.fee_cents,
        debit_cents=risk.debit_cents,
        ask_dollars=str(risk.ask),
        model_version=signal.model_version,
        entry_class=signal.entry_class,
        opened_at=now_iso,
    )
    return build_report(
        ledger,
        now,
        model_version,
        action="entry",
        cycle_id=cycle_id,
        market_ticker=ticker,
        side=signal.side,
        rule=signal.rule,
        entry_class=signal.entry_class,
        contracts=risk.contracts,
        debit_cents=risk.debit_cents,
        settled_this_cycle=settled_n,
        data_health=health,
    )
