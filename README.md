# KXBTC15M personal paper simulator

Standalone **paper-only** Kalshi `KXBTC15M` (BTC 15-minute up/down) simulator. It reads **public production GETs** only. No order endpoints, credentials, auth, deposits, or live/demo trades.

This tree ships **two isolated paper books**:

| Strategy | Model | Ledger file | Default state dir | Starter |
|---|---|---|---|---|
| Original baseline (frozen) | `exp-baseline-v1@2026-11-05` | `ledger.sqlite` | `~/.local/share/kxbtc15m-paper` or `KXBTC15M_STATE_DIR` | `cycle` / `status` |
| Open-and-watch (second) | `exp-open-exit-v1@2026-11-05` | `openexit.sqlite` | `~/.local/share/kxbtc15m-paper-openexit` or `KXBTC15M_OPENEXIT_STATE_DIR` | `run` / `watch` / `report` |

The original baseline is **unchanged**. Do not reset, migrate, or monkeypatch it. The parent-reported book at `/workspace/personal-finance/kalshi-paper/state/ledger.sqlite` is **not** in this environment and is never created here.

This is a **build**. Copy the `tar.gz` artifact onto the Linux computer that will run it. The parent executor deploys the artifact; it does not clone this repo. Shipping the code does **not** mean the parent runtime is deployed.

## Limits (read these)

- Public GETs only. Default API base: `https://api.elections.kalshi.com/trade-api/v2`.
- Fills are simulated at the **current** executable ask (entry) or bid (exit), including depth and official taker fees. Same-instant open/target fills are **not** guaranteed.
- No past fills across poll gaps. A gap is logged; the next tick uses the live book only.
- `observed_at` is the wall clock of that run, never the market `close_time`.
- Official `result` still settles a pending row even if an early bid exit was impossible (no liquidity). Settlement is **not** a sale.
- No invented confidence, win rate, or edge. Rules are frozen on the model version string.
- `https://external-api.kalshi.com/trade-api/v2` returned HTTP 403 on the parent machine. Do not circumvent that.

## Official fee

Kalshi *Fee Schedule for July 2026 — 7.7.26 Update*:

`fees = round up(M × 0.07 × C × P × (1 − P))`

Pinned excerpt: `docs/official/kalshi-fee-schedule-excerpt.md`. Missing excerpt → new entries fail closed.

## Open-and-watch rules (`exp-open-exit-v1@2026-11-05`)

Independent **$100** virtual ledger. Worst-case debit **$1 inclusive** (entry cost + entry fee + reserved exit fee at 50¢). Denver-day downside **$5**, counting pending reserve; wins do not refill. One pending. No martingale.

1. Side = majority of last **10** official finalized `yes`/`no` with `close_time` before this `open_time`. Tie or fewer than 10 → skip.
2. First look must be within **180s** of `open_time`. Later → `missed_open`.
3. Enter at the conservative executable **ask** in **10–90¢**. Ask = max(market ask, `1 −` best opposite bid) when both are valid. Bid for exits = min(market bid, best same-side bid). Small or large ask/book disagreement uses the conservative price; it does **not** systematic-skip at 2¢ (that skip stays on the frozen baseline only).
4. Exits, first match on a live tick: **+8¢** target; after a **+5¢** high, trail **3¢**; **−10¢** book stop; or **5** known-aggressor opposite prints. Ambiguous tape (`taker_outcome_side` missing or disagreeing with `taker_side`) is ignored. Quote exits still run.
5. Else hold to official settlement.

Public tape often has no reliable aggressor. Ambiguous prints never force an exit.

## Install from the artifact (parent)

Python 3.11+ stdlib only. No `pip`. Deploy the tarball, not a git clone.

```bash
# inspect, then extract
tar -tzf kxbtc15m-paper-v2.tar.gz | head
mkdir -p "$HOME/kxbtc15m-paper"
tar -xzf kxbtc15m-paper-v2.tar.gz -C "$HOME/kxbtc15m-paper" --strip-components=1
cd "$HOME/kxbtc15m-paper"
chmod +x kxbtc15m

# --- original baseline (leave the existing ledger alone) ---
export KXBTC15M_STATE_DIR="$HOME/.local/share/kxbtc15m-paper"   # or the parent path you already use
# Parent-reported book (do not reset): /workspace/personal-finance/kalshi-paper/state/ledger.sqlite

# --- second strategy (new isolated book) ---
export KXBTC15M_OPENEXIT_STATE_DIR="$HOME/.local/share/kxbtc15m-paper-openexit"
export KXBTC15M_API_BASE="https://api.elections.kalshi.com/trade-api/v2"
mkdir -p "$KXBTC15M_OPENEXIT_STATE_DIR"

./kxbtc15m run --state-dir "$KXBTC15M_OPENEXIT_STATE_DIR"
./kxbtc15m watch --state-dir "$KXBTC15M_OPENEXIT_STATE_DIR"    # 20s public GET loop; singleton
./kxbtc15m report --state-dir "$KXBTC15M_OPENEXIT_STATE_DIR"   # 15-minute compare; read-only on baseline
./kxbtc15m status --state-dir "$KXBTC15M_STATE_DIR"            # baseline scorecard only
```

