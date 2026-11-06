# Kalshi V3 prediction — design of record

**Status:** conceptual design approved 2026-11-06 (Drew: “I approve this V3 design. Proceed with it.”). This file is the written spec for user review. **No implementation, fit, bulk download, daemon, or live runner until the written spec is accepted and a plan is written.**  
**Date:** 2026-11-06  
**Filename date:** `2026-11-05` (repo convention).  
**Supersedes for V3 only:** last-10 direction as a *model*; open-exit tape-exit rules as a *predictor*. Those remain historical paper strategies. They are not V3.

**One-liner:** at each `KXBTC15M` open, publish one **frozen** YES/NO (and an uncalibrated probability if the model emits one) within the first minute, from **normalized chart shape** known at a fixed instant, then score it against the official Kalshi CF settlement — not against Coinbase and not against a rewritten later update.

---

## 0. Isolation and what stays off

| Item | Rule |
|---|---|
| Baseline paper sim (`exp-baseline-v1@2026-11-05`) | **Permanently not resumed** under this scope. Ledger **read-only**. |
| Open-exit paper sim (`exp-open-exit-v1*` / risk10) | **Stopped.** Ledger **read-only.** Do not start `watch` / timers. |
| Ledgers | `/workspace/personal-finance/kalshi-paper/state/ledger.sqlite` and `/workspace/var/openexit` (and parent copies) — **do not reset, migrate, or write.** Old P&L is not a V3 metric. |
| Orders / keys / demo | Forbidden. Public GET only. No new accounts, paid hosting, or API keys unless the user later authorizes them in writing. |
| Always-on host / cloud schedule | **Not approved.** No watch, cron, or chat pings from this spec. |
| Web trading app | Cancelled earlier. V3 is **not** that project. |
| Included model usage | Local numpy for v1. No external paid AI/data. |

V3 state, if created later: `$KXBTC15M_V3_STATE_DIR` (default `var/v3/` in this tree; parent install may set `~/.local/share/kxbtc15m-v3`). It must refuse to open the old ledger paths for write.

---

## 1. Goal and non-goals

### Goal

1. Inventory **all accessible** settled `KXBTC15M` markets (live + historical tiers).
2. For each window, at a **fixed first-minute instant**, build as-of features and publish a frozen prediction — or an explicit miss/skip.
3. Fit a compact regularized classifier and a train-only pattern-similarity challenger on **train/validation only**.
4. Score **untouched holdout** YES/NO honestly (coverage, skips, baselines, intervals). End-price error is secondary.
5. Persist versioned artifacts a **local read-only** results screen can render. Untrained / missing as-of data shows **unavailable**, never fake metrics.

### Non-goals

- Promising 80–90% accuracy (display reference only).
- Tuning or re-splitting the holdout to chase that line.
- Trading-profit backtests, fill replay, or “we would have made $X” (no historical L2).
- Treating Coinbase (or event `live_data`) as CF Benchmarks.
- Using eventual `floor_strike` on a settled row as if it had been observed at `t*`.
- Backfilling a late initial forecast after `open+60s`.
- Overwriting the frozen initial with a later intra-window update.
- Macro features (source not verified).
- ETH/SOL/XRP/DOGE/BNB **training** in v1 (schema may be series-keyed for later).
- Resuming old sims, real orders, publishing this private draft, or opening a PR.

---

## 2. Official labels (CF) vs venue proxy

Settlement source on `GET /series/KXBTC15M`: CF Benchmarks. Live `rules_primary` (probed): YES if the 60-second simple average of BRTI **before close** is **at least** the 60-second simple average **before open**. `strike_type = greater_or_equal`. `rules_secondary`: official value is that average, rounded to 2 decimals.

| Name | Field | Role |
|---|---|---|
| Official opening ref (label) | `floor_strike` on the **settled** market | Label-time strike only |
| Official end print (label) | `expiration_value` | Regression target; **never** a feature |
| Official outcome (label) | `result` ∈ {`yes`,`no`} after `status=finalized` | Primary classification target |
| As-of opening ref `S_t` | See §4 | The strike the **decision** is allowed to know |
| Venue proxy `R_t` | Last **completed** Coinbase BTC-USD 1m **close** with period end ≤ `t*` | Feature, panel “current”, last-price control — **not** the `forecast_end` base |

