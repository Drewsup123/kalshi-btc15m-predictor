# Open-and-Watch Paper Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a second, isolated open-and-watch paper engine (last-10 lean at real ask, proposed dynamic/adverse exits, 20s GET watch, 15-min compare) without changing the original baseline cycle or its ledger.

**Architecture:** New `kxbtc15m.openexit` package. Reuse fees/money/clock/PublicClient only. Unwrap real Kalshi envelopes (`{market:…}`, `{markets:[…]}`). Book-complement quotes (conservative ask/bid) instead of baseline’s 2¢ skip. Separate sqlite + singleton watch lock.

**Tech Stack:** Python 3.11+ stdlib. Unittest. No pip.

## Global Constraints

- Do not modify `cycle.py`, `quotes.py`, `signal.py`, `risk.py`, `ledger.py` behavior; CLI `cycle`/`status` stay baseline.
- Do not create, reset, or write `/workspace/personal-finance/kalshi-paper/state/ledger.sqlite`.
- Paper public GET only; no `/portfolio` or `/orders`.
- Model `exp-open-exit-v1@2026-11-05`; no invented confidence.
- $100 start; $1 inclusive reserve = entry debit + exit-fee reserve; $5 Denver-day pending-aware; 1 pending.
- firstlook ≤ 180s; 10–90¢ band; min 10 history; 5–5 skip; ignore ambiguous aggressors; quote exits kept.
- `observed_at` is wall clock, never future `close_time`.
- Build ≠ parent deployed.

## File map

- Create: `src/kxbtc15m/schema.py` — unwrap market payloads
- Create: `src/kxbtc15m/openexit/*.py` — quotes, lean, tape, exits, risk, ledger, tick, watch, compare, lock
- Modify: `src/kxbtc15m/cli.py` — add `run`/`watch`/`report` only
- Modify: `README.md` — state mapping, PID/log, lock
- Test: `tests/test_openexit_*.py`, keep existing tests green

---

### Task 1: Schema unwrap + book-complement quotes + lean/exits/risk

**Done.** Handle `{market:…}` (live official GET). Quotes: executable ask = max(market, 1−best opposite bid) when both valid; do **not** skip at 2¢ disagreement (use conservative price); skip only missing book/invalid/stale/near_close/closed. Exit bid = min(market bid, best same-side bid). Lean last-10. Exits precedence: target +8¢, trail +5/−3, 5 known opposite prints, −10¢ book. Risk reserves entry+exit fee.

### Task 2: Isolated ledger + tick orchestrator

**Done.** New `openexit.sqlite`. Idempotent ticks, restart, official settlement unwrap, no gap backfill, reduce size to depth (no leftover partial). Never touches baseline path.

### Task 3: CLI run/watch/report + singleton + compare schema

**Done.** `run` = one tick. `watch` = 20s loop, lock file, PID, log. `report` = 15-min JSON+text both strategies; baseline missing → say so; `observed_at` now. `cycle`/`status` unchanged.

### Task 4: README, artifact, this-env watch, live smoke on temp dir

**Done in this pass.** Pack tar.gz without .git/secrets/ledgers. Start watch here on `/workspace/var/openexit` only. Do not claim parent deploy.
