# KXBTC15M Paper Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Ship a standalone personal paper-only Kalshi `KXBTC15M` Python CLI that settles, discovers, snapshots, signals, risk-checks, and simulates at most one entry per 15-minute cycle against a restart-safe SQLite ledger.

**Architecture:** Stdlib-only package `kxbtc15m`. Public GETs via `urllib`. Integer-cent ledger. Experimental versioned baseline (momentum with seeded fallback) writes immutable predictions, then either a simulated taker fill or an explicit skip. No order POSTs, no secrets.

**Tech Stack:** Python 3.11+ stdlib (`argparse`, `sqlite3`, `urllib`, `unittest`, `decimal`, `hashlib`, `json`, `zoneinfo`). No pip runtime deps.

## Global Constraints

- Paper only: never call order/portfolio write APIs; no credentials or deposits.
- Public production GETs only; default base `https://api.elections.kalshi.com/trade-api/v2`.
- Do not circumvent HTTP 403 or other network policy blocks.
- Official fee constant `0.07` from `docs/official/kalshi-fee-schedule-excerpt.md` or fail closed.
- $100 start; max $1 inclusive worst-case debit/pick including fees; max $5 Denver-day downside counting pending and ignoring wins as refill; 1 pending; no martingale.
- Experimental entries only; no invented calibrated probabilities, trained performance, or 75% edge.
- SQLite durable and idempotent; 15-minute buckets; no fabricated backfills.
- Unit fixtures isolated from any intended live ledger path.
- Artifact `tar.gz` under `/opt/cursor/artifacts` excluding `.git` and secrets.
- Included usage only; no other bots; do not publish a repo or create a PR unless asked.

## File map

- Create: `src/kxbtc15m/money.py` — cents / ceil helpers
- Create: `src/kxbtc15m/fees.py` — official quadratic taker fee
- Create: `src/kxbtc15m/clock.py` — 15m buckets + Denver day
- Create: `src/kxbtc15m/quotes.py` — executable ask + skip reasons
- Create: `src/kxbtc15m/signal.py` — momentum + seeded control
- Create: `src/kxbtc15m/risk.py` — size + daily downside + pending
- Create: `src/kxbtc15m/ledger.py` — SQLite schema + idempotent writes
- Create: `src/kxbtc15m/client.py` — public GET client
- Create: `src/kxbtc15m/cycle.py` — orchestrator
- Create: `src/kxbtc15m/report.py` — JSON + readable
- Create: `src/kxbtc15m/config.py` — config load
- Create: `src/kxbtc15m/cli.py`, `__init__.py`, `__main__.py`
- Create: `tests/test_*.py`, `tests/fixtures/*.json`
- Create: `config.schema.json`, `config.example.json`, `README.md`

---

### Task 1: Money and official fees

**Files:**
- Create: `src/kxbtc15m/money.py`
- Create: `src/kxbtc15m/fees.py`
- Test: `tests/test_money.py`, `tests/test_fees.py`

**Interfaces:**
- Produces: `dollars_to_cents_ceil(d) -> int`, `cents_to_dollars(c) -> str`, `taker_fee_cents(contracts: int, price_dollars, multiplier=1, fee_constant=0.07) -> int`, `assert_fee_source_ok(excerpt_text: str) -> None`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_money.py
from kxbtc15m.money import dollars_to_cents_ceil, cents_to_dollars

def test_ceil_fractional_cent():
    assert dollars_to_cents_ceil("0.671") == 68
    assert dollars_to_cents_ceil(0.01) == 1
    assert dollars_to_cents_ceil(1) == 100

def test_cents_format():
    assert cents_to_dollars(10000) == "100.00"
```

```python
# tests/test_fees.py
from decimal import Decimal
from kxbtc15m.fees import taker_fee_cents, assert_fee_source_ok, FEE_CONSTANT

def test_fee_constant_is_official():
    assert FEE_CONSTANT == Decimal("0.07")

def test_mid_price_one_contract_rounds_up():
    # 0.07 * 1 * 0.5 * 0.5 = 0.0175 -> 2 cents
    assert taker_fee_cents(1, Decimal("0.50")) == 2

def test_low_price_rounds_up_to_one_cent():
    # 0.07 * 0.10 * 0.90 = 0.0063 -> 1 cent
    assert taker_fee_cents(1, Decimal("0.10")) == 1

def test_order_total_not_per_contract_then_sum():
    # 0.07 * 2 * 0.10 * 0.90 = 0.0126 -> 2 cents
    assert taker_fee_cents(2, Decimal("0.10")) == 2