**Side rule:** official correctness is `pred_yes == result`. The **headline** `pred_yes` is the primary classifier (§7). The companion return model’s side is `forecast_end ≥ S_t` and may disagree; both are stored. `forecast_end` is the official as-of ref times the predicted return: `S_t × exp(ŷ_log)` (§7). `R_t` is the venue *current* (panel + features + last-price control), not the conversion base.

**Equality:** `expiration_value == floor_strike` → official YES. Do not invent a tie-break.

**Coinbase** (`https://api.exchange.coinbase.com/products/BTC-USD/candles`, granularity 60) is a venue OHLCV proxy. A probed 15m Coinbase close was near but **not equal** to `expiration_value`. Say “Coinbase proxy,” never “index” or “BRTI.”

**`GET /live_data/events/{event_ticker}`:** public crypto timeseries exists historically; a naive last-60s mean did **not** reconstruct floor/expiration (one probed window: last point equaled `expiration_value`, intra-minute mean did not). **Not BRTI. Not a label. Not a v1 feature.**

**CF REST passthrough** (`/cfbenchmarks/...`) requires Kalshi API credentials. Out of scope.

---

## 3. Forecast clock (frozen initial)

All times UTC. `open` / `close` = that market’s `open_time` / `close_time`.

| Mark | Instant | Meaning |
|---|---|---|
| Open | `open` | Window starts. Initialized markets probed with `floor_strike=null`. |
| **Decision `t*`** | **`open + 30s`** | **Only** as-of cutoff for features and `S_t`. Data arriving after `t*` is unused, even if still before the deadline. |
| **Deadline** | **`open + 60s`** | Last legal emit (`t_pub`) for compute/IO. Not an extra data-wait window. |
| Publish `t_pub` | `t* ≤ t_pub ≤ deadline` | Stored. Payload frozen at emit. |
| Miss | emit missing, `t_pub > deadline`, or required as-of fields absent **at `t*`** | `missed_deadline` or the skip reason. **No backfill.** |

**Scoring lead:** the frozen initial only (about 14.5 minutes to scheduled close). Stored `time_left = close_time − t*`. `can_close_early=true` → use the market’s `close_time` as known at `t*`, not a hard-coded +15m.

**Later updates** (T+1m, T+5m, T+10m, …): optional later, **separate** `forecast_id` / lead bucket. They must not mutate the initial row. They are **not** the headline metric.

**1m bars:** include a bar iff **period end ≤ `t*`**. `t_pub` does not enlarge the bar set. Coinbase exchange candles are labeled at **period start** `T` covering `[T, T+60)`, closed at `T+60`.

- Last legal bar at `t*`: the bar that **ends at `open`** (start `open−60s`).
- **Current open minute** `[open, open+60)` ends at `open+60s` → **excluded** from the initial.
- No 15m (or “full window”) bar of the current market.

**Replay assumption (disclosed):** in historical replay, a completed bar is treated as available at its period end. That is **not** a claim that a live HTTP GET succeeded at that instant. Live emit must log the GET time. If the required closed bars are absent at `t*` → skip `missing_underlying`, not a fabricated close.

**No “full market data”:** features may not include any print, candle, or metadata whose event time is after `t*`.

**Historical tape (optional pressure):** public `GET /markets/trades` or `/historical/trades` for the prior ticker (and the current ticker if any prints exist), keep rows with `created_time ≤ t*` and a known `taker_outcome_side`. Page with backoff; persist raw pages. Do **not** paste live book snapshots, the ~20 local `state/snapshots/` files, or post-`t*` trades into history. Unknown aggressor is dropped, not guessed. Tape is not a profit fill tape.

---

## 4. As-of opening ref `S_t` (no hindsight floor)

The settled object’s `floor_strike` is the **label** strike. It is **not** automatically a `t*` feature.

Probed (2026-11-05/06, public GET): prior `expiration_value` chained to the next market’s `floor_strike` on 39/39 consecutive pairs in a 40-row page; `settlement_ts` lagged close by about **2–7 seconds**.

### Allowed `S_t` (observed-arrival — default score)

Cutoff is **`t*`**, not `t_pub`. Use the first that exists **as of `t*`**:

1. Previous same-series official `expiration_value` whose `settlement_ts ≤ t*`.
2. **Live only:** `floor_strike` on the **current** market if a GET **started at or before `t*`** returned a finite value. Store the raw envelope and the request timestamp. A GET started after `t*` cannot supply `S_t` for the initial.

