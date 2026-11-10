# KXBTC15M V3 strategy sweep + next-market preview (addendum)

> **For agentic workers:** REQUIRED SUB-SKILL: implement task-by-task (TDD). Parent plan: `docs/superpowers/plans/2026-11-09-kalshi-v3-prediction.md` (`d53301a`). Spec of record: `docs/superpowers/specs/2026-11-05-kalshi-v3-prediction-design.md` (`636db72`). This addendum does **not** replace Phase 1 isolation or the original first-minute lock.

**Goal:** Pre-register and score a broad YES/NO strategy grid (decision time, Brownian z, fitted models, market-implied, regimes, kNN, ensembles, selective coverage) aiming at **75%** without tuning on any holdout. Add a read-only **Next market preview** card and a public-GET refresh CLI.

**Architecture:** New modules under `kxbtc15m.v3` reuse inventory/candles already in `var/v3/`. Decision time `t_dec = open + offset` replaces the Phase-1-only `t* = open+30s` for sweep rows. Features and `S_t` still as-of `t_dec` under `historical_replay` / `prior_print_after_settlement_ts`. Selection uses train+val walk-forward + 111m embargo only. Final numbers: fresh settled windows with `close_time` > `lock.json dataset_asof` if `n` is large enough; otherwise the existing holdout labeled **previously viewed**.

**Tech stack:** Python 3.12, numpy, stdlib, optional free `scikit-learn` HistGradientBoosting (no LightGBM required). No paid services.

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
- **ALWAYS READ-ONLY: public GET endpoints only, no order/auth code paths at all.**

Addendum-only rules:

- Do not rewrite Phase 1 `lock.json` λ. Sweep writes `var/v3/sweep/` (variants.json, selection.json, preview.json).
- Do not tune on the previously viewed holdout or on any fresh holdout.
- Selective rows must show **accuracy and coverage**. Never hide coverage.
- Market-implied uses public trades with `created_time ≤ t_dec` only. Current `yes_bid`/`last_price` on a settled row is **not** a replay feature.
- Pre-open preview is labeled **PREVIEW / pre-open**. Estimated start = latest print (Coinbase last close or prior official print if `settlement_ts ≤ now`). Not official CF floor unless a live receipt exists.

## Pre-registered grid (frozen before any new holdout look)

**Decision offsets (seconds after `open_time`):** `30, 60, 120, 300, 420, 600, 720, 840`  
plus **pre-open** `offset=0` (bars with period end ≤ open; used for preview backtest).

**Families (every offset unless noted):**

| id | Rule | Notes |
|---|---|---|
| `C_lastprice` | YES iff `R_t ≥ S_t` | control |
| `C_nochange` | always YES | ŷ=0 |
| `C_majority` | train majority | fitted on train only |
| `C_last10` | last-10 majority; skip if used<10 or tie | coverage < 1 |
| `D_brownian_16` | `p=Φ(z)`, `z=log(R_t/S_t)/(σ_16 √τ)` | τ=minutes to close, min 1s; σ=1m log-return RMS over last 16 completed bars |
| `D_brownian_96` | same, σ over 96 bars | |
| `A_logistic` | Phase-1 shape logistic, λ=10 (locked) | refit intercept/coef on train at that offset |
| `A_logistic_z` | logistic on shape + `z_16` + `log(τ)` | λ=10 |
| `A_hgb` | sklearn `HistGradientBoostingClassifier` (max_depth=3, max_iter=80, lr=0.05) if importable; else skip recorded | |
| `B_knn_k25` | purged kNN k=25 | all offsets |
| `B_knn_k11` / `B_knn_k51` | kNN k=11 and 51 | offsets 30, 300, 840 only |
| `E_regime_trend` | last-price if `logret_16` available else majority | bull/bear split is the last-price itself on signed move |
| `E_regime_vol` | last-price if `atr16` ≥ train median else majority | calm vs wild |
| `F_vote` | majority of `{C_lastprice, D_brownian_16, A_logistic}` | skip if <2 votes |
| `I_yes_last` | last public trade `yes_price_dollars` with `created_time ≤ t_dec`; YES iff ≥ 0.50 | skip `implied_unavailable` if no trade; do not invent |
| `S_{model}_c{c}` | selective: emit iff `|p_yes−0.5| ≥ c` | `model ∈ {D_brownian_16, A_logistic_z}`; `c ∈ {0.05,0.10,0.15,0.20,0.25,0.30,0.35,0.40}` |

