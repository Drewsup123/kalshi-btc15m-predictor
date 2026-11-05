"""One open-exit tick: settle, maybe enter, maybe exit. No gap backfills."""

from __future__ import annotations

from decimal import Decimal

from kxbtc15m.clock import bucket_id, denver_day, iso_utc, parse_utc
from kxbtc15m.fees import assert_fee_source_ok, load_official_excerpt
from kxbtc15m.openexit import MODEL_VERSION
from kxbtc15m.openexit.exits import ExitConfig, choose_exit
from kxbtc15m.openexit.lean import choose_lean
from kxbtc15m.openexit.ledger import OpenExitLedger
from kxbtc15m.openexit.quotes import LiveQuoteConfig, live_quotes, side_ask_bid
from kxbtc15m.openexit.risk import OpenExitRisk, size_entry
from kxbtc15m.openexit.tape import count_opposite
from kxbtc15m.schema import unwrap_market, unwrap_markets

MAX_OPEN_LOOK_SECONDS = 180
ASK_LO = Decimal("0.10")
ASK_HI = Decimal("0.90")
GAP_SECONDS = 45


def _history(client) -> list[dict]:
    try:
        payload = client.get_json(
            "/markets",
            {"series_ticker": "KXBTC15M", "status": "settled", "limit": "20"},
        )
    except Exception:
        return []
    return unwrap_markets(payload)


def _open_markets(client) -> list[dict]:
    try:
        payload = client.get_json(
            "/markets",
            {"series_ticker": "KXBTC15M", "status": "open", "limit": "10"},
        )
    except Exception:
        return []
    return unwrap_markets(payload)


def _prints_since(client, ticker: str, after_iso: str) -> list[dict]:
    try:
        payload = client.get_json("/markets/trades", {"ticker": ticker, "limit": "100"})
    except Exception:
        return []
    trades = payload.get("trades") if isinstance(payload, dict) else None
    if not isinstance(trades, list):
        return []
    after = parse_utc(after_iso)
    out = []
    for row in trades:
        created = row.get("created_time")
        if not created:
            continue
        if parse_utc(created) > after:
            out.append(row)
    return out


