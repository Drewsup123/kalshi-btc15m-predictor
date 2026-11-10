# KXBTC15M V3 Prediction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or implement task-by-task in this session). Steps use checkbox (`- [ ]`) syntax for tracking. Spec of record: `docs/superpowers/specs/2026-11-05-kalshi-v3-prediction-design.md` (commit `636db72`).

**Goal:** Phase 1 only — offline historical **replay** evaluation of a frozen first-minute YES/NO forecast for `KXBTC15M`, plus a local read-only results screen. Prediction-only. No trading.

**Architecture:** New isolated package `kxbtc15m.v3`. Public GET inventory (Kalshi live settled + `/historical/markets`) joined to Coinbase BTC-USD 1m candles. Features as-of `t* = open+30s` (completed bars with period end ≤ `t*`). Models A (L2 logistic), A-ret (Ridge log-return → `forecast_end = S_t × exp(ŷ)`), B (purged kNN k=25), C controls. Chronological 70/15/15; walk-forward + 96m+15m embargo inside train/val; holdout once after lock. Artifacts under `var/v3/` (or `$KXBTC15M_V3_STATE_DIR`). Static HTML screen reads those files.

**Tech Stack:** Python 3.11+, numpy, stdlib `urllib`/`unittest`/`json`/`html`. Reuse `kxbtc15m.schema.unwrap_*` and `kxbtc15m.clock.parse_utc`. No scikit-learn required. No pip paid services.

## Global Constraints

Copied from the spec of record, plus the read-only mandate:

- Baseline paper sim (`exp-baseline-v1@2026-11-05`): **Permanently not resumed** under this scope. Ledger **read-only**.
- Open-exit paper sim (`exp-open-exit-v1*` / risk10): **Stopped.** Ledger **read-only.** Do not start `watch` / timers.
- Ledgers `/workspace/personal-finance/kalshi-paper/state/ledger.sqlite` and `/workspace/var/openexit` (and parent copies) — **do not reset, migrate, or write.** Old P&L is not a V3 metric.
- Orders / keys / demo: Forbidden. Public GET only. No new accounts, paid hosting, or API keys unless the user later authorizes them in writing.
- Always-on host / cloud schedule: **Not approved.** No watch, cron, or chat pings from this spec.
- Web trading app: Cancelled earlier. V3 is **not** that project.
- Included model usage: Local numpy for v1. No external paid AI/data.
- **ALWAYS READ-ONLY: public GET endpoints only, no order/auth code paths at all.**
- `t* = open+30s` is the decision cutoff; deadline `+60s` is simulated emit-only; late/missing → miss, no backfill.
- `forecast_end = S_t × exp(ŷ_log)`; CF labels; Coinbase is venue proxy only.
- Default history is `historical_replay` + `prior_print_after_settlement_ts`; event timestamps are not receipts.
- Eventual current `floor_strike` is not an input on the default path.
- Last-10 uses `settlement_ts ≤ t*` (replay) and median **log-return**, not dollar residual, not `close_time < open`.
- Holdout untouched until lock; leakage tests on synthetic + train/val only.
- 80–90% is a chart line, not a pass condition and not a holdout-tuning target.
- Macro off; no invented L2; optional tape may be omitted in v1 (spec: optional).
- Screen: untrained/unavailable honestly; `prediction_asof` / `dataset_asof` vs `run_generated_at`; live panel only if observed-live snapshot exists.
- Do not publish this private draft or open a PR unless asked.

## File map

