# Lean-50 paper strategy — WITHDRAWN

**Withdrawn 2026-11-05.** Fixed 50¢ buy / 60¢ sell was an example, not the strategy.  
**Use instead:** `docs/superpowers/specs/2026-11-05-kxbtc15m-open-exit-design.md`

# Lean-50 paper strategy — design for Drew approval (obsolete)

**Status:** withdrawn. Do not implement.  
**Date:** 2026-11-05 (report schema added same day)  
**Hard rules:** paper only. No live/demo orders. No credentials. Public GETs only. Do not change the existing baseline cycle or its ledger. **Do not reset the original paper book.**

This is a **second, isolated** experimental paper strategy beside the unchanged `exp-baseline-v1@2026-11-05` taker-and-hold path.

---

## 1. What Drew is being asked to approve

Add a **separate $100 paper account** that, near each new `KXBTC15M` window:

1. Looks at the last **10 official finalized** public market results (known before the decision).
2. If YES leads, try to **buy YES**; if NO leads, try to **buy NO**.
3. Entry is a **50¢ LIMIT**, never a guaranteed 50¢ fill.
4. After a real simulated fill, arm a **60¢ LIMIT sell** on the same side.
5. If the 60¢ exit never becomes honestly executable, hold to the official `result`.
6. Compare this book to the original baseline book. Do not mix cash.

**Speakable one-liner:** second paper wallet, last-10 winner lean, 50¢ limit in / 60¢ limit out, only if the public book actually shows it, own ledger, original bot untouched.

---

## 2. What stays frozen (baseline)

| Frozen | Path / behavior |
|---|---|
| Original CLI `cycle` / `status` | Exact current behavior |
| Original state dir | Default `~/.local/share/kxbtc15m-paper` / `ledger.sqlite` — **never delete, recreate, or re-seed $100** |
| `exp-baseline-v1@2026-11-05` | Momentum + seeded control, taker-at-ask, hold to settlement |
| Risk on that account | $100 / $1 inclusive / $5 Denver-day / 1 pending |
| First real-paper baseline fill (parent-reported) | ~2026-11-05 **12:39 MST**: **NO**, **15 contracts**, **99¢ inclusive** debit, **7¢ fees**. This workspace does not hold that sqlite and must not invent a replacement. |

Implementation must not open the original ledger for writes. New code lives in new modules and new CLI verbs. Existing tests must still pass unchanged.

---

## 3. Isolation

| | Baseline (unchanged) | Lean-50 (new) |
|---|---|---|
| State dir | `KXBTC15M_STATE_DIR` (existing) | `KXBTC15M_LEAN50_STATE_DIR` default `~/.local/share/kxbtc15m-paper-lean50` |
| Ledger file | `ledger.sqlite` | `lean50.sqlite` in the new dir only |
| Starting cash | $100 (existing history kept) | **new** $100, empty book |
| Model | `exp-baseline-v1@2026-11-05` | `exp-lean50-v1@2026-11-05` |
| Entry class | `experimental` | `experimental` (not `model_gated`) |

Comparison reads **both files read-only**. No shared cash, pending, daily budget, or position row.

Risk on the lean-50 wallet (same numbers, own counters):

- $1 inclusive worst-case debit per position including **both legs’ fees** reserved at arm time
- $5 Denver-day downside: realized losses + reserved/pending exposure; **wins do not refill**
- 1 pending lean-50 position
- no martingale

At 50¢ + taker fee, C=1 is the usual size (~52¢ debit). Size up only if $1 inclusive still holds after entry+exit fee reserve.

---

## 4. “Last 10” and “previous orders” — honest definitions

**Lean signal (frozen):** majority of the last **10 official finalized** `KXBTC15M` markets whose `close_time` is **strictly before** this window’s `open_time`, and whose `result` is `yes` or `no`. That is a **short-horizon outcome trend**, not sentiment and not open interest.

| Case | Action |
|---|---|
| ≥10 finalized, YES count > NO count | side = YES |
| ≥10 finalized, NO count > YES count | side = NO |
| ≥10 finalized, 5–5 tie | **skip** `lean_tie` |
| fewer than 10 finalized known before `open_time` | **skip** `insufficient_history` |
| a listed market has empty/`void` result | drop it; do not invent; may fall into insufficient_history |

**“Previous orders” means:**

1. Official public **settled market outcomes** (the lean input above).
2. **Our** paper orders/fills/skips on this lean-50 ledger (and, for the comparison report only, the baseline ledger).

It does **not** mean other traders’ private working orders. We cannot see those.

**Public trade tape** (`GET /markets/trades?ticker=…`, confirmed HTTP 200 this session, no auth) is a **print log**: price, size, time, taker side. Store it as `public_prints`. Never label it “orders,” “sentiment,” or “open interest.”

**Volume / open interest** (live this session: `volume_fp`, `open_interest_fp` on each market) are stored on every snapshot under those names only. They are **not** the lean input.

