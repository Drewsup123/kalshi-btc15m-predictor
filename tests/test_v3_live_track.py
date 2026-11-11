"""Append-only live calls, settle scoring, and % math."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from kxbtc15m.v3.live_track import (
    LIVE_CALLS_NAME,
    load_calls,
    record_frozen_call,
    score_calls_against_settled,
    summarize_track,
)


def test_record_frozen_call_append_once_immutable():
    with tempfile.TemporaryDirectory() as raw:
        state = Path(raw)
        first = {
            "ticker": "KXBTC15M-AAA",
            "pred_yes": "yes",
            "decision_offset_s": 300,
            "prediction_asof": "2026-11-11T18:05:00Z",
            "p_yes": 0.61,
            "family": "D_brownian_16",
            "frozen_at": "2026-11-11T18:05:01Z",
        }
        assert record_frozen_call(state, first) is True
        # Same ticker+offset must not rewrite / duplicate
        again = dict(first)
        again["p_yes"] = 0.99
        again["pred_yes"] = "no"
        assert record_frozen_call(state, again) is False
        lines = (state / LIVE_CALLS_NAME).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        stored = json.loads(lines[0])
        assert stored["pred_yes"] == "yes"
        assert stored["p_yes"] == 0.61

        other = dict(first)
        other["ticker"] = "KXBTC15M-BBB"
        assert record_frozen_call(state, other) is True
        assert len(load_calls(state)) == 2


def test_score_settled_and_summarize_today_vs_alltime():
    with tempfile.TemporaryDirectory() as raw:
        state = Path(raw)
        record_frozen_call(
            state,
            {
                "ticker": "T1",
                "pred_yes": "yes",
                "decision_offset_s": 60,
                "prediction_asof": "2026-11-11T17:00:30Z",
                "frozen_at": "2026-11-11T17:00:31Z",
            },
        )
        record_frozen_call(
            state,
            {
                "ticker": "T2",
                "pred_yes": "no",
                "decision_offset_s": 60,
                "prediction_asof": "2026-11-11T17:15:30Z",
                "frozen_at": "2026-11-11T17:15:31Z",
            },
        )
        record_frozen_call(
            state,
            {
                "ticker": "T3",
                "pred_yes": "yes",
                "decision_offset_s": 60,
                "prediction_asof": "2026-11-10T17:00:30Z",
                "frozen_at": "2026-11-10T17:00:31Z",
            },
        )
        settled = [
            {"ticker": "T1", "result": "yes", "settlement_ts": "2026-11-11T17:15:05Z"},
            {"ticker": "T2", "result": "yes", "settlement_ts": "2026-11-11T17:30:05Z"},
            {"ticker": "T3", "result": "yes", "settlement_ts": "2026-11-10T17:15:05Z"},
        ]
        scored = score_calls_against_settled(load_calls(state), settled)
        assert scored[0]["correct"] is True
        assert scored[1]["correct"] is False
        assert scored[2]["correct"] is True
        now = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)
        summary = summarize_track(scored, now=now)
        assert summary["all_time"]["n_scored"] == 3
        assert summary["all_time"]["n_correct"] == 2
        assert summary["all_time"]["summary"] == "2 of 3 correct (67%)"
        assert summary["today"]["n_scored"] == 2
        assert summary["today"]["n_correct"] == 1
        assert summary["today"]["summary"] == "1 of 2 correct (50%)"