- Create: `src/kxbtc15m/v3/__init__.py` — `MODEL_VERSION`, `FEATURE_SPEC`
- Create: `src/kxbtc15m/v3/paths.py` — refuse old ledger dirs
- Create: `src/kxbtc15m/v3/clock.py` — `t_star`, deadline, `t_pub_sim`
- Create: `src/kxbtc15m/v3/client.py` — Kalshi + Coinbase public GET; forbidden order/auth fragments
- Create: `src/kxbtc15m/v3/inventory.py` — page/dedup/score-universe/grid holes
- Create: `src/kxbtc15m/v3/candles.py` — Coinbase 1m parse + as-of filter
- Create: `src/kxbtc15m/v3/asof.py` — `S_t`, last-10 eligibility
- Create: `src/kxbtc15m/v3/features.py` — normalized shape vector
- Create: `src/kxbtc15m/v3/split.py` — 70/15/15 + embargo helper
- Create: `src/kxbtc15m/v3/models.py` — logistic, ridge, kNN, scalers
- Create: `src/kxbtc15m/v3/controls.py` — majority, last-10, no-change, last-price
- Create: `src/kxbtc15m/v3/metrics.py` — accuracy, Wilson, coverage, MAE/bias, Brier
- Create: `src/kxbtc15m/v3/lock.py` — freeze scalers/λ before holdout
- Create: `src/kxbtc15m/v3/evaluate.py` — pipeline
- Create: `src/kxbtc15m/v3/screen.py` — static HTML
- Modify: `src/kxbtc15m/cli.py` — `v3-inventory`, `v3-evaluate`, `v3-screen` (read-only wrt old books)
- Create: `tests/test_v3_*.py`
- Create: `var/v3/` at runtime only (gitignored)
- Do **not** modify `cycle.py`, `signal.py`, `risk.py`, `ledger.py`, open-exit engines.

---

### Task 1: Clock and isolation paths

**Files:**
- Create: `src/kxbtc15m/v3/__init__.py`, `clock.py`, `paths.py`
- Test: `tests/test_v3_clock.py`, `tests/test_v3_paths.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_v3_clock.py
from datetime import datetime, timezone, timedelta
from kxbtc15m.v3.clock import t_star, deadline, t_pub_sim, time_left_seconds

def test_t_star_is_open_plus_30s():
    open_t = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
    assert t_star(open_t) == open_t + timedelta(seconds=30)
    assert deadline(open_t) == open_t + timedelta(seconds=60)

def test_t_pub_sim_clamped_and_miss_after_deadline():
    open_t = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
    assert t_pub_sim(open_t, open_t + timedelta(seconds=45)) == open_t + timedelta(seconds=45)
    assert t_pub_sim(open_t, open_t + timedelta(seconds=61)) is None  # missed_deadline

def test_time_left_uses_close_minus_tstar():
    open_t = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
    close_t = datetime(2026, 11, 6, 0, 15, tzinfo=timezone.utc)
    assert time_left_seconds(open_t, close_t) == 14.5 * 60

def test_run_generated_at_is_not_t_pub():
    open_t = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
    run = datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)
    assert t_pub_sim(open_t, t_star(open_t)) != run
```

```python
# tests/test_v3_paths.py
import tempfile
from pathlib import Path
from kxbtc15m.v3.paths import assert_safe_v3_dir, V3Error

def test_refuses_baseline_and_openexit():
    for p in (
        "/workspace/personal-finance/kalshi-paper/state",
        "/workspace/var/openexit",
    ):
        try:
            assert_safe_v3_dir(p)
            raise AssertionError("should have refused")
        except V3Error:
            pass

def test_allows_isolated_temp():
    with tempfile.TemporaryDirectory() as raw:
        got = assert_safe_v3_dir(Path(raw) / "v3")
        assert got.name == "v3"
```

- [ ] **Step 2: Run tests — expect fail**
- [ ] **Step 3: Implement `clock.py` / `paths.py` / `__init__.py`**
- [ ] **Step 4: Tests pass. Commit.**

---

### Task 2: Inventory parse, score universe, grid holes (no live download in tests)

**Files:** `src/kxbtc15m/v3/inventory.py`, `tests/test_v3_inventory.py`

Score universe: `status=finalized`, `result in {yes,no}`, finite `floor_strike` and `expiration_value`, `strike_type=greater_or_equal`. Dedup by ticker. Expected 15m grid from min to max `close_time`.

