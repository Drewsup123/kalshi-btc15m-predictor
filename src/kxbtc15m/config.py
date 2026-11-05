"""CLI and environment configuration. No secrets."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from kxbtc15m.quotes import QuoteConfig
from kxbtc15m.risk import RiskConfig
from kxbtc15m.signal import DEFAULT_SEED, DEFAULT_THRESHOLD, MODEL_VERSION

DEFAULT_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DEFAULT_STATE_DIR = Path.home() / ".local" / "share" / "kxbtc15m-paper"


@dataclass(frozen=True)
class AppConfig:
    state_dir: Path
    api_base: str = DEFAULT_API_BASE
    series_ticker: str = "KXBTC15M"
    starting_cash_cents: int = 10000
    max_debit_cents: int = 100
    max_daily_downside_cents: int = 500
    max_pending: int = 1
    stale_quote_seconds: int = 30
    near_close_seconds: int = 60
    ask_epsilon: Decimal = Decimal("0.02")
    model_version: str = MODEL_VERSION
    seed: int = DEFAULT_SEED
    momentum_threshold_dollars: Decimal = DEFAULT_THRESHOLD
    timezone: str = "America/Denver"

    @property
    def ledger_path(self) -> Path:
        return Path(self.state_dir) / "ledger.sqlite"

    @property
    def snapshot_dir(self) -> Path:
        return Path(self.state_dir) / "snapshots"

    def risk(self) -> RiskConfig:
        return RiskConfig(
            starting_cash_cents=self.starting_cash_cents,
            max_debit_cents=self.max_debit_cents,
            max_daily_downside_cents=self.max_daily_downside_cents,
            max_pending=self.max_pending,
        )

    def quote(self) -> QuoteConfig:
        return QuoteConfig(
            stale_seconds=self.stale_quote_seconds,
            near_close_seconds=self.near_close_seconds,
            ask_epsilon=self.ask_epsilon,
        )


def load_config(
    state_dir: str | Path | None = None,
    api_base: str | None = None,
    model_version: str | None = None,
) -> AppConfig:
    overlay: dict = {}
    chosen_state = Path(
        state_dir or os.environ.get("KXBTC15M_STATE_DIR") or DEFAULT_STATE_DIR
    ).expanduser()
    cfg_path = chosen_state / "config.json"
    if cfg_path.is_file():
        overlay = json.loads(cfg_path.read_text(encoding="utf-8"))
    return AppConfig(
        state_dir=chosen_state,
        api_base=api_base
        or os.environ.get("KXBTC15M_API_BASE")
        or overlay.get("api_base")
        or DEFAULT_API_BASE,
        series_ticker=overlay.get("series_ticker", "KXBTC15M"),
        starting_cash_cents=int(overlay.get("starting_cash_cents", 10000)),
        max_debit_cents=int(overlay.get("max_debit_cents", 100)),
        max_daily_downside_cents=int(overlay.get("max_daily_downside_cents", 500)),
        max_pending=int(overlay.get("max_pending", 1)),
        stale_quote_seconds=int(overlay.get("stale_quote_seconds", 30)),
        near_close_seconds=int(overlay.get("near_close_seconds", 60)),
        ask_epsilon=Decimal(str(overlay.get("ask_epsilon", "0.02"))),
        model_version=model_version or overlay.get("model_version") or MODEL_VERSION,
        seed=int(overlay.get("seed", DEFAULT_SEED)),
        momentum_threshold_dollars=Decimal(str(overlay.get("momentum_threshold_dollars", DEFAULT_THRESHOLD))),
        timezone=overlay.get("timezone", "America/Denver"),
    )
