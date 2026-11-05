# KXBTC15M personal paper simulator

Standalone **paper-only** Kalshi `KXBTC15M` (BTC 15-minute up/down) simulator. It reads **public production GETs**, writes an immutable prediction, then either books one **simulated** taker fill or records an explicit skip. Official `result` settles the ledger.

This is a **build**, not a deployed or scheduled runner. After you copy the artifact to the Linux computer that will run it, you create any 15-minute routine. This repo does not place live or demo orders, does not store credentials, and does not contact other systems.

## What a cycle does

`cycle` runs this sequence once:

1. Settle any pending paper position from the official market `result` (`yes`/`no` only). Missing results stay pending.
2. Discover the current open `KXBTC15M` market.
3. Snapshot market quote + order book (raw JSON under the state dir).
4. Validate quote quality (stale, thin, closed, inconsistent book, near close).
5. Experimental signal: preregistered momentum on official Kalshi prints, else deterministic seeded control.
6. Risk: $1 inclusive worst-case debit including fees, $5 Denver-day downside that counts pending and is **not** refilled by wins, one pending position, no martingale.
7. Simulate a taker fill or write a skip reason.
8. Print JSON and a readable scorecard.

`status` is **read-only**. It will not create a ledger and will not settle or trade.

## Limits (read these)

- **Build ≠ deployed ≠ scheduled.** Shipping this code does not start a 15-minute job.
- Cadence is however often you invoke `cycle`. It will not invent trades for missed 15-minute buckets.
- Not minute-exact. Quote age, HTTP latency, and settlement lag after `close_time` are real.
- Fills are simulated at a conservative executable ask. **No extra slippage tick** is added; that is optimistic versus live latency and is printed on every report.
- Experimental baseline **claims no edge**. It does not invent calibrated probabilities, trained performance, or a 75% win rate. `entry_class=experimental` only. `model_gated` is unused.
- Pending cost is locked capital, not realized profit. Equity is cash + pending at cost.
- `https://external-api.kalshi.com/trade-api/v2` returned HTTP 403 on the parent machine (unknown cause). Default base is the documented alternate production host `https://api.elections.kalshi.com/trade-api/v2`. Do not circumvent 403s, challenges, or network policy.

## Official fee source

Kalshi *Fee Schedule for July 2026 — 7.7.26 Update*:

`https://kalshi.com/docs/kalshi-fee-schedule.pdf`

Taker fee used here:

`fees = round up(M × 0.07 × C × P × (1 − P))`

Pinned excerpt: `docs/official/kalshi-fee-schedule-excerpt.md`. If that file is missing or does not contain the official formula, new entries **fail closed**. Live series `KXBTC15M` reported `fee_type=quadratic`, `fee_multiplier=1` in this build session.

## Install on the parent Linux computer

Python 3.11+ stdlib only. No `pip` packages required.

```bash
# from the self-contained artifact (preferred), not a git clone
tar -tzf kxbtc15m-paper-v1.tar.gz | head
mkdir -p "$HOME/kxbtc15m-paper"
tar -xzf kxbtc15m-paper-v1.tar.gz -C "$HOME/kxbtc15m-paper" --strip-components=1
cd "$HOME/kxbtc15m-paper"

# persistent paper ledger — choose this path once and keep using it
export KXBTC15M_STATE_DIR="$HOME/.local/share/kxbtc15m-paper"
export KXBTC15M_API_BASE="https://api.elections.kalshi.com/trade-api/v2"
mkdir -p "$KXBTC15M_STATE_DIR"
# optional overlay (copy example, then leave it in the state dir)
cp config.example.json "$KXBTC15M_STATE_DIR/config.json"

chmod +x kxbtc15m
./kxbtc15m status --state-dir "$KXBTC15M_STATE_DIR"
./kxbtc15m cycle --state-dir "$KXBTC15M_STATE_DIR"
```

Equivalent:

```bash
PYTHONPATH=src python3 -m kxbtc15m cycle --state-dir "$KXBTC15M_STATE_DIR"
PYTHONPATH=src python3 -m kxbtc15m status --state-dir "$KXBTC15M_STATE_DIR"
```

You own any cron/`systemd` timer. Example (not installed by this build):

```cron
# every 15 minutes, plus a small delay for books to appear
3,18,33,48 * * * * KXBTC15M_STATE_DIR=$HOME/.local/share/kxbtc15m-paper $HOME/kxbtc15m-paper/kxbtc15m cycle >>$HOME/.local/share/kxbtc15m-paper/cycle.log 2>&1
```

## CLI

```text
kxbtc15m cycle [--state-dir DIR] [--api-base URL] [--model-version V]
kxbtc15m status [--state-dir DIR]
```

| Input | Env | Default |
|---|---|---|
| `--state-dir` | `KXBTC15M_STATE_DIR` | `~/.local/share/kxbtc15m-paper` |
| `--api-base` | `KXBTC15M_API_BASE` | `https://api.elections.kalshi.com/trade-api/v2` |
| `--model-version` | overlay `config.json` | `exp-baseline-v1@2026-11-05` |

JSON Schema: `config.schema.json`. Overlay file, if used, is `$STATE_DIR/config.json`. There is no secrets schema.

State files: `ledger.sqlite`, `snapshots/*.json`.

## Experimental baseline

`exp-baseline-v1@2026-11-05`

1. Momentum using official Kalshi prints only (prior finalized `expiration_value − floor_strike`, CF Benchmarks BRTI). Frozen threshold **$20**. Continuation: up → YES, down → NO.
2. If the move is below threshold or prints are missing: deterministic `sha256(seed:ticker)` control. Default seed `20261105`.

`p_hat` is always null. Predictions are append-only and are not rewritten at settlement.

## Risk defaults

| Control | Value |
|---|---|
| Starting cash | $100.00 |
| Max worst-case debit / pick (fees in) | $1.00 inclusive |
| Daily downside (Denver) | $5.00; pending counts; wins do not refill |
| Pending positions | 1 |
| Martingale | forbidden |
| Stale quote | skip if snapshot older than 30s |
| Near close | skip if < 60s to `close_time` |

## Tests

From the repo or extracted artifact:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Unit fixtures live under `tests/fixtures/` and write only to temp dirs. They never open the intended starting ledger. Live smoke (`tests/test_live_smoke.py`) uses public GETs and a disposable temp ledger; set `KXBTC15M_SKIP_LIVE=1` to skip it.

Covered: fee/cents rounding, inclusive max debit, cash vs pending equity, pending reserve daily limit, duplicate cycle/market/settlement, missing result stays pending, restart persistence, no lookahead, API errors, CLI isolation.

## Layout

```
src/kxbtc15m/     # stdlib package
tests/            # unittest + fixtures
docs/superpowers/ # approved spec + plan
docs/official/    # fee excerpt (required at runtime)
config.schema.json
config.example.json
kxbtc15m          # launcher
```

## Disclaimer

Simulated paper results only. Not a licensed advisor. Past paper P&L is not future results.