```python
# tests/test_v3_inventory.py
from kxbtc15m.v3.inventory import score_universe, grid_holes, dedup_by_ticker

def test_excludes_void_and_missing_prints():
    rows = [
        {"ticker": "A", "status": "finalized", "result": "yes", "floor_strike": 1, "expiration_value": "2", "strike_type": "greater_or_equal", "close_time": "2026-01-10T00:15:00Z", "open_time": "2026-01-10T00:00:00Z"},
        {"ticker": "B", "status": "finalized", "result": "", "floor_strike": 1, "expiration_value": "2", "strike_type": "greater_or_equal", "close_time": "2026-01-10T00:30:00Z", "open_time": "2026-01-10T00:15:00Z"},
        {"ticker": "C", "status": "finalized", "result": "no", "floor_strike": None, "expiration_value": "2", "strike_type": "greater_or_equal", "close_time": "2026-01-10T00:45:00Z", "open_time": "2026-01-10T00:30:00Z"},
    ]
    scored, excluded = score_universe(rows)
    assert [r["ticker"] for r in scored] == ["A"]
    assert {e["ticker"] for e in excluded} == {"B", "C"}

def test_dedup_and_grid_hole():
    rows = [
        {"ticker": "A", "close_time": "2026-01-10T00:15:00Z", "open_time": "2026-01-10T00:00:00Z", "status": "finalized", "result": "yes", "floor_strike": 1, "expiration_value": "1.1", "strike_type": "greater_or_equal"},
        {"ticker": "A", "close_time": "2026-01-10T00:15:00Z", "open_time": "2026-01-10T00:00:00Z", "status": "finalized", "result": "yes", "floor_strike": 1, "expiration_value": "1.1", "strike_type": "greater_or_equal"},
        {"ticker": "C", "close_time": "2026-01-10T00:45:00Z", "open_time": "2026-01-10T00:30:00Z", "status": "finalized", "result": "no", "floor_strike": 1, "expiration_value": "0.9", "strike_type": "greater_or_equal"},
    ]
    scored, _ = score_universe(dedup_by_ticker(rows))
    holes = grid_holes(scored)
    assert any(h.endswith("00:30:00Z") for h in holes)
```

- [ ] Tests fail → implement → pass → commit.

---

### Task 3: As-of `S_t` and last-10 (replay vs live receipt)

**Files:** `src/kxbtc15m/v3/asof.py`, `tests/test_v3_asof.py`

Default replay: prior `expiration_value` iff `settlement_ts ≤ t*`. Never eventual current floor. Last-10: `settlement_ts ≤ t*`, not `close_time < open`. Live: `observation_at ≤ t*`.

```python
# tests/test_v3_asof.py
from datetime import datetime, timezone, timedelta
from kxbtc15m.v3.asof import opening_ref, last10
from kxbtc15m.v3.clock import t_star

OPEN = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
TSTAR = t_star(OPEN)

PRIOR = {
    "ticker": "PREV",
    "open_time": "2026-11-05T23:45:00Z",
    "close_time": "2026-11-06T00:00:00Z",
    "settlement_ts": "2026-11-06T00:00:07Z",
    "expiration_value": "100.0",
    "floor_strike": 99.0,
    "result": "yes",
    "status": "finalized",
}
CUR = {
    "ticker": "CUR",
    "open_time": "2026-11-06T00:00:00Z",
    "close_time": "2026-11-06T00:15:00Z",
    "floor_strike": 100.0,  # eventual — forbidden as default S_t
    "expiration_value": "101.0",
    "result": "yes",
}

def test_replay_uses_prior_print_not_eventual_floor():
    s, src, skip = opening_ref(CUR, [PRIOR], TSTAR, availability="historical_replay")
    assert skip is None
    assert s == 100.0
    assert src == "prior_expiration_value"
    assert s != CUR["expiration_value"]

def test_no_prior_print_skips_even_if_eventual_floor_present():
    s, src, skip = opening_ref(CUR, [], TSTAR, availability="historical_replay")
    assert skip == "insufficient_opening_ref"
    assert s is None

def test_settlement_after_tstar_not_eligible_for_last10():
    late = dict(PRIOR, settlement_ts="2026-11-06T00:00:45Z", result="no")
    # close_time < open but settlement after t*
    got = last10([late], TSTAR, availability="historical_replay")
    assert got["used"] == 0

def test_live_late_response_cannot_supply_st():
    s, src, skip = opening_ref(
        CUR, [PRIOR], TSTAR, availability="observed_live",
        observation_at=TSTAR + timedelta(seconds=5),
        request_started_at=TSTAR - timedelta(seconds=5),
    )
    assert skip == "insufficient_opening_ref"
```

