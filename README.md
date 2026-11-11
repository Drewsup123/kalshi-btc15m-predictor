# KXBTC15M predictor (read-only)

Research tool for Kalshi’s **KXBTC15M** 15-minute BTC up/down markets. It **predicts** official YES/NO from public data. It does **not** trade.

- Public Kalshi GET endpoints only (`https://api.elections.kalshi.com/trade-api/v2`)
- Public Coinbase Exchange BTC-USD 1-minute candles as a **venue proxy** (not CF Benchmarks / BRTI)
- **No** order placement, **no** auth, **no** API keys, **no** new accounts
- Order and credential URL paths are refused in code (`/orders`, `/portfolio`, `/api_keys`, …)

An older paper-money simulator also lives in this tree (`cycle` / `watch`). It is isolated, paper-only, and is **not** required to run the V3 predictor. This README is about the read-only predictor.

**Not financial advice. For research only. Accuracy is not profit.** A correct YES/NO call is not a fill, not a fee-adjusted return, and not an edge after costs.

## Requirements

- Python 3.11+
- `numpy` (V3 models)
- `tzdata` (IANA zoneinfo; **required on Windows**, harmless elsewhere — without it `America/Denver` fails under `zoneinfo`)
- Optional: `scikit-learn` (HistGradientBoosting in the strategy sweep; skipped if missing)

No paid services. Generated state (`var/`, `*.sqlite`, candle/market caches) is gitignored.

## Install

```bash
git clone https://github.com/Drewsup123/kalshi-btc15m-predictor.git
cd kalshi-btc15m-predictor
python3 -m pip install numpy tzdata
# optional, for the HGB sweep family only:
python3 -m pip install scikit-learn
chmod +x kxbtc15m
```

Or run without installing the package: the `./kxbtc15m` launcher adds `src/` to `PYTHONPATH`.

### Windows quick-start (PowerShell)

```powershell
cd $HOME\kalshi-btc15m-predictor
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install numpy tzdata
# optional:
.\.venv\Scripts\python.exe -m pip install scikit-learn
.\.venv\Scripts\python.exe kxbtc15m v3-live --state-dir var\v3
# open http://127.0.0.1:43147/results.html
```

`v3-live` refreshes public GETs every ~20s, rewrites `preview.json` / `results.html`, serves the state dir on `127.0.0.1:43147`, and appends frozen hero calls to `live_calls.jsonl` (scored when Kalshi settles).

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Set `KXBTC15M_SKIP_LIVE=1` to skip the two live public-GET smokes. Fixtures write only to temp dirs. V3 tests: `PYTHONPATH=src python3 -m unittest tests.test_v3_function_loader`.

## Run the predictor

State dir defaults to `./var/v3` (or `$KXBTC15M_V3_STATE_DIR`). It must not be an old paper-ledger directory.

```bash
export KXBTC15M_V3_STATE_DIR="${KXBTC15M_V3_STATE_DIR:-$PWD/var/v3}"

# 1) page public settled KXBTC15M + Coinbase 1m history (GET only; slow the first time)
./kxbtc15m v3-inventory --state-dir "$KXBTC15M_V3_STATE_DIR"

# 2) chronological 70/15/15 replay; lock λ on train/val; one holdout pass
./kxbtc15m v3-evaluate  --state-dir "$KXBTC15M_V3_STATE_DIR"

# 3) optional: pre-registered decision-time / Brownian / kNN sweep (select on train/val only)
./kxbtc15m v3-sweep     --state-dir "$KXBTC15M_V3_STATE_DIR"

# 4) refresh current + next-market cards (public GETs, no scheduler)
./kxbtc15m v3-preview   --state-dir "$KXBTC15M_V3_STATE_DIR"

# 5) write results.html
./kxbtc15m v3-screen    --state-dir "$KXBTC15M_V3_STATE_DIR"

# 6) one-command live UI (refresh loop + local server on 127.0.0.1:43147)
./kxbtc15m v3-live      --state-dir "$KXBTC15M_V3_STATE_DIR"
# open http://127.0.0.1:43147/results.html

# optional instead of v3-live: one-shot static view
python3 -m http.server 43147 --bind 127.0.0.1 --directory "$KXBTC15M_V3_STATE_DIR"
```