def test_missing_excerpt_fails_closed():
    try:
        assert_fee_source_ok("unrelated text")
    except ValueError as e:
        assert "fee" in str(e).lower()
    else:
        raise AssertionError("expected fail closed")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m unittest tests.test_money tests.test_fees -v`  
Expected: FAIL / import errors (modules missing).

- [x] **Step 3: Implement money.py and fees.py** (stdlib Decimal; read excerpt path relative to repo `docs/official/kalshi-fee-schedule-excerpt.md`; require `0.07` and `round up` in the text).

- [x] **Step 4: Re-run tests — Expected: PASS**

- [x] **Step 5: Commit** `feat: integer-cent money and official quadratic taker fee`

---

### Task 2: Quotes, clock, signal, risk

**Files:**
- Create: `src/kxbtc15m/clock.py`, `quotes.py`, `signal.py`, `risk.py`
- Test: `tests/test_quotes.py`, `tests/test_signal.py`, `tests/test_risk.py`

**Interfaces:**
- `bucket_id(close_time) -> str`
- `denver_day(utc_dt) -> date`
- `evaluate_quote(market, book, now, intended_contracts, cfg) -> QuoteDecision`
- `choose_side(market_ticker, last_print, seed, threshold_dollars) -> Signal`
- `size_and_gate(ask, book_size, cash_cents, used_downside_cents, pending_count, cfg) -> RiskDecision`

- [x] **Step 1: Failing tests**

Quote: market YES ask 0.67 + best NO bid 0.33 → executable 0.67; disagree by 0.05 → `inconsistent_book`; ask 1.00 → `invalid_ask`; empty book → `thin_book`; age 31s → `stale_quote`; 30s to close → `near_close`.

Signal: last_print move +40 vs threshold 20 → YES; −40 → NO; +5 → seeded fallback (deterministic for ticker+seed); same seed+ticker always same fallback.

Risk: ask 0.99 + fee 1 cent → C=1 debit 100 allowed (inclusive); ask 0.99 needing 101 → skip `per_pick_cap`; used 400 + debit 101 → `daily_downside_cap`; used 400 + debit 100 allowed; pending_count 1 → `pending_open`; size never increases after a simulated prior loss (same ask yields same C).

- [x] **Step 2: Run — Expected FAIL**

- [x] **Step 3: Implement the four modules**

- [x] **Step 4: Run — Expected PASS**

- [x] **Step 5: Commit** `feat: quote gates, experimental signal, risk caps`

---

### Task 3: Ledger persistence and idempotency

**Files:**
- Create: `src/kxbtc15m/ledger.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- `Ledger(path)` with `init()`, `cash_cents()`, `record_prediction(...)`, `record_skip(...)`, `open_position(...)`, `settle(...)`, `pending()`, `summary(denver_day)`, `event_log()`

- [x] **Step 1: Failing tests** — start 10000 cents; open position debits cash, pending exposure set, realized unchanged; settle win/loss updates realized only; duplicate open/settle no second effect; missing result leaves pending; reopen same path restores cash/pending; prediction timestamp stored and not updated on settle.

- [x] **Step 2: Run — Expected FAIL**

- [x] **Step 3: Implement SQLite schema + unique indexes**

- [x] **Step 4: Run — Expected PASS**

- [x] **Step 5: Commit** `feat: idempotent sqlite paper ledger`

---

### Task 4: Client, cycle orchestrator, report, CLI

**Files:**
- Create: `src/kxbtc15m/client.py`, `cycle.py`, `report.py`, `config.py`, `cli.py`, `__init__.py`, `__main__.py`
- Test: `tests/test_cycle.py`, `tests/test_cli.py`
- Create: `tests/fixtures/open_market.json`, `settled_yes.json`, `settled_no.json`, `orderbook.json`, `series.json`

**Interfaces:**
- `PublicClient.get_json(path)` — GET only; raises `FeedError` on HTTP/JSON errors (including 403)
- `run_cycle(cfg, client, ledger, now) -> Report`
- `format_json(report)`, `format_text(report)`
- CLI `cycle` / `status`

- [x] **Step 1: Failing tests using fixture client (no network)** — full cycle skip on failed feed; entry writes prediction then position; second cycle same bucket no duplicate debit; settle after close from official result; prediction time ≤ close; status does not write; CLI cycle with temp state-dir; smoke ledger path ≠ fixture live path.

- [x] **Step 2: Run — Expected FAIL**

- [x] **Step 3: Implement orchestrator + CLI**

- [x] **Step 4: Run — Expected PASS**

- [x] **Step 5: Commit** `feat: cycle/status CLI with fixture-driven paper loop`

---

### Task 5: Docs, schema, live read-only smoke, artifact

**Files:**
- Create: `README.md`, `config.schema.json`, `config.example.json`
- Test: `tests/test_live_smoke.py` (skips if network/403)

- [x] **Step 1: Write README (install/run, config schema, limitations, fee source, build ≠ deployed)**

- [x] **Step 2: Live smoke GET series/markets/orderbook into temp dir; never default ledger**

- [x] **Step 3: Full unittest suite**

- [x] **Step 4: Pack `/opt/cursor/artifacts/kxbtc15m-paper-v1.tar.gz` excluding `.git`, secrets, `__pycache__`, local ledgers

- [x] **Step 5: Commit** `docs: README, schema, and deployment notes`

---

## Spec coverage check

- Paper-only public GETs, elections default, 403 documented: Tasks 4–5
- Fee official / fail closed: Task 1
- $100 / $1 inclusive / $5 pending-aware daily / 1 pending / no martingale: Task 2–3
- Experimental momentum + seeded, no fake edge: Task 2
- Immutable predictions, official settle, idempotent SQLite: Task 3–4
- Skip reasons, honest cash/pending/realized: Task 2–4
- CLI cycle+status, artifact, tests listed: Task 4–5