- [ ] Tests fail → implement → pass → commit.

---

### Task 4: Candles and normalized features

**Files:** `src/kxbtc15m/v3/candles.py`, `features.py`, `tests/test_v3_features.py`

Coinbase bar at start `T` covers `[T, T+60)`. Include iff period end ≤ `t*`. Open-minute excluded. Vector: log returns 1/4/16/96, vol-scaled, rel volume, range/wick/path, last-10 counts + median log-return. No raw USD residual. Missing 16-bar block → `missing_underlying`.

```python
# tests/test_v3_features.py
from datetime import datetime, timezone, timedelta
from kxbtc15m.v3.candles import filter_completed
from kxbtc15m.v3.features import FEATURE_NAMES, build_features
from kxbtc15m.v3.clock import t_star

OPEN = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
TSTAR = t_star(OPEN)

def bars(n, end=OPEN):
    out = []
    for i in range(n):
        start = end - timedelta(minutes=n - i)
        out.append({"start": start, "open": 100, "high": 101, "low": 99, "close": 100 + 0.01 * i, "volume": 1.0})
    return out

def test_drops_bar_ending_after_tstar():
    illegal = {"start": OPEN, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}  # ends open+60s
    kept = filter_completed(bars(2) + [illegal], TSTAR)
    assert all(b["start"] + timedelta(seconds=60) <= TSTAR or b["start"] + timedelta(seconds=60) <= OPEN for b in kept)
    assert illegal not in kept

def test_feature_names_have_no_usd_residual():
    assert not any("dollar" in n or n.endswith("_usd") for n in FEATURE_NAMES)
    assert "last10_median_logret" in FEATURE_NAMES

def test_insufficient_history_without_16_bars():
    vec, meta, skip = build_features(bars(5), last10={"used": 0, "yes": 0, "no": 0, "median_logret": 0.0}, t_star=TSTAR)
    assert skip == "missing_underlying"
```

- [ ] Tests fail → implement → pass → commit.

---

### Task 5: Split 70/15/15 and embargo

**Files:** `src/kxbtc15m/v3/split.py`, `tests/test_v3_split.py`

Sort by `close_time`. No random split. Embargo ≥ 96m+15m after last training close for walk-forward slices.

```python
# tests/test_v3_split.py
from datetime import datetime, timezone, timedelta
from kxbtc15m.v3.split import chronological_split, walkforward_slices

def test_70_15_15_order_preserved():
    rows = [{"close_time": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * i)} for i in range(100)]
    tr, va, ho = chronological_split(rows)
    assert len(tr) == 70 and len(va) == 15 and len(ho) == 15
    assert tr[-1]["close_time"] < va[0]["close_time"] < ho[0]["close_time"]

def test_embargo_gap():
    rows = [{"close_time": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * i)} for i in range(200)]
    slices = walkforward_slices(rows[:170], slice_days=7)
    for train, test in slices:
        gap = test[0]["close_time"] - train[-1]["close_time"]
        assert gap >= timedelta(minutes=96 + 15)
```

- [ ] Tests fail → implement → pass → commit.

---

### Task 6: Models A, A-ret, B, C

**Files:** `src/kxbtc15m/v3/models.py`, `controls.py`, `tests/test_v3_models.py`