def run_tick(client, ledger: OpenExitLedger, now, series_ticker: str = "KXBTC15M") -> dict:
    now = parse_utc(now)
    now_iso = iso_utc(now)
    report = {
        "action": "idle",
        "skip_reason": None,
        "model_version": MODEL_VERSION,
        "observed_at": now_iso,
        "market_ticker": None,
        "side": None,
        "exit": None,
        "cycle_pnl_cents": None,
        "win_loss": "none",
    }
    try:
        assert_fee_source_ok(load_official_excerpt())
    except ValueError:
        report.update(action="skip", skip_reason="failed_fee_source")
        return report

    for pos in list(ledger.pending_rows()):
        ticker = pos["market_ticker"]
        try:
            raw = client.get_json(f"/markets/{ticker}")
        except Exception:
            continue
        market = unwrap_market(raw)
        if not market:
            continue
        result = str(market.get("result") or "").lower()
        status = str(market.get("status") or "").lower()
        close = market.get("close_time")
        closed = close and parse_utc(close) <= now
        if result in {"yes", "no"} and (status in {"finalized", "settled"} or closed):
            settled = ledger.official_settle(ticker, result, now_iso)
            if settled.ok:
                report.update(
                    action="official_settlement",
                    market_ticker=ticker,
                    side=pos["side"],
                    exit="official_settlement",
                    cycle_pnl_cents=settled.pnl_cents,
                    win_loss="win" if settled.pnl_cents > 0 else "loss" if settled.pnl_cents < 0 else "none",
                )
                return report

    opens = [
        m
        for m in _open_markets(client)
        if str(m.get("status") or "").lower() in {"active", "open"}
        and m.get("close_time")
        and parse_utc(m["close_time"]) > now
    ]
    if not opens:
        report.update(action="skip", skip_reason="market_not_open")
        return report
    market = min(opens, key=lambda m: parse_utc(m.get("close_time") or now_iso))
    ticker = market["ticker"]
    report["market_ticker"] = ticker
    cycle_id = bucket_id(market.get("close_time") or now_iso)
    open_time = market.get("open_time")
    if not open_time:
        report.update(action="skip", skip_reason="invalid_quote")
        return report

    pos = ledger.position(ticker)
    if pos and pos["status"] == "pending":
        last = pos["last_tick_at"]
        if last and (now - parse_utc(last)).total_seconds() > GAP_SECONDS:
            ledger._log(now_iso, "gap", {"ticker": ticker, "gap_seconds": (now - parse_utc(last)).total_seconds()})
            ledger.conn.commit()
        try:
            book = client.get_json(f"/markets/{ticker}/orderbook")
        except Exception:
            report.update(action="skip", skip_reason="failed_feed")
            return report
        quotes = live_quotes(market, book, now, now, LiveQuoteConfig())
        if not quotes.ok:
            ledger.touch_tick(ticker, now_iso, pos["hold_high"])
            report.update(action="hold", skip_reason=quotes.skip_reason, side=pos["side"], exit="hold")
            return report
        ask, bid, _, _ = side_ask_bid(quotes, pos["side"])
        high = max(Decimal(pos["hold_high"]), bid)
        ledger.touch_tick(ticker, now_iso, str(high))
        prints = _prints_since(client, ticker, pos["opened_at"])
        opposite = count_opposite(prints, pos["side"])
        decision = choose_exit(pos["side"], Decimal(pos["entry_ask"]), bid, high, opposite, ExitConfig())
        if decision.reason == "hold":
            report.update(action="hold", side=pos["side"], exit="hold")
            return report
        filled = ledger.exit_at_bid(ticker, bid, decision.reason, now_iso)
        report.update(
            action=decision.reason,
            side=pos["side"],
            exit=decision.reason,
            cycle_pnl_cents=filled.pnl_cents,
            win_loss="win" if filled.pnl_cents > 0 else "loss" if filled.pnl_cents < 0 else "none",
        )
        return report

    if ledger.pending_count() >= 1:
        report.update(action="skip", skip_reason="pending_open")
        return report
    prior = ledger.skip_for(cycle_id) or ledger.position(ticker)
    if prior is not None:
        report.update(action="already_done")
        return report

    since_open = (now - parse_utc(open_time)).total_seconds()
    if since_open > MAX_OPEN_LOOK_SECONDS:
        ledger.record_skip(cycle_id, ticker, "missed_open", now_iso)
        report.update(action="skip", skip_reason="missed_open")
        return report
    if since_open < 0:
        report.update(action="skip", skip_reason="market_not_open")
        return report

    lean = choose_lean(_history(client), open_time)
    if lean.skip_reason:
        ledger.record_skip(cycle_id, ticker, lean.skip_reason, now_iso)
        report.update(action="skip", skip_reason=lean.skip_reason)
        return report

    try:
        book = client.get_json(f"/markets/{ticker}/orderbook")
    except Exception:
        report.update(action="skip", skip_reason="failed_feed")
        return report
    quotes = live_quotes(market, book, now, now, LiveQuoteConfig())
    if not quotes.ok:
        ledger.record_skip(cycle_id, ticker, quotes.skip_reason or "invalid_quote", now_iso)
        report.update(action="skip", skip_reason=quotes.skip_reason)
        return report
    ask, bid, ask_size, _ = side_ask_bid(quotes, lean.side)
    if ask <= ASK_LO or ask >= ASK_HI:
        ledger.record_skip(cycle_id, ticker, "ask_no_room", now_iso)
        report.update(action="skip", skip_reason="ask_no_room", side=lean.side)
        return report

    day = str(denver_day(now))
    sized = size_entry(
        ask,
        ask_size,
        ledger.cash_cents(),
        ledger.used_downside_cents(day),
        ledger.pending_count(),
        OpenExitRisk(),
    )
    if not sized.ok:
        ledger.record_skip(cycle_id, ticker, sized.skip_reason or "per_pick_cap", now_iso)
        report.update(action="skip", skip_reason=sized.skip_reason, side=lean.side)
        return report

    opened = ledger.open_position(
        market_ticker=ticker,
        cycle_id=cycle_id,
        side=lean.side,
        contracts=sized.contracts,
        entry_ask=sized.ask,
        cost_cents=sized.cost_cents,
        entry_fee_cents=sized.entry_fee_cents,
        exit_fee_reserve_cents=sized.exit_fee_reserve_cents,
        reserve_cents=sized.reserve_cents,
        opened_at=now_iso,
    )
    report.update(
        action="entry" if opened.ok else "skip",
        skip_reason=opened.reason,
        side=lean.side,
        contracts=sized.contracts,
        debit_cents=sized.reserve_cents,
    )
    return report