Otherwise: skip `insufficient_opening_ref`. Do not score official YES/NO for that row. Waiting until +59s for a late `settlement_ts` is backfill and is forbidden.

### Forbidden

- Filling `S_t` from the current market’s **eventual** settled `floor_strike` without an as-of observation.
- Using a prior `expiration_value` before that market’s `settlement_ts`.
- Treating event-time (`close_time`, candle end, `open_time`) as proof a metadata field had arrived.

### Diagnostics (not features, not labels)

- Chain rate: eventual `floor_strike` vs as-of prior print (expect near 1.0; breaks are reported).
- Sensitivity (optional, labeled `replay_assumption=prior_print_by_tstar`): assume prior print is visible by `t*` whenever `settlement_ts` is within 30s after prior close. **Not** the headline universe.

`result` / `expiration_value` of the **current** window are labels after `settlement_ts`. Never inputs.

---

## 5. Dataset inventory (after plan approval — not this commit)

**Host:** `https://api.elections.kalshi.com/trade-api/v2`  
**Cutoff (probed, moves):** `GET /historical/cutoff` → `market_settled_ts` and `trades_created_ts` were `2026-09-06T00:00:00Z` on 2026-11-05/06.

| Tier | Path |
|---|---|
| Live settled | `GET /markets?series_ticker=KXBTC15M&status=settled&limit=1000` + cursor |
| Archived | `GET /historical/markets?series_ticker=KXBTC15M&limit=1000` + cursor |
| One market | `GET /markets/{ticker}` or `GET /historical/markets/{ticker}` |
| Trades (optional pressure) | live `/markets/trades` or `/historical/trades` with `ticker`, time bounds, `limit` |
| Coinbase 1m | public exchange candles, chunked ranges |

Historical `/historical/markets` has **no** timestamp filter (series + cursor). Live settled may use `min_settled_ts` / `max_settled_ts` (mutually exclusive with other timestamp filters).

**Builder rules (when implemented):**

- Cursor until empty. Dedup by `ticker`.
- Persist raw JSON pages + request URL + response time + HTTP status (provenance).
- 429: exponential backoff, no penalty assumed; checkpoint cursor; resume later.
- Bounded concurrency. **This spec commit does not start that download.**
- Cache is a content-addressed raw store, not a mutated feature store.

**Completeness (required before any fit):**

- Expected 15-minute grid from first to last `close_time` in the pull.
- Count missing buckets, duplicate tickers, empty/`void` results, missing prints, `strike_type` mix.
- YES/NO base rate; `settlement_ts − close_time` distribution; chain-break list.
- Survivorship: do not drop early windows after seeing later outcomes. Missing slots stay missing.

**Score universe (BTC v1):** `status=finalized`, `result ∈ {yes,no}`, finite `floor_strike` and `expiration_value`, `strike_type=greater_or_equal`. All other pulled rows are **exclusions** (coverage), not incorrect predictions.

**Extensibility:** `KXETH15M`, `KXSOL15M`, `KXXRP15M`, `KXDOGE15M`, `KXBNB15M` share `frequency=fifteen_min` and `CRYPTO15M-bulk-2026-04-20`. Coinbase `ETH-USD`, `SOL-USD`, `XRP-USD`, `DOGE-USD`, `BNB-USD` returned 200 in a probe. **Do not train them in v1.** Same recipe later, per-series inventory first.

---

## 6. Features (normalized shape, as-of `t*`)

Philosophy: the past may rhyme in **shape**, not in dollar level. That is not an edge claim.

**Train-only scaling:** means, standard deviations, volume medians, and the pattern library are fit on the **current train fold only** (walk-forward: only the past). Apply frozen to val/holdout.

### v1 vector (same for classifier, pattern challenger, and return regression)

From Coinbase 1m bars with period end ≤ `t*`:

| Group | Definition |
|---|---|
| Multi-window log returns | `log(c_t / c_{t−h})` for `h ∈ {1,4,16,96}` closed bars |
| Vol-scaled momentum | those returns ÷ recent vol (e.g. std of last 16 closed 1m log returns); ε-guard |
| Relative volume | last closed bar volume ÷ train-defined median of prior 96 closed volumes |
| Normalized range / path | `(high−low)/close`; ATR-style mean range / close over 16 bars; upper wick / range; lower wick / range; `(close−low)/(high−low)` on the last closed bar |
| Last-10 official | counts and median residual `(expiration − floor)` of up to 10 prior same-series finalized markets with `settlement_ts ≤ t*` — **not** `close_time < open` |
| Point-in-time pressure | optional: size-weighted known-aggressor imbalance on the **prior** ticker (and current ticker if any) with `created_time ≤ t*`; unknown aggressor excluded; then z-scored with train stats |