`watch` and `report` refuse any state dir under `personal-finance/kalshi-paper` or a directory that already holds a baseline `ledger.sqlite`.

You own cron/`systemd`. Example (not installed by this build):

```cron
# open-exit 20s runner is a long-lived process, not cron:
# systemd: ExecStart=/home/YOU/kxbtc15m-paper/kxbtc15m watch --state-dir /home/YOU/.local/share/kxbtc15m-paper-openexit

# 15-minute compare (does not create the baseline ledger)
3,18,33,48 * * * * KXBTC15M_OPENEXIT_STATE_DIR=$HOME/.local/share/kxbtc15m-paper-openexit $HOME/kxbtc15m-paper/kxbtc15m report --state-dir $HOME/.local/share/kxbtc15m-paper-openexit --baseline-state-dir $HOME/.local/share/kxbtc15m-paper >>$HOME/.local/share/kxbtc15m-paper-openexit/report.log 2>&1
```

## State mapping, PID, log, lock

| Path | Who writes it | Purpose |
|---|---|---|
| `$KXBTC15M_STATE_DIR/ledger.sqlite` | baseline `cycle` only | Original paper book. Do not delete. |
| `$KXBTC15M_STATE_DIR/snapshots/*.json` | baseline `cycle` | Raw public snapshots. |
| `$KXBTC15M_OPENEXIT_STATE_DIR/openexit.sqlite` | `run` / `watch` | Isolated $100 open-exit book. Survives restart. |
| `$KXBTC15M_OPENEXIT_STATE_DIR/watch.lock` | `watch` | `fcntl` exclusive lock. Second `watch` exits. |
| `$KXBTC15M_OPENEXIT_STATE_DIR/watch.pid` | `watch` | PID of the holder. |
| `$KXBTC15M_OPENEXIT_STATE_DIR/watch.log` | `watch` | One line per 20s tick. |
| `$KXBTC15M_OPENEXIT_STATE_DIR/report.log` | your `report` cron | 15-minute compare output. |

Restart: stop the process (lock releases on exit). Start `watch` again against the **same** `--state-dir`. Pending rows, cash, and skips reload from `openexit.sqlite`. No backfilled fills for the downtime gap.

This cloud workspace, if a watch is started here, uses `/workspace/var/openexit` only. That is **not** the parent runtime.

## CLI

```text
kxbtc15m cycle  [--state-dir DIR] [--api-base URL] [--model-version V]
kxbtc15m status [--state-dir DIR]
kxbtc15m run    [--state-dir DIR] [--api-base URL]
kxbtc15m watch  [--state-dir DIR] [--api-base URL] [--interval 20]
kxbtc15m report [--state-dir DIR] [--baseline-state-dir DIR]
```

| Input | Env | Default |
|---|---|---|
| baseline `--state-dir` | `KXBTC15M_STATE_DIR` | `~/.local/share/kxbtc15m-paper` |
| open-exit `--state-dir` | `KXBTC15M_OPENEXIT_STATE_DIR` | `~/.local/share/kxbtc15m-paper-openexit` |
| `--api-base` | `KXBTC15M_API_BASE` | `https://api.elections.kalshi.com/trade-api/v2` |
| report `--baseline-state-dir` | `KXBTC15M_STATE_DIR` | parent path if present, else that env |

`report` never creates a missing baseline `ledger.sqlite`. `observed_at` is the report clock.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Fixtures write only to temp dirs. Live smokes (`tests/test_live_smoke.py`, `tests/test_openexit_live.py`) use public GETs and disposable temp state; set `KXBTC15M_SKIP_LIVE=1` to skip.

Covered: official fees and reserved exit leftover; $1 / $5 / inventory / cash; deterministic timestamps (`observed_at` ≠ `close_time`); live-tape ambiguity ignored; idempotent ticks and restart; invalid quotes and first-look / open timing; target / trail / stop / tape precedence; quantity capped by book depth; process singleton; baseline file hashes unchanged; report isolation.

## Layout

```
src/kxbtc15m/            # stdlib package
src/kxbtc15m/openexit/   # second strategy (does not import cycle)
tests/
docs/superpowers/        # approved specs + plans
docs/official/           # fee excerpt (required)
config.schema.json
config.example.json
kxbtc15m                 # launcher
```

## Readonly note on the parent pending ticker

`KXBTC15M-26NOV051445-45` (parent-reported pending NO×15, 99¢ incl. 7¢, ~12:39 MST) was checked on the official public GET. Envelope is `{market:{…}}`. Inner `status=finalized`, `result=yes`, `settlement_ts=2026-11-05T19:45:02.127035Z`. That is not a live settlement delay at the check time (~50 minutes after close).

Labeled hypotheses only (not a claimed parent-runtime root cause, and **no baseline code change** this pass):

- **H-envelope:** a reader of top-level `result` would miss the wrapped YES.
- **H-inconsistent_book:** baseline skips when market ask and `1−opposite bid` differ by >2¢; live books in this series often sit near that edge.

If that parent row is still pending after 19:45Z, official YES would make the paper NO a realized loss **once the parent process actually reads `result`**.

## Disclaimer

Simulated paper results only. Not a licensed advisor. Past paper P&L is not future results. No calibrated edge.
