# KXBTC15M personal paper simulator

Standalone **paper-only** Kalshi `KXBTC15M` (BTC 15-minute up/down) simulator. It reads **public production GETs** only. No order endpoints, credentials, auth, deposits, or live/demo trades.

This tree ships **two isolated paper books**:

| Strategy | Model | Ledger file | Default state dir | Starter |
|---|---|---|---|---|
| Original baseline (frozen) | `exp-baseline-v1@2026-11-05` | `ledger.sqlite` | `~/.local/share/kxbtc15m-paper` or `KXBTC15M_STATE_DIR` | `cycle` / `status` |
| Open-and-watch (second) | `exp-open-exit-v1-risk10@2026-11-05` (prior rows: `exp-open-exit-v1@2026-11-05`) | `openexit.sqlite` | `~/.local/share/kxbtc15m-paper-openexit` or `KXBTC15M_OPENEXIT_STATE_DIR` | `run` / `watch` / `report` |

Baseline **rules** and `model_version` (`exp-baseline-v1@2026-11-05`) stay at **$1 / $5**. Software **2.2.0** is the open-exit risk-regime change plus the earlier settlement unwrap. Opening an existing `openexit.sqlite` stamps `risk_regime=openexit-risk10-nocap@2026-11-05` and does **not** reset cash or realized P&L. Do not reset, migrate, or rewrite the original ledger. The parent-reported book at `/workspace/personal-finance/kalshi-paper/state/ledger.sqlite` may exist on the parent machine. Tests must not require it to be absent; they use isolated fixtures and only fingerprint that path read-only. Never reset or rewrite it.

This is a **build**. Copy the `tar.gz` artifact onto the Linux computer that will run it. The parent executor deploys the artifact; it does not clone this repo. Shipping the code does **not** mean the parent runtime is deployed.

## v2.1 atomic deploy (baseline `cycle` only)

Parent: extract into a **new** directory. Point the existing `cycle` job at the new executable. Leave the original ledger path unchanged.

Artifact: `kxbtc15m-paper-v2.1.tar.gz`  
SHA256: `docs/artifact-v2.1.sha256` (hash of the tarball itself; do not expect that file to contain its own digest).

```bash
# 1. extract beside the running v2 tree — do not overwrite it in place
mkdir -p "$HOME/kxbtc15m-paper-v2.1"
tar -xzf kxbtc15m-paper-v2.1.tar.gz -C "$HOME/kxbtc15m-paper-v2.1" --strip-components=1
chmod +x "$HOME/kxbtc15m-paper-v2.1/kxbtc15m"

# 2. same ledger the parent already uses (do not copy, reset, or migrate)
export KXBTC15M_STATE_DIR="${KXBTC15M_STATE_DIR:-$HOME/.local/share/kxbtc15m-paper}"
# parent-reported book, if that is the live path:
# export KXBTC15M_STATE_DIR=/workspace/personal-finance/kalshi-paper/state

# 3. one-shot check, then switch only the cycle executable in cron/systemd
"$HOME/kxbtc15m-paper-v2.1/kxbtc15m" status --state-dir "$KXBTC15M_STATE_DIR"
"$HOME/kxbtc15m-paper-v2.1/kxbtc15m" cycle --state-dir "$KXBTC15M_STATE_DIR"
```

A wrapped official YES on a pending paper NO of 99¢ inclusive realizes **−$0.99**. `observed_at` is the run clock (UTC + America/Denver), not `close_time`. `software_version` is `2.1.0`; `model_version` stays `exp-baseline-v1@2026-11-05`.

Open-exit watchers already on v2 keep using their own tree and `openexit.sqlite`. This v2.1 tree still contains `run`/`watch`/`report`.

## v2.2 open-exit risk ($10, no daily cap)

