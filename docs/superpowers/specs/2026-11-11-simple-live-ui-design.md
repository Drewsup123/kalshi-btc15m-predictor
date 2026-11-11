# Simple live UI + `v3-live` (design)

Read-only KXBTC15M preview hero for `results.html`, plus a single-process live refresher. Public Kalshi GET + Coinbase public candles only. No orders, auth, or credentials.

## Goals

1. Simple hero at the top of `results.html` for the **current** 15-minute market.
2. `v3-live`: loop refresh + serve state dir on `127.0.0.1:43147` in one process.
3. Fix direction vs predicted-end contradiction by making the hero classifier-consistent.
4. Move all existing in-depth panels under a **Details** heading (substance unchanged).
5. Live append-only call log with settled scoring; show % correct on past/scored surfaces.
6. Windows support: document `tzdata`; `v3-live` works on PowerShell and Linux.

## Hero (current market)

Shown fields (all from `preview.json` / model output — never invented):

| Field | Source |
|---|---|
| Ticker | Kalshi open market |
| Window | `open_denver` / `close_denver` (America/Denver) |
| Start price `S_t` | Opening ref |
| Live BTC | Coinbase last / `R_t` |
| Change since open | `R_t − S_t` |
| Countdown | `close_time − now` (JS ticks; server refreshes clock) |
| Call | Classifier `pred_yes`: YES→**UP**, NO→**DOWN** |
| Confidence % | Call-side probability (see below) |
| Confidence label | Low / Medium / High |
| Why | 1–2 sentences from features / prices |
| Historical accuracy | Sweep/metrics at this family + decision offset |
| Stale badge | Set when last refresh failed or age exceeds threshold |

Below hero: small **Next market** pre-open card. Then **Recent calls** strip (last 10–20 scored live/replay calls with ✓/✗ and running %). Then **Details** (existing content).

### Confidence mapping

`p_call = p_yes` when call is UP/yes; else `1 − p_yes`.

`confidence_pct = round(100 × p_call)` (integer percent).

| Label | Rule |
|---|---|
| Low | `confidence_pct < 55` |
| Medium | `55 ≤ confidence_pct < 65` |
| High | `confidence_pct ≥ 65` |

If `p_yes` is missing, confidence is unavailable (em dash / no label) — never fabricated.

### Why-text rules

Build from available observed fields only:

1. Always include dollar change vs open and whole minutes left when both are known.
2. If `logret_1` (1-minute log return) is present and |logret_1| ≥ 1e-5, add momentum “up”/“down”.
3. If last-10 majority exists and is not a tie, optionally add a short clause.
4. Cap at two sentences. No invented magnitudes.

### Direction / end-price consistency

Hero direction and confidence come **only** from the chosen classifier (`pred_yes` / `p_yes`).

Displayed predicted end price:

- **Show** only when `(forecast_end ≥ S_t) == (pred_yes == "yes")`.
- Otherwise **hide** the end-price figure on the hero (details may still show raw fields labeled as last-price proxy).

### Historical accuracy at decision time

Lookup from sweep holdout rows for matching `family` + `offset_s` (else nearest documented last-price-by-offset / Phase-1 family metrics). Display as `accuracy` with `n_scored` and coverage when present. Separate from live track-record %.

## Recent calls + % correct

Wherever past/scored markets appear (latest scored window, recent strip, holdout table summary):

- Format: `"{k} of {n} correct ({pct}%)"` with integer pct = `round(100 * k / n)` when `n > 0`.
- Never show a % when `n == 0`.

**Recent calls strip:** last 10–20 settled scored calls (prefer live track; fall back to holdout/replay tail), each UP/DOWN vs actual with ✓/✗, plus running %.

## Live track record (`live_calls.jsonl`)

Append-only JSONL in the state dir. On each successful `v3-live` / preview refresh:

1. If current card has a frozen call (`ticker`, `pred_yes` in {yes,no}, `decision_offset_s`, `prediction_asof`), append **once** per `(ticker, decision_offset_s)` — never edit prior lines.
2. When Kalshi settled results are available for that ticker, set `result` / `correct` on a **new score line or in-memory join** without rewriting the frozen call fields. Implementation: keep frozen call immutable; scoring reads settled markets and computes correctness at display time, optionally writing `live_scores.json` summary derived from calls+settlements.

Display separately:

- Live track: all-time and today (America/Denver day) `%` + counts.
- Historical backtest: existing sweep/metrics numbers.

## `v3-live`

- CLI: `v3-live [--state-dir] [--interval 20] [--port 43147]`
- Same process: background `ThreadingHTTPServer` on `127.0.0.1` serving the state directory; foreground loop every ~15–30s calls `run_preview` (public GETs), records calls, rewrites `preview.json` / `results.html`.
- On network errors: keep last good files; set `preview.stale = true` / `stale_reason`; page shows **stale** badge.
- Market rollover: next loop’s `fetch_open_and_next` selects the new open market; hero JS follows `preview.json` ticker changes without full reload.
- Windows + Linux; document `pip install tzdata` for zoneinfo on Windows.

## Tests

- Confidence % and Low/Medium/High thresholds
- Why-text generation from features
- Direction / end-price agree vs hide
- Rollover offset / current-ticker switch helpers
- Live-call append-once, settle scoring, % math (`k of n`)
- Screen contains hero + Details; existing untrained/unavailable behavior preserved

## Out of scope

Orders, auth, credentials, rewriting history, cloud scheduling, external CDNs.