numpy IRLS logistic + L2; Ridge closed form; kNN k=25 Euclidean, unweighted majority; purge neighbors with `open ∈ (t* − 96m, t*]`. Scalers fit on train only. Controls: train majority; last-10 majority (tie skip); no-change YES at `S_t`; last-price `R_t ≥ S_t`.

```python
# tests/test_v3_models.py
import numpy as np
from datetime import datetime, timezone, timedelta
from kxbtc15m.v3.models import fit_logistic, fit_ridge, knn_predict, StandardScaler
from kxbtc15m.v3.controls import majority_side, no_change, last_price_side

def test_scaler_train_only():
    s = StandardScaler().fit(np.array([[0.0], [2.0]]))
    assert abs(s.mean_[0] - 1.0) < 1e-9
    z = s.transform(np.array([[4.0]]))
    assert abs(z[0, 0] - 3.0) < 1e-6  # (4-1)/1 if std of [0,2] is 1? std ddof=0 is 1.0

def test_logistic_separates():
    X = np.vstack([np.zeros((20, 2)), np.ones((20, 2))])
    y = np.array([0] * 20 + [1] * 20)
    m = fit_logistic(X, y, l2=1.0)
    p = m.predict_proba(np.array([[1.0, 1.0]]))[0]
    assert p > 0.5

def test_ridge_zero_when_y_zero():
    X = np.random.RandomState(0).randn(30, 3)
    y = np.zeros(30)
    m = fit_ridge(X, y, l2=1.0)
    assert abs(m.predict(X).mean()) < 1e-6

def test_knn_purges_nearby_window():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    library = [
        {"x": np.zeros(2), "label": 1, "open": t0, "y_log": 0.01},
        {"x": np.ones(2), "label": 0, "open": t0 - timedelta(days=2), "y_log": -0.01},
    ]
    pred, p, yhat = knn_predict(np.zeros(2), t_star=t0 + timedelta(minutes=15, seconds=30), library=library, k=25)
    assert pred == 0  # nearby purged; only far neighbor remains

def test_controls():
    assert majority_side(["yes", "yes", "no"]) == "yes"
    assert no_change() == ("yes", 0.0)
    assert last_price_side(101.0, 100.0) == "yes"
    assert last_price_side(99.0, 100.0) == "no"
```

- [ ] Tests fail → implement → pass → commit.

---

### Task 7: Metrics, freeze/lock, leakage (no real holdout)

**Files:** `src/kxbtc15m/v3/metrics.py`, `lock.py`, `tests/test_v3_metrics.py`, `tests/test_v3_leakage.py`

Skip ≠ error. Empty report has **no numeric accuracy**. Wilson 95%. Replay vs live tables do not blend. Lock file required before holdout metrics.

Leakage fixtures (synthetic + pretend train/val only): future bar dropped; eventual floor unused; last-10 `close_time < open` but `settlement_ts > t*` excluded; live late response unusable; permutation only on a validation copy, never holdout.

```python
# tests/test_v3_metrics.py
from kxbtc15m.v3.metrics import score_table, empty_metrics

def test_skip_not_error():
    rows = [
        {"pred_yes": "yes", "result": "yes", "skip_reason": None, "forecast_end": 101, "expiration_value": 100},
        {"pred_yes": None, "result": "no", "skip_reason": "insufficient_opening_ref", "forecast_end": None, "expiration_value": 100},
    ]
    m = score_table(rows)
    assert m["n_scored"] == 1
    assert m["accuracy"] == 1.0
    assert m["coverage"] == 0.5
    assert m["n_skip"] == 1

def test_empty_has_no_accuracy_number():
    m = empty_metrics()
    assert "accuracy" not in m or m["accuracy"] is None
```

```python
# tests/test_v3_leakage.py
# Reuse asof/feature tests; plus:
def test_permutation_helper_does_not_accept_holdout_tag():
    from kxbtc15m.v3.metrics import permutation_disclosure
    try:
        permutation_disclosure([{"split": "holdout", "pred_yes": "yes", "result": "no"}], split_allowed=("validation",))
        raise AssertionError("must refuse holdout")
    except ValueError:
        pass
```