Second book only. Entry debit + reserved exit fee ≤ **$10**. **No** Denver-day downside cap. Still one pending. Still bounded by cash on the existing virtual book (no borrow, reset, or top-up). Lean / first-look / tape / exits unchanged.

**Preserve history.** Parent-reported open-exit book at restart should stay **cash 9965¢ / realized −35¢ / flat**. Baseline stays **9901¢ / realized −99¢**. Migration writes meta + one `risk_migration` event; it does not rewrite settlements.

Artifact: `kxbtc15m-paper-v2.2.tar.gz`  
SHA256: `docs/artifact-v2.2.sha256`

Parent replaces the **singleton watcher** (do not start a second). Example — parent runs this, not this cloud session:

```bash
mkdir -p /workspace/personal-finance/kalshi-paper/app-v2.2
tar -xzf kxbtc15m-paper-v2.2.tar.gz -C /workspace/personal-finance/kalshi-paper/app-v2.2 --strip-components=1
chmod +x /workspace/personal-finance/kalshi-paper/app-v2.2/kxbtc15m

# 1) confirm the live book (read-only)
/workspace/personal-finance/kalshi-paper/app-v2.2/kxbtc15m report \
  --state-dir /workspace/var/openexit \
  --baseline-state-dir /workspace/personal-finance/kalshi-paper/state

# 2) stop the current singleton only (exact PID from watch.pid, e.g. 2477494)
kill -TERM "$(cat /workspace/var/openexit/watch.pid)"
# wait until watch.lock is released

# 3) start exactly one new watcher on the SAME state dir (migrates on open)
/workspace/personal-finance/kalshi-paper/app-v2.2/kxbtc15m watch \
  --state-dir /workspace/var/openexit \
  --api-base https://api.elections.kalshi.com/trade-api/v2 --interval 20
```

`report` after restart should show `model_version=exp-open-exit-v1-risk10@2026-11-05`, `risk_regime=openexit-risk10-nocap@2026-11-05`, cash still 9965 if no new fill, realized still −35. Baseline `cycle` remains the v2.1 executable + $1/$5 rules.

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

## Open-and-watch rules (`exp-open-exit-v1-risk10@2026-11-05`)

Independent **$100** starting virtual ledger (existing books keep their cash). Worst-case debit **$10 inclusive** (entry cost + entry fee + reserved exit fee at 50¢). **No** Denver-day downside cap. Bounded by cash on the book. One pending. No martingale. No borrow / reset / top-up.

1. Side = majority of last **10** official finalized `yes`/`no` with `close_time` before this `open_time`. Tie or fewer than 10 → skip.
2. First look must be within **180s** of `open_time`. Later → `missed_open`.
3. Enter at the conservative executable **ask** in **10–90¢**. Ask = max(market ask, `1 −` best opposite bid) when both are valid. Bid for exits = min(market bid, best same-side bid). Small or large ask/book disagreement uses the conservative price; it does **not** systematic-skip at 2¢ (that skip stays on the frozen baseline only).
4. Exits, first match on a live tick: **+8¢** target; after a **+5¢** high, trail **3¢**; **−10¢** book stop; or **5** known-aggressor opposite prints. Ambiguous tape (`taker_outcome_side` missing or disagreeing with `taker_side`) is ignored. Quote exits still run.
5. Else hold to official settlement.

Public tape often has no reliable aggressor. Ambiguous prints never force an exit.

## Install from the artifact (parent)

Python 3.11+ stdlib only. No `pip`. Deploy the tarball, not a git clone.

```bash
# inspect, then extract (v2.1 is the settlement-parser fix; v2 still runs open-exit)
tar -tzf kxbtc15m-paper-v2.1.tar.gz | head
mkdir -p "$HOME/kxbtc15m-paper-v2.1"
tar -xzf kxbtc15m-paper-v2.1.tar.gz -C "$HOME/kxbtc15m-paper-v2.1" --strip-components=1
cd "$HOME/kxbtc15m-paper-v2.1"
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