**Not in v1:** raw USD levels; “nearest $76,014” neighbors; historical L2 or invented depth; 1m bid/ask highs as “spread” unless explicitly named `spread_proxy_1m` and ablated; macro calendar; event `live_data`; current-window path; `expiration_value` / terminal contract price of the current market.

**Degrade:** missing group → zero + `missing_<group>=1` if the core (opening ref + at least the 16-bar return/vol block) exists; else skip (`missing_underlying`, `insufficient_history`, `insufficient_opening_ref`). Never invent a side or a calibrated percent.

**Last-10 leakage fix:** existing open-exit `lean.py` uses `close_time < open`. V3 must not copy that. At `t* = open+30s`, the just-closed window is usually eligible (probed settle lag 2–7s) **only if** its `settlement_ts ≤ t*`. If not, it is out. Record which tickers entered.

---

## 7. Models

One feature vector. Parameters chosen on **train + validation only**.

| ID | What | Output | Role |
|---|---|---|---|
| **A (v1 primary)** | L2-regularized **logistic** on the shape vector, implemented in **numpy** (IRLS / iteratively reweighted least squares). scikit-learn is not required for v1. | `p_yes` (uncalibrated), `pred_yes = 1{p_yes ≥ 0.5}` | Headline class |
| **A-ret (companion)** | L2 **Ridge** (numpy) trained on official log-return `y = log(expiration_value / floor_strike)` using **label-time** prints only for `y`. At decision, apply to as-of `S_t`. | `ŷ_log`; `forecast_end = S_t × exp(ŷ_log)` | Secondary price |
| **B (challenger)** | Train-only kNN in **z-scored** feature space (`k=25`, Euclidean, unweighted majority). Distance weights are a validation-only ablation. | vote `pred_yes`; `p_yes =` yes-neighbor fraction (uncalibrated); `forecast_end = S_t × exp(median neighbor official log-return)` | Pattern-rhyme baseline |
| **C controls** | Majority class (train prior); last-10 majority (`settlement_ts ≤ t*`, tie → skip); **no-change** `ŷ_log=0` → `forecast_end=S_t`, side YES (equality rule); **last-price** `forecast_end=R_t`, side `R_t ≥ S_t` | — | Always reported on the same scored rows |

**Headline `pred_yes` for A** is the logistic class, even if `forecast_end ≥ S_t` disagrees. Store both. **B** uses its vote as headline for the B column.

**Pattern match must not include:** the neighbor’s forward 15m path; any bar ending after that neighbor’s `t*`; val/holdout templates; raw price level.

**Nearby-window purge (B):** drop neighbors with `open ∈ (t* − 96m, t*]`. Last-1 / last-10 remain **named** controls so kNN cannot silently become “copy the last window.”

**Regularization:** one `λ` (A) and one `λ` (A-ret) picked by validation log-loss (A) / MAE (A-ret). Feature groups added on validation only (ablation table). **One** lock, then **one** holdout pass.

**`p_yes`:** labeled `calibration=uncalibrated` until a written validation note accepts a 10-bin reliability diagram on the **validation** fold. There is no numeric ECE “pass” baked in. The screen must say uncalibrated until that note exists. Do not print “80% confidence.” Holdout must not be used to decide calibration.

80–90% accuracy is an **aspirational reference line** on the eval chart. It is not a pass condition and not a reason to retune the holdout.

---

## 8. Splits, purge, walk-forward

Unit = one 15m market in the score universe that has a frozen initial (or an explicit miss, which counts in coverage only).

- Sort by `close_time` ascending.
- **Train** first 70%, **validation** next 15%, **holdout** last 15% of score-universe rows.
- Holdout is **untouched** until the model and scalers are locked. No peeking, no re-cut.
- **Walk-forward inside train+val only:** expanding origin, test slices of 7 calendar days, embargo **≥ 96m + 15m** after the last training close.
- Scalers / kNN library / `λ` refit only on that fold’s training past.