---

## 5. 50¢ in / 60¢ out — no invented fills

`50¢` is a **limit price**, not a promise.

### Entry (buy chosen side)

Fill **only** as a simulated **taker** when a **fresh** snapshot (age ≤ 30s, wall clock vs capture time) shows:

- conservative executable **ask ≤ $0.50** (max of market ask and `1 − best opposite bid`, same book-consistency gate as today)
- ask in `(0, 1)`
- opposite-side depth ≥ intended contracts
- market still open and not inside the last 60s before `close_time`

If ask is **below** 50¢, fill at that ask. Record:

- `limit_price = 0.50`
- `fill_price` (actual)
- `improvement_vs_limit_cents` (positive if cheaper than 50¢)

If ask is **above** 50¢: **do not fill**. Arm a working paper bid at 50¢ (intent only).

**Maker / resting 50¢ (default: do not fill).** Quote-touch is not a fill. We have no queue position. A later public print at 50¢ does **not** prove our bid was hit. Default: expire the unfilled 50¢ bid at `close_time` with reason `limit_expired`. Optional later flag `approx_maker_tape` (off) would still be labeled approximate and is **not** recommended for v1.

### Exit (sell same side at 60¢)

Armed only **after** entry is filled. Concurrent means “working immediately after fill,” not “filled in the same instant.”

Fill the exit only as a simulated **taker sell** when a fresh snapshot shows conservative executable **bid ≥ $0.60** and depth ≥ contracts.

If bid is **above** 60¢, fill at that bid and record improvement vs 60¢. If bid stays below 60¢ until close: **no fake 60¢ exit** — settle the official `yes`/`no` like the baseline.

### Fees (both legs)

Same official quadratic taker formula, fail-closed on the existing excerpt.

- Entry fill: charge taker fee at `fill_price`
- 60¢ (or better) exit: charge a **second** taker fee at exit price
- Hold-to-settlement: entry fee only (settlement is not a second trade)
- Do not assume maker rebate. Series is `quadratic` (no maker-fee table). Resting fills, if ever enabled later, would still not invent a rebate.

Unfilled 50¢: release reserved debit at expire; no fee.

### Exposure at close

| State at `close_time` | Action |
|---|---|
| 50¢ working, never filled | expire, no P&L |
| filled, 60¢ never executable | settle official `result` |
| filled and 60¢ filled | realized = exit credit − entry cost − both fees |
| result missing | stay pending (`result_not_ready`) |

---

## 6. Why a 15-minute cron cannot do this

Checked live this session (elections host HTTP 200; did not circumvent anything):

- Window `KXBTC15M-26NOV051445-45` opened `19:30Z`. At `19:40Z` (~10 minutes in) YES ask was **$0.946**, bid **$0.945**. A 50¢ taker buy was **not** available then. A 60¢ sell was also meaningless (book already ~94¢).
- Public 1-minute candlesticks exist (`GET /series/KXBTC15M/markets/{ticker}/candlesticks`) but the original design already noted live open windows can be sparse. They are **audit**, not a substitute for seeing the open.
- Baseline `cycle` is one snapshot then hold. It cannot watch the open **and** a mid-window 60¢ bid.

So: **parent’s existing 15-minute `cycle` stays as the baseline reporter.** Lean-50 needs **intra-window** public GETs. This design does **not** start that runner now.

**Cannot promise:** the exact first second of the book, a fill at 50.00, or a 60¢ exit in every window. Late start → skip `missed_open` / `ask_above_limit`.

---

## 7. Two viable runners (public GET only, no paid services, no auth)

Both write **only** the lean-50 state dir. Both stop on 403 / policy block (same as today). Neither is installed by this design.

### Option A — frequent tick (recommended)

Parent adds a **systemd timer or cron every 20 seconds** (or 15–30s) on the Linux box:

```text
kxbtc15m lean50-tick --state-dir ~/.local/share/kxbtc15m-paper-lean50
```

Each tick: settle/expire if needed → snapshot open market + book (+ optional prints/OI) → maybe arm 50¢ / fill / arm 60¢ / exit. Idempotent. Stdlib. No extra packages. No always-on Python daemon required (timer fires the CLI).

Keep the **existing 15-minute** `cycle` on the original state dir, plus a 15-minute **read-only** `compare` for Drew.

- **Pros:** actually has a chance to see near-open asks around 50¢ and mid-window 60¢ bids; restart-safe; still GET-only.
- **Cons:** more HTTP; still not tick-level; parent must create the timer (we will not start it in this approval pass).

### Option B — a few extra crons, no 20s timer

Add 2–3 cron lines per 15-minute bucket, e.g. `:00/:15/:30/:45` plus `+2m` and `+8m`.

- **Pros:** fewer requests; still no daemon.
- **Cons:** misses most opens and most 60¢ windows (this session’s +10m book was already 94¢). Weak for the strategy as stated.