- [ ] Tests fail → implement → pass → commit.

---

### Task 8: Evaluate pipeline + public GET client (forbidden paths)

**Files:** `src/kxbtc15m/v3/client.py`, `evaluate.py`, `tests/test_v3_client.py`, `tests/test_v3_evaluate.py`

Client: Kalshi default `https://api.elections.kalshi.com/trade-api/v2`; Coinbase `https://api.exchange.coinbase.com`. Raise on any path containing `/portfolio`, `/orders`, `/order_groups`, `/api_keys`, `/cfbenchmarks` (auth). User-Agent identifies GET-only V3.

Evaluate on a tiny in-memory universe: build features, split, fit A/A-ret/B/C on train, pick λ on val (`[1e-2, 1, 10]`), write lock, score holdout once, write `predictions.csv` + `metrics.json`. `run_generated_at` ≠ `t_pub_sim`. Rows tagged `historical_replay`.

- [ ] Tests fail → implement → pass → commit.

---

### Task 9: CLI + isolation fingerprint + results screen

**Files:** modify `cli.py`; `src/kxbtc15m/v3/screen.py`; `tests/test_v3_cli.py`, `tests/test_v3_screen.py`

Subcommands:

- `v3-inventory --state-dir …` — fetch/cache (when implemented)
- `v3-evaluate --state-dir …` — fit+lock+holdout
- `v3-screen --state-dir …` — write `results.html`

Screen: banner with `availability` + `replay_assumption`; clocks `prediction_asof` / `dataset_asof` / `run_generated_at`; live current panel **unavailable** unless `observed_live` snapshot; eval: holdout accuracy vs 80/90 lines, coverage, skips, MAE, A/B/C/baselines, confusion, table. Untrained HTML contains the words `not trained` and no fabricated percent.

Fingerprint parent ledger before/after CLI.

- [ ] Tests fail → implement → pass → commit.

---

### Task 10: Fetch all usable history and run once

Not a unit test. After Task 9 is green:

1. `v3-inventory` pages Kalshi live settled + historical until cursor empty; cache raw JSON under `var/v3/raw/`.
2. Fetch Coinbase 1m for `[min_open−2d, max_close]` chunked, cached.
3. Completeness report in `inventory.json`.
4. `v3-evaluate` with frozen λ from validation only.
5. Do **not** retune on holdout.
6. `v3-screen`; screenshot to `/opt/cursor/artifacts/v3-results-screen.png`.
7. Commit code (not giant raw caches if they blow the repo; raw cache stays in `var/v3` gitignored). Metrics JSON may be committed if small, otherwise artifact-only.

---

## Self-review vs spec

| Spec | Plan |
|---|---|
| `t*=open+30s`, deadline +60s, freeze initial | Task 1 clock; evaluate uses `t_pub_sim=t*` |
| Replay ≠ observed; settlement_ts is proxy | Task 3; row `availability=historical_replay` |
| No eventual floor as default `S_t` | Task 3 skip |
| Last-10 log-return, `settlement_ts` | Task 3–4 |
| Normalized shape, no raw USD | Task 4 names |
| A / A-ret / B k=25 purged / C | Task 6 |
| 70/15/15, embargo 96m+15m, holdout once | Task 5, 8 lock |
| Leakage not on holdout | Task 7 |
| No L2/macro/tape required | Tape omitted v1 (optional) |
| Screen honest clocks + unavailable live | Task 9 |
| Read-only public GET, no order paths | Task 8 client + Global Constraints |
| Old ledgers untouched | Task 1 paths + Task 9 fingerprint |
| 80–90 not a pass | Screen lines only; Task 10 no retune |

**Out of this plan (Phase 2):** always-on live first-minute daemon. On-demand live CLI may exist as a stub that records receipts but is not required to populate the live panel for Phase 1.

**Optional tape pressure:** omitted in v1 to keep the full-history run bounded; feature slot remains `missing_pressure=1`.