**Leakage tests (job fails if any fail):**

1. Current `expiration_value` / `result` / eventual `floor_strike` absent from the feature vector.
2. Last-10 membership uses `settlement_ts ≤ t*`, not `close_time < open`.
3. Every bar has period end ≤ `t*`.
4. Label permutation on train → holdout accuracy ~ chance (within a frozen band of majority ± 3 pp).
5. No random (i.i.d.) split is used for the reported number.

---

## 9. Metrics

**Headline universe:** holdout rows with a frozen initial and official `result`. Misses/skips are **coverage**, not scored as wrong.

**Primary**

- Accuracy of `pred_yes` vs `result`
- Wilson 95% interval (n = scored holdout)
- Confusion matrix
- Coverage = scored / (scored + skips + misses); skip-reason histogram
- Vs 50%, vs train-majority, vs last-10 (same rows where last-10 exists), vs same-timestamp contract implied **only if** a quote was **observed at or before `t*`** (historical open book is usually missing → that baseline is omitted, not padded)
- Class imbalance (YES rate)
- If `p_yes` present: Brier, log-loss, reliability bins — still tagged uncalibrated unless §7 says otherwise

**Secondary**

- End-price MAE and bias of `forecast_end` vs official `expiration_value`
- Same vs no-change (`S_t`) and vs last-price (`R_t`)

**Also report, never as the claim:** train acc, val acc, walk-forward OOS, “all scored history.”  
**By chunk:** UTC month and a frozen vol-regime split (train 16-bar vol tertiles).  
**Not a metric:** paper or hypothetical trading P&L.

---

## 10. Row contract and artifacts (when built)

Every prediction row stores at least:

`model_version`, `feature_spec_hash`, `dataset_cutoff_id`, `ticker`, `open_time`, `close_time`, `t_star`, `t_pub`, `lead_bucket=initial`, `S_t` + `S_t_source`, `R_t` + candle end, `pred_yes`, `p_yes` + `calibration`, `forecast_end`, `ŷ_log`, skip/miss reason or null, replay label (`observed_arrival` | `replay_assumption=…`), raw-input provenance (payload hashes or cache keys), official `floor_strike` / `expiration_value` / `result` / `settlement_ts` **after** settle (label block, separate from features).

On-disk default (later): `$KXBTC15M_V3_STATE_DIR` or `var/v3/` → `raw/`, `inventory.json`, `predictions.csv`, `metrics.json`. Never under `personal-finance/kalshi-paper` or the openexit dir. Old ledgers never written.

---

## 11. Evaluation interface (proposed, not built)

**Phase 1 (this spec’s product):** offline historical evaluation + a **local read-only** results screen that **only** reads those artifacts. No server on the public internet. No background browser job. No fake stream.

**Phase 2 (optional, later):** on-demand CLI that, if invoked during `[open, open+60s]`, emits one frozen initial. Not promised as an always-on or offline-page side effect.

| Surface | Rule |
|---|---|
| Current-market panel | Show opening `S_t`, current `R_t`, frozen `forecast_end`, official result (if settled), time left, as-of inputs — **only** if a real as-of snapshot for this window exists. Else **unavailable**. |
| Eval section | Holdout accuracy vs 80% and 90% **lines**; coverage; skips; baselines; imbalance; Brier if present; out-of-time chunk curve; confusion; per-market table (predicted / actual / correct / `|forecast_end − expiration_value|` / timestamps / `model_version`); download of the prediction file |
| Empty / untrained | Copy: **not trained** / **no evaluation yet**. No 0%, no 80%, no dummy rows |

The current-market view and the historical eval are **not** an auto-updating live stream unless a later authorized runner exists. This spec does not authorize that runner.

---

## 12. Architecture (later implementation — not this commit)

```
inventory (public GET, cached raw)
  → asof feature builder (t*, completed bars only)
  → split + scalers (train only)
  → A logistic + A-ret Ridge + B kNN + C controls
  → lock → holdout once
  → metrics.json + predictions.csv
  → local read-only screen
```

Units (single purpose): `inventory`, `asof`, `features`, `split`, `models`, `metrics`, `report`. Reuse `schema.unwrap_*` and `clock.parse_utc` from the existing tree. Do not import open-exit `lean.py` for last-10.

---

## 13. Acceptance criteria (for the future implementation)

