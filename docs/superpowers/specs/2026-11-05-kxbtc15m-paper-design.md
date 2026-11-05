# KXBTC15M personal paper simulator — design of record

**Status:** approved for implementation (user-attached design + 2026-11-05 paper-only 15-minute cycle override).  
**Date:** 2026-11-05  
**Scope:** standalone personal paper-only Kalshi `KXBTC15M` simulator. No live/demo orders, no credentials, no deposits, no other bots, no business repos, no personal account data.

This file is the implementation spec. The attached reviewed design remains the source narrative; where the latest user change conflicts, **this spec wins**.

---

## 1. Goal

A local, restart-safe, dependency-light Python CLI that, on each parent-invoked `cycle`:

1. Settles any pending paper position from the official Kalshi `result` only.
2. Discovers the current `KXBTC15M` window.
3. Snapshots public production quotes + top-of-book.
4. Emits an immutable pre-outcome prediction.
5. Applies risk and quote gates.
6. Books **one honest simulated entry** or records an **explicit skip reason**.
7. Prints JSON + a readable scorecard.

A separate `status` command is read-only.

Parent deploys the artifact on their Linux computer and creates any 15-minute routine. This repo does **not** create cloud schedules, chat pings, or external communications.

## 2. Latest override vs original design

| Original v1 | Override in force |
|---|---|
| Daily chat scorecard only; Phase 0 always-skip / observational | Each cycle updates after that cycle; entry **or** explicit skip |
| Passive baseline | Transparent **experimental** versioned baseline that can make simulated entries |
| Calibrated edge gate required for picks | Do **not** invent calibrated `p_hat`, trained performance, or 75% edge. Experimental entries are **not** model-gated. Later model-gated class is reserved and unused. |
| Intermittent agent polls | 15-minute clock buckets; parent schedules. No fabricated backfilled trades for missed buckets |

## 3. Non-goals

- Real or demo order API calls (`POST /portfolio/orders` or any write).
- API keys, OAuth, deposits, account linking.
- Circumventing `external-api.kalshi.com` 403s or any network policy block.
- Promising minute-exact cadence or every-market coverage.
- Invented settlement results, mark-to-market “profit”, or martingale sizing.
- Other series (ETH, etc.).
- Other bots, publishing a public repo, or contacting people.

## 4. Public data only

**Default API base:** `https://api.elections.kalshi.com/trade-api/v2`  
Documented alternate production host (worked in research and this build). Official recommended host `https://external-api.kalshi.com/trade-api/v2` returned 403 on the parent machine; this environment saw 200. Configurable. Never scrape the UI. Never use demo hosts for fills.

Allowed methods: **GET** of public market-data paths only:

- `GET /series/KXBTC15M`
- `GET /markets?series_ticker=KXBTC15M&…`
- `GET /markets/{ticker}`
- `GET /markets/{ticker}/orderbook`

## 5. Architecture

```
cycle:
  settle pending (official result or keep pending)
  → discover current 15m bucket market
  → snapshot market + book (raw JSON archive)
  → validate quote (else skip with reason)
  → experimental signal (side or skip)
  → risk gate (else skip)
  → simulate taker fill (cash debit, one pending)
status:
  read ledger only
```

Components (one responsibility each): `money`, `fees`, `clock`, `quotes`, `signal`, `risk`, `ledger`, `client`, `cycle`, `report`, `cli`.

## 6. Money and fees

- Paper cash and fees are **integer cents**.
- Contract prices may be deci-cents; **cost is rounded up to the next cent** (conservative).
- Official taker fee, order total, then round up to the next cent:

  `fee_dollars = ceil_cent(0.07 × M × C × P × (1 − P))`

  Source: `docs/official/kalshi-fee-schedule-excerpt.md`. If that excerpt is missing or the constant mismatches, **fail closed** (no new entries).

- Live series `fee_type` must be `quadratic` and multiplier used as returned (default 1). Unknown `fee_type` → skip `unsupported_fee_type`.

- Slippage assumption (visible on every report): fill at the conservative executable ask; **no extra adverse tick**. This is optimistic versus real latency.

## 7. Quote quality

Skip (record reason) when any of:

- feed/HTTP/JSON failure (`failed_feed`)
- market not open/active (`market_closed` / `market_not_open`)
- missing or non-finite bid/ask (`invalid_quote`)
- ask ≤ 0 or ≥ 1 (`invalid_ask`)
- market ask vs book-implied ask (`1 − best_opposite_bid`) differ by more than `ask_epsilon` (default $0.02) (`inconsistent_book`)
- available opposite-side size < intended contracts (`thin_book`); default is skip, do not partial-fill
- snapshot older than 30s at decision time (`stale_quote`)
- fewer than 60s to `close_time` (`near_close`)
- book lists empty (`thin_book`)

Executable ask = **max(market ask, book-implied ask)** when they agree within epsilon (conservative).

