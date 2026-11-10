"""Observed-live current + next-market preview. Public GET only. No scheduler."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from kxbtc15m.clock import iso_utc, parse_utc
from kxbtc15m.schema import unwrap_markets
from kxbtc15m.v3 import SERIES
from kxbtc15m.v3.client import PublicGetClient
from kxbtc15m.v3.evaluate import build_replay_rows
from kxbtc15m.v3.fetch import DEFAULT_API_BASE, COINBASE
from kxbtc15m.v3.sweep import apply_family, PREOPEN_OFFSET

DENVER = ZoneInfo("America/Denver")


def denver_stamp(dt) -> str:
    return parse_utc(dt).astimezone(DENVER).strftime("%Y-%m-%d %H:%M %Z")


def _observation_get(client: PublicGetClient, url: str):
    started = datetime.now(timezone.utc)
    payload = client.get_json(url)
    done = datetime.now(timezone.utc)
    return payload, started, done


def fetch_open_and_next(client: PublicGetClient, api_base: str = DEFAULT_API_BASE) -> dict:
    open_url = api_base.rstrip("/") + f"/markets?series_ticker={SERIES}&status=open&limit=10"
    nxt_url = api_base.rstrip("/") + f"/markets?series_ticker={SERIES}&status=unopened&limit=200"
    open_payload, _, open_obs = _observation_get(client, open_url)
    next_payload, _, next_obs = _observation_get(client, nxt_url)
    now = datetime.now(timezone.utc)
    opened = unwrap_markets(open_payload)
    unopened = unwrap_markets(next_payload)
    current = None
    if opened:
        current = sorted(opened, key=lambda m: parse_utc(m["open_time"]))[-1]
    upcoming = [m for m in unopened if parse_utc(m.get("open_time") or "1970-01-01T00:00:00Z") >= now]
    nxt = sorted(upcoming, key=lambda m: parse_utc(m["open_time"]))[0] if upcoming else None
    return {
        "current": current,
        "next": nxt,
        "current_observation_at": iso_utc(open_obs),
        "next_observation_at": iso_utc(next_obs),
        "now": iso_utc(now),
    }


def fetch_coinbase_last(client: PublicGetClient) -> tuple[float | None, str | None]:
    payload, _, obs = _observation_get(client, f"{COINBASE}/products/BTC-USD/ticker")
    try:
        price = float(payload["price"])
    except (TypeError, ValueError, KeyError):
        return None, iso_utc(obs)
    return price, iso_utc(obs)


def _elapsed_offset(market: dict, now: datetime) -> int:
    open_t = parse_utc(market["open_time"])
    close_t = parse_utc(market["close_time"])
    if now <= open_t:
        # Seconds before open (negative). Features use period end ≤ now, not the future open.
        return int((now - open_t).total_seconds())
    elapsed = (now - open_t).total_seconds()
    legal = [0, 30, 60, 120, 300, 420, 600, 720, 840]
    chosen = 0
    for off in legal:
        if off <= elapsed and open_t.timestamp() + off < close_t.timestamp():
            chosen = off
    return int(chosen)


def _latest_print(priors: list[dict], t_dec: datetime, coinbase_last: float | None) -> tuple[float | None, str]:
    eligible = []
    for m in priors:
        if not m.get("settlement_ts"):
            continue
        if str(m.get("result") or "").lower() not in {"yes", "no"}:
            continue
        if parse_utc(m["settlement_ts"]) > t_dec:
            continue
        try:
            eligible.append((parse_utc(m["settlement_ts"]), float(m["expiration_value"])))
        except (TypeError, ValueError, KeyError):
            continue
    if eligible:
        eligible.sort(key=lambda x: x[0])
        return eligible[-1][1], "prior_expiration_value"
    if coinbase_last is not None:
        return coinbase_last, "coinbase_last_print"
    return None, "none"


def forecast_market(
    market: dict,
    bars: list[dict],
    priors: list[dict],
    t_offset: int,
    fit: dict,
    family: str,
    observation_at: str,
    coinbase_last: float | None,
    availability: str = "observed_live",
) -> dict:
    rows = build_replay_rows([market] + [p for p in priors if p.get("ticker") != market.get("ticker")], bars, offset_seconds=t_offset)
    row = next((r for r in rows if r.get("ticker") == market.get("ticker")), None)
    if row is None:
        return {"skip_reason": "no_row", "availability": availability}
    t_dec = parse_utc(row["prediction_asof"])
    obs = parse_utc(observation_at)
    if availability == "observed_live" and obs > t_dec:
        # Live freeze: if the GET finished after t_dec, still show the card as preview-at-now
        # but label that observation_at missed t_dec for a frozen-at-offset claim.
        row["live_note"] = "observation_after_offset; card is as-of observation, not a missed-offset freeze"
    est, src = _latest_print(priors, t_dec, coinbase_last)
    if row.get("S_t") is None and est is not None:
        row["S_t"] = est
        row["S_t_source"] = src
        if row.get("skip_reason") == "insufficient_opening_ref":
            row["skip_reason"] = None
    pred_rows = apply_family([row], family, fit)
    pred = pred_rows[0]
    return {
        "ticker": market.get("ticker"),
        "status": market.get("status"),
        "open_time": market.get("open_time"),
        "close_time": market.get("close_time"),
        "open_denver": denver_stamp(market["open_time"]),
        "close_denver": denver_stamp(market["close_time"]),
        "S_t": pred.get("S_t") or row.get("S_t") or est,
        "S_t_source": row.get("S_t_source") or src,
        "R_t": row.get("R_t") or coinbase_last,
        "pred_yes": pred.get("pred_yes"),
        "p_yes": pred.get("p_yes"),
        "forecast_end": pred.get("forecast_end"),
        "skip_reason": pred.get("skip_reason"),
        "family": family,
        "decision_offset_s": t_offset,
        "prediction_asof": row.get("prediction_asof"),
        "observation_at": observation_at,
        "availability": availability,
        "label": "PREVIEW / pre-open" if t_offset <= 0 else "observed_live",
        "calibration": "uncalibrated",
        "live_note": row.get("live_note"),
    }


def build_preview_bundle(
    client: PublicGetClient,
    bars: list[dict],
    settled: list[dict],
    fit_preopen: dict,
    fit_inwindow: dict,
    family_preopen: str,
    family_inwindow: str,
    api_base: str = DEFAULT_API_BASE,
) -> dict:
    snap = fetch_open_and_next(client, api_base)
    last, last_obs = fetch_coinbase_last(client)
    now = parse_utc(snap["now"])
    current_card = None
    if snap["current"]:
        off = _elapsed_offset(snap["current"], now)
        fam = family_inwindow if off > 0 else family_preopen
        fit = fit_inwindow if off > 0 else fit_preopen
        current_card = forecast_market(
            snap["current"],
            bars,
            settled,
            off,
            fit,
            fam,
            snap["current_observation_at"],
            last,
        )
        current_card["card"] = "current"
    next_card = None
    if snap["next"]:
        next_off = _elapsed_offset(snap["next"], now)
        next_card = forecast_market(
            snap["next"],
            bars,
            settled,
            next_off,
            fit_preopen,
            family_preopen,
            snap["next_observation_at"],
            last,
        )
        next_card["card"] = "next"
        next_card["label"] = "PREVIEW / pre-open"
    return {
        "availability": "observed_live",
        "now": snap["now"],
        "coinbase_last": last,
        "coinbase_observation_at": last_obs,
        "current": current_card,
        "next": next_card,
        "family_preopen": family_preopen,
        "family_inwindow": family_inwindow,
    }