**Recommendation: Option A.** Option B is only a fallback if Drew refuses a 20s timer. Do not pretend Option B is “buy immediately at the open.”

**Not proposed:** WebSocket (auth), paid collectors, cloud schedules from this agent, or anything that writes orders.

Parent **15-minute reporting routine is in force now** (read-only scorecard). It must cover **both** strategies every cycle using the schema in §13. Until lean-50 is approved and deployed, the lean-50 block is mandatory and must say **`running: false` / `not_running`**. Do not omit it. Do not fake ticks.

After implementation (not now):

```text
kxbtc15m compare --baseline-state-dir … --lean50-state-dir …
```

No chat/email from the program. Parent (not this agent) attaches the JSON+text to the 15-minute routine.

---

## 8. Data flow (lean-50 tick)

```
tick:
  settle official pending / expire unfilled 50¢ at close
  → discover current window
  → snapshot market + book + volume_fp + open_interest_fp
    (+ optional public prints, stored as prints)
  → if no working intent: compute last-10 lean (finalized only, close < this open)
        skip tie / short history / bad quote
        else arm 50¢ limit (reserve debit)
  → if 50¢ armed and ask<=50 with depth+fresh: taker fill (record vs-50¢)
  → if filled and bid>=60 with depth+fresh: taker sell (fees on both legs)
  → else hold
compare (15min, read-only): baseline ledger vs lean50 ledger
```

Predictions remain immutable and pre-outcome. No lookahead: last-10 uses only markets that had already finalized before this `open_time`.

---

## 9. Tests required before any lean-50 paper day counts

Unit / fixture only; **never** open the original live `ledger.sqlite`.

- Isolation: lean-50 writes cannot change baseline cash, rows, or file bytes
- Last-10: only finalized `yes`/`no` with `close_time < open_time`; ignore later windows (no lookahead)
- Tie 5–5 → `lean_tie`; 9 history → `insufficient_history`
- Volume / OI stored under their real names; lean input is not OI
- Public prints stored as prints, not “orders”
- 50¢ is a cap: ask 0.51 → no fill; ask 0.49 → fill 0.49 and `improvement_vs_limit_cents = 1`
- Stale / thin / inconsistent book → no fill
- 60¢ exit refused until entry filled; bid 0.59 → no exit; bid 0.61 → fill 0.61 + improvement
- Fees charged on entry and on exit; hold-to-settlement has one fee
- Unfilled 50¢ expires at close, reserve released, no P&L
- Filled, no exit → official result only
- Duplicate ticks: no second debit / second fill
- Restart: working 50¢ / filled pending / expired states survive
- Missing official result stays pending
- `$1` inclusive including reserved exit fee; `$5` pending-aware; 1 pending
- Original `cycle` tests still pass with no behavior change
- Disposable live GET smoke uses a temp lean-50 dir only
- 15-minute `compare` uses `observed_at` = run/snapshot time, never `close_time` as if it were “now”
- Settlement events are `official_settlement`, never `sell` / `fill_sell_60`
- Win/loss and `cycle_pnl_cents` appear only after a realized close (60¢ fill or official settlement)
- Lean-50 block is `not_running` when the second ledger/timer is absent
- Loss analysis: `cause` is `unknown` unless a fixture proves a mechanism; hypotheses stay `unproven`
- Opening the original live ledger path with a fresh $100 seed is forbidden in tests and deploy

---

## 10. Deploy / migration (after approval only)

1. New artifact (e.g. `kxbtc15m-paper-v2.tar.gz`) that **adds** lean-50 modules; baseline code path stays.
2. Parent extracts beside or over the **program** copy, **not** over `~/.local/share/kxbtc15m-paper`.
3. Original `ledger.sqlite` is left in place. No migration rewrite. No import of baseline trades into lean-50.
4. First `lean50-tick` creates a **new** $100 `lean50.sqlite`.
5. Parent (not this agent) adds the 20s timer **and** keeps the 15-minute baseline `cycle` + `compare`.
6. Build ≠ deployed ≠ timer running.

---

## 11. Explicit limitations

- Not a live bot. Not exchange-matched. No other traders’ private orders.
- Cannot promise the instant open or a fill at exactly 50.00.
- 20s polling still misses seconds; books can jump through 50¢/60¢ between ticks.
- Last-10 majority is a crude trend proxy. No claimed edge, no calibrated probability, no 75% story.
- Public volume/OI/prints are stored honestly and are not “sentiment.”
- `external-api.kalshi.com` 403 on the parent box: keep elections host; do not bypass.
- Candles/prints can be empty or lagged; skip, don’t invent.
- This file is not permission to start a runner or publish a repo.

---

## 12. Approval gate

Reply **approve Option A** (or **approve Option B** / changes) before any lean-50 code, new sqlite, or timers.

No critical product ambiguity remains if Drew accepts: last-10 = official finalized public results only; our paper history is stored and compared, not voted into the lean; v1 fills are **taker-only** when the book crosses the limit.