1. Inventory reports grid holes, exclusions, base rate, chain breaks; N is measured, not guessed.
2. A synthetic fixture with a bar ending after `t*` is dropped; a test fails if it appears in the vector.
3. A fixture whose only `floor_strike` is the settled eventual value, with no prior print whose `settlement_ts ≤ t*`, is `insufficient_opening_ref`. A print that arrives after `t*` but before the deadline must not create `S_t`.
4. Last-10 fixture: `close_time < open` but `settlement_ts > t*` → market **excluded** from last-10.
5. Emit after `open+60s` → `missed_deadline`; no backfilled initial.
6. Updating a T+1m row does not change the initial row’s `pred_yes` / `forecast_end` / `t_pub`.
7. Holdout metrics appear only after a lock file; before that the screen is **not trained**.
8. Old ledger files’ mtime/hash unchanged by V3 commands.
9. No order/account paths; client keeps those fragments forbidden.
10. Headline table includes A, B, and C on the same scored holdout rows, plus Wilson and coverage.

---

## 14. Test plan (when implementing)

| Layer | Tests |
|---|---|
| Clock | `t*` / deadline vs sample `open_time`; early close uses live `close_time` |
| As-of | candle inclusion; `S_t` sources; forbidden eventual floor; `settlement_ts` last-10 |
| Inventory | cursor stub pages, dedup, grid hole, exclusion reasons |
| Features | no raw USD in the vector; train-only scaler does not see holdout |
| Models | A vs B vs C on a tiny fixture; purge drops overlapping neighbors |
| Metrics | skip ≠ error; Wilson on a known n; empty report has no numeric accuracy |
| Isolation | refuse write under personal-finance / openexit paths |
| Leakage | the five checks in §8 |

Live HTTP in tests: bounded optional smoke only, never a training run.

---

## 15. Known limitations

- First-minute forecast has **no** in-window 1m bar; it is a pre-open shape call.
- Coinbase ≠ CF; residual error vs `expiration_value` is expected.
- Historical L2 does not exist; market-implied baseline will often be absent.
- Bar-available-at-close is a replay assumption, not a logged live arrival.
- `floor_strike` publish at the first millisecond of `open` was not sampled; default `S_t` is the prior official print after `settlement_ts`.
- Pattern similarity can look convincing and still be chance; no edge is assumed.
- Public unauth GET rate limits are not a documented Basic-tier token budget; backoff is required.
- Contract-terms PDF returned HTTP 500 during research; `rules_primary` on the market is the rule used here.
- 80–90% at a 14.5-minute lead may not be achievable; the product is an honest score, not that number.

---

## 16. Sources (research, not training data)

- Kalshi: [Historical data](https://docs.kalshi.com/getting_started/historical_data), [Market lifecycle](https://docs.kalshi.com/getting_started/market_lifecycle), [Market settlement](https://docs.kalshi.com/getting_started/market_settlement), [Crypto help](https://help.kalshi.com/en/articles/13823838-crypto-markets), [Pagination](https://docs.kalshi.com/getting_started/pagination), [Rate limits](https://docs.kalshi.com/getting_started/rate_limits) (authenticated tiers), [CF passthrough](https://docs.kalshi.com/cfbenchmarks/rest-passthrough.md) (auth — unused).
- Series / markets / cutoff / trades: public GET `https://api.elections.kalshi.com/trade-api/v2` (probed 2026-11-05–06).
- Coinbase exchange public candles.
- Attached research note: `history-research_68a0.md` (availability matrix; last-10 `close_time` pitfall).
- This repo: `src/kxbtc15m/openexit/lean.py` (incorrect eligibility for V3), `schema.py`, `clock.py`.

---

## 17. After this spec is accepted

1. User reviews **this file**.
2. Writing-plans produces an implementation plan (TDD, inventory first, no holdout peek).
3. Then implementation. Not before.

**Locked choices (not left open):** `t* = open+30s` is the data cutoff; deadline `+60s` is emit-only; observed-arrival `S_t` as of `t*`; `forecast_end = S_t × exp(ŷ_log)`; 96m lookback; embargo 96m+15m; 70/15/15; A = numpy L2 logistic; A-ret = numpy Ridge on official log-return; B = k=25 purged kNN; no-change vs last-price are distinct controls; macro off; BTC-only score; Phase 1 = offline eval + local read-only screen.