`v3-preview`, `v3-screen`, and `v3-live` do not place orders. Forecasts are frozen at a decision instant (`t*` = open+30s for Phase 1; later offsets in the sweep). Labels are official Kalshi `result` / `expiration_value`.

### Live hero confidence labels

Call-side probability `p_call` = `p_yes` for UP, else `1 − p_yes`. Displayed as an integer percent.

| Label | Rule |
|---|---|
| Low | confidence &lt; 55% |
| Medium | 55% ≤ confidence &lt; 65% |
| High | confidence ≥ 65% |

The hero direction always comes from the classifier. A predicted end price is shown only when it agrees with that direction; otherwise it is hidden so last-price proxies cannot contradict the call. Historical backtest accuracy at the same family/offset is shown separately from the live track-record %.

## Honest results (already measured)

Replay assumption: `historical_replay` + `prior_print_after_settlement_ts` (event timestamps are not live receipts). Holdout was used once for Phase 1, then reused as **previously viewed** for the 276-variant sweep (`n_fresh` after lock was 5, too small for a new holdout). Wilson intervals are unadjusted for multiple comparisons. Coinbase last price is not the CF settlement.

**Dataset:** 28,385 finalized KXBTC15M windows, closes 2026-01-13 23:00Z → 2026-11-10 06:15Z; 70/15/15 chronological split; holdout **n = 4,259**.

### Phase 1 first-minute models (`t*` = open+30s)

| Model | Accuracy | Wilson 95% | Coverage | End-price MAE | n |
|---|---|---|---|---|---|
| **A logistic (headline)** | **53.7%** | 52.2–55.2% | 100% | 189.49 | 4259 |
| A-ret Ridge side | 51.6% | 50.1–53.1% | 100% | 189.49 | 4259 |
| B purged kNN k=25 | 52.2% | 50.7–53.7% | 100% | 94.83 | 4259 |
| C majority | 50.7% | 49.2–52.2% | 100% | 92.53 | 4259 |
| C last-10 | 48.6% | 46.9–50.4% | 73.9% | 94.79 | 3146 |
| C last-price (`R_t ≥ S_t`) | 54.7% | 53.2–56.2% | 100% | 91.44 | 4259 |

The first-minute classifier does **not** reach 75–90%. Last-price is slightly ahead of model A on this holdout.

### Last-price rule by decision time (same holdout, 100% coverage)

YES iff last completed Coinbase 1m close at that instant ≥ opening ref `S_t`. Brownian CDF at a 0.5 cutoff is the same rule.

| Decision time | Accuracy | Wilson 95% | Coverage | n |
|---|---|---|---|---|
| pre-open | 49.6% | 48.1–51.1% | 100% | 4259 |
| open+30s | 54.7% | 53.2–56.2% | 100% | 4259 |
| +1m | 58.8% | 57.3–60.3% | 100% | 4259 |
| +2m | 63.8% | 62.3–65.2% | 100% | 4259 |
| +5m | 71.0% | 69.6–72.3% | 100% | 4259 |
| +7m | 74.8% | 73.5–76.1% | 100% | 4259 |
| **+10m** | **80.5%** | **79.3–81.7%** | **100%** | 4259 |
| +12m | 86.1% | 85.0–87.1% | 100% | 4259 |
| +14m | 95.0% | 94.3–95.6% | 100% | 4259 |

**75% full-coverage accuracy is reachable around minute 7–10 of the 15-minute window, not in the first minute.** At +7m the last-price rule is 74.8% (interval includes 75%); at +10m it is 80.5%. Selective first-minute filters that hit 75% do so by skipping almost every market (example: +30s, |p−0.5|≥0.35 → 75% accuracy, **0.19% coverage**, n=8). Coverage is never omitted.

Market-implied YES last trade was **not scored** in that sweep (no bulk as-of tape cache; coverage 0). It was not faked.

## Layout

```
src/kxbtc15m/v3/     # read-only replay predictor (numpy)
src/kxbtc15m/        # paper-only simulator (unused for V3 scoring)
tests/
docs/superpowers/    # specs and plans
kxbtc15m             # launcher
```

## Disclaimer

This software is for **research only**. It is **not** financial, investment, or trading advice. Past replay accuracy is not future accuracy and is **not profit**. Official Kalshi settlement uses CF Benchmarks; Coinbase candles are a proxy. Use of Kalshi or Coinbase is subject to their terms. You are responsible for what you do with public data.