Orderbook `orderbook_fp.yes_dollars` / `no_dollars` are **bids**, typically sorted low→high. Best bid = highest price.

## 8. Experimental baseline (versioned)

`model_version` default: `exp-baseline-v1@2026-11-05`  
`entry_class`: `experimental` (this build). `model_gated` is a reserved unused class.

Rules, in order, after quote validation:

1. **Preregistered momentum** using official Kalshi prints only (prior finalized `expiration_value` vs that market’s `floor_strike`, which is CF Benchmarks BRTI — the same spot the contract settles on).  
   - `move = last_expiration − last_floor`  
   - `threshold` default **$20** (frozen).  
   - If `move >= +threshold` → side YES (continuation).  
   - If `move <= −threshold` → side NO.  
   - If `|move| < threshold` or prints missing → fall through.
2. **Deterministic seeded control** — `sha256(f"{seed}:{market_ticker}")` even digest → YES, odd → NO. Default `seed=20261105`. No claimed edge.

Never write a calibrated probability. Optional `p_hat` field stays null for experimental entries. Inputs hash is stored. Predictions are append-only and never rewritten after settlement.

## 9. Risk

| Control | Default |
|---|---|
| Starting cash | $100.00 (10000 cents) |
| Max worst-case debit / pick including fees | **$1.00 inclusive** |
| Max daily downside | **$5.00** America/Denver day |
| Pending positions | **1** |
| Martingale | forbidden — size from the $1 cap and book only |
| Bankroll floor | cash must stay ≥ 0; halt on bug |

**Worst-case debit** = `ceil_cent(ask × C) + fee_cents` (lose case; settlement $0).

**Size:** largest integer `C ≥ 1` such that debit ≤ $1 and book size ≥ C. If C=1 does not fit → skip `per_pick_cap`.

**Daily downside (gains do not refill the budget):**

```
used = sum(realized losses that Denver day) + sum(pending worst-case debit)
if used + new_debit > 500 cents → skip daily_downside_cap
```

Realized wins do **not** reduce `used`. Pending exposure counts now.

If any pending row exists → skip `pending_open` (do not add a second position).

## 10. Ledger (SQLite)

Configurable `state_dir` (env `KXBTC15M_STATE_DIR` or `--state-dir`). Files:

- `ledger.sqlite`
- `snapshots/<utc>_<ticker>.json`
- `config.json` (optional overlay)

Tables: `meta`, `predictions`, `skips`, `positions`, `settlements`, `events`.

Idempotency:

- unique `(cycle_id, market_ticker)` for prediction / skip / new position
- unique `market_ticker` for settlement
- duplicate `cycle` / settle of same market is a no-op (no second debit, no second P&L)

`cycle_id` = the market’s 15-minute `close_time` bucket (`YYYY-MM-DDTHH:MM:00Z`). Missed buckets are **not** invented.

Restart-safe: reopen DB, pending stays pending until official `result` is `yes` or `no`. Missing/empty result → remain pending (`result_not_ready`).

## 11. Settlement

After `close_time`, GET the market. Only `result` in `{yes, no}` on `status` finalized/settled closes the position.

- Win: credit `100 cents × C`; realized P&L = credit − entry_cost_cents − fee_cents
- Loss: credit 0; realized P&L = −(entry_cost_cents + fee_cents)

Do not treat pending cost as realized profit. Reported equity for display = `cash + pending_cost` (capital locked at cost), never pending marked at $1.

## 12. Reports

Every `cycle` and `status` prints:

- JSON object (stdout, first or `--format json`)
- Human-readable block

Fields: cash, pending_exposure (worst-case debit still open), pending_cost, realized_pnl, wins, losses, skips, pending_count, fees_paid, max_drawdown (peak-to-trough of cash+pending_cost after settlements), model_version, last action (entry or skip reason), slippage assumption, data-health, disclaimer.

Win rate = wins / (wins+losses) among **settled picks only**; state the denominator.

## 13. CLI and config

```
python3 -m kxbtc15m cycle [--state-dir DIR] [--api-base URL] [--model-version V]
python3 -m kxbtc15m status [--state-dir DIR]
```

See `config.schema.json`. No secrets schema.

## 14. Testing

Unit fixtures never touch the intended live paper ledger path. Disposable smoke uses a temp dir.

Required tests: fee/cents rounding; inclusive max debit; cash vs pending equity; pending reserve daily limit; duplicate cycle/market/settlement; missing result stays pending; restart persistence; no lookahead (prediction time ≤ close); API errors; smoke isolation.

Live read-only smoke (optional): public GETs only. If a disposable simulated trade is exercised, it must use a temp state dir.

## 15. Runtime honesty

Build ≠ deployed ≠ parent-scheduled. Cadence depends on when parent runs `cycle`. Settlement can lag `close_time`. Latency can stale a quote. Coverage is not exhaustive.

## 16. Disclaimer

Simulated paper results only. Not a licensed advisor. Past paper P&L ≠ future results. No edge is claimed for the experimental baseline.