**Selection (train+val only):** among variants, walk-forward (7-day, 111m embargo) mean accuracy. If any variant has walk-forward accuracy ≥ 0.75, pick the one with **highest coverage** among those. Else pick highest walk-forward accuracy. Store the choice in `selection.json` before scoring holdout.

**Final scoring:** count settled score-universe rows with `close_time` > lock `dataset_asof`. If `n ≥ 200`, that set is `holdout_fresh` (untouched). Else score the original Phase-1 holdout as `holdout_previously_viewed`, state `n_fresh`, variant count, and a multiple-comparisons caveat.

## File map

- Create: `docs/superpowers/plans/2026-11-10-kalshi-v3-strategy-sweep.md` (this file)
- Modify: `src/kxbtc15m/v3/clock.py` — `decision_time(open, offset_seconds)`
- Create: `src/kxbtc15m/v3/brownian.py` — `norm_cdf`, `z_score`, `p_yes_brownian`
- Create: `src/kxbtc15m/v3/implied.py` — as-of last YES trade
- Modify: `src/kxbtc15m/v3/evaluate.py` — `build_replay_rows(..., offset_seconds=)`
- Create: `src/kxbtc15m/v3/sweep.py` — grid, WF select, score, persist
- Create: `src/kxbtc15m/v3/preview.py` — observed_live current + next
- Modify: `src/kxbtc15m/v3/screen.py` — time curve, sweep table, preview card
- Modify: `src/kxbtc15m/v3/pipeline.py`, `cli.py` — `v3-sweep`, `v3-preview`
- Create: `tests/test_v3_sweep.py`, `tests/test_v3_preview.py`, `tests/test_v3_brownian.py`
- Do **not** modify `cycle.py`, ledgers, open-exit, or Phase-1 `lock.json`.

---

### Task 1: Decision clock + Brownian (TDD)

**Test:** `t_dec(open, 840) == open+14m`; bars with period end after `t_dec` unused; `p_yes` → 1 when `R_t ≫ S_t` and τ small; `p_yes` → 0.5 when `R_t == S_t`.

```python
from datetime import datetime, timezone, timedelta
from kxbtc15m.v3.clock import decision_time
from kxbtc15m.v3.brownian import p_yes_brownian

open_t = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
assert decision_time(open_t, 840) == open_t + timedelta(minutes=14)
p, z = p_yes_brownian(r_t=101.0, s_t=100.0, sigma=0.0004, tau_minutes=1.0)
assert p > 0.99
p0, _ = p_yes_brownian(r_t=100.0, s_t=100.0, sigma=0.001, tau_minutes=10.0)
assert abs(p0 - 0.5) < 1e-9
```

### Task 2: Replay rows at arbitrary offset

Same `S_t` rule (prior print iff `settlement_ts ≤ t_dec`). Current-window Coinbase bars allowed only if period end ≤ `t_dec`. Never current `expiration_value`.

### Task 3: Sweep runner

Fit on train only. Walk-forward on train+val. Write `sweep/variants.json` with every variant (id, offset_s, accuracy, wilson, coverage, n, split_label). No holdout reads until `selection.json` exists.

### Task 4: Implied trades (optional coverage)

Public `GET /markets/trades` and `/historical/trades?ticker=`. Cache under `var/v3/raw/trades/`. If a ticker has no as-of trade, skip `implied_unavailable` (coverage, not error). Do not use settled-row `last_price`.

### Task 5: Next-market preview + CLI

`v3-preview` GETs `status=open` (current) and `status=unopened` (earliest `open_time` ≥ now). `observation_at` = HTTP response completed. Card fields: ticker, Denver open/close, estimated start, predicted result, p_yes, predicted end, PREVIEW/pre-open. Backtest offset=0 on the same split policy; show accuracy+CI beside the card. No scheduler.

### Task 6: Screen

Top: current (observed_live or unavailable) + **Next market preview**. Then accuracy-vs-time curve for `C_lastprice`, `D_brownian_16`, `A_logistic_z`, `I_yes_last`. Sweep table. 75% reference line. Coverage always visible. Holdout banner: `previously viewed` or `fresh`.

## Self-review vs spec

- Replay vs live clocks unchanged; new offsets are additional frozen initials, not mutations of the Phase-1 row.
- Eventual floor still unused.
- Holdout not used for selection; previously viewed labeled if reused.
- 75% is a target, not a license to hide skips.
- Read-only GET client still forbids `/orders` `/portfolio` `/api_keys`.

## Execution note

Run `v3-sweep` then `v3-preview` then `v3-screen`. Commit after tests; push after the sweep. Screenshot `/opt/cursor/artifacts/v3-sweep-results.png` (and preview close-up if needed).
