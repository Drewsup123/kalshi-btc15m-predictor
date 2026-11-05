# Open-and-watch paper strategy — design for Drew approval

**Status:** design only. No code, timer, websocket, or new ledger until approved.  
**Supersedes:** the 50¢-buy / 60¢-sell draft (`lean50`). Those numbers were an **example**, not the strategy.  
**Date:** 2026-11-05

**Frozen:** original `cycle` / `status`, original `ledger.sqlite`, first parent-reported baseline fill (~12:39 MST, NO × 15, 99¢ inclusive, 7¢ fees). Do not reset that book. No live orders. Public data only. No invented sentiment or guaranteed reversal.

**One-liner:** second $100 paper wallet; buy the last-10 official lean at the **real opening ask**; then watch public book + prints and sell early on a **stated** target/trail/adverse rule — or hold to official settlement (settlement is **not** a sale).

---

## 1. What it does

Near each new `KXBTC15M` open:

1. Side from **last 10 official finalized results** (close_time **before** this open). That is a trend **proxy**, not “interest” or sentiment.
2. Store public `volume_fp`, `open_interest_fp`, quotes, and `GET /markets/trades` prints under those names. Never relabel them as sentiment or other people’s private orders.
3. If the book is usable, **buy immediately** at the conservative executable **ask** (same ask/depth/stale rules as baseline). Not 50¢. Not a made-up price.
4. While holding, poll live public book + prints more often than 15 minutes.
5. Sell early only if a **written** exit rule fires on an observed snapshot. No clairvoyance that “it will reverse.”
6. If no rule fires by close: **official `result` only**. Not booked as a sale.

Own ledger. Own $1 / $5 pending-aware caps. Compared to baseline every 15 minutes.

---

## 2. Isolation (unchanged intent)

| | Baseline (do not touch) | Open-and-watch (new) |
|---|---|---|
| Dir | existing `KXBTC15M_STATE_DIR` | `KXBTC15M_OPENEXIT_STATE_DIR` → `~/.local/share/kxbtc15m-paper-openexit` |
| File | `ledger.sqlite` (keep pending rows) | new `openexit.sqlite`, fresh $100 |
| Model | `exp-baseline-v1@2026-11-05` | `exp-open-exit-v1@2026-11-05` |

Deploy must **not** open the original ledger for writes or re-seed $100. Pending baseline positions stay.

---

## 3. Side, warmup, tape (proposed)

**Side (proposed default):** majority of last 10 finalized `yes`/`no` with `close_time < this open_time`.

| Case | Skip |
|---|---|
| 5–5 | `lean_tie` |
| <10 known | `insufficient_history` |
| void/empty result | drop that market; may become insufficient |
| first good tick **> 180s** after `open_time` | `missed_open` |
| ask ≥ 0.90 or ask ≤ 0.10 | `ask_no_room` (little up-move or already crushed) |

**Public prints at the open (optional confirm, not sentiment):** if ≥8 prints already exist on **this** new ticker before entry, and ≥6 have a **known** `taker_outcome_side` opposite the lean → skip `open_tape_against`. If fewer prints, skip this check.

**Aggressor unknown:** a print counts only if `taker_outcome_side` is `yes` or `no`. If that field is missing or disagrees with `taker_side`, store `aggressor_unknown` and **do not** use it for skip/exit counts.

**“Previous orders”** = official settled outcomes + **our** paper fills. Not other traders’ resting orders.

---

## 4. Fills (no fabricated path)

Taker only, on a **fresh** snapshot (age ≤ 30s): conservative ask/bid (max of market vs `1 − opposite best bid`), book consistent within 2¢, depth ≥ size, market open, not inside last 60s.

- **Entry** at that ask. Size so worst-case debit (ask×C + fee) ≤ **$1 inclusive**. Daily **$5** = realized losses + pending; wins do not refill. One pending.
- **Exit** at that bid when a rule fires. Second taker fee. Same official `0.07` formula, fail-closed.
- **Gaps:** if ticks are >45s apart, record `gap_seconds`. Evaluate **current** book/prints only. No backfilled “we would have sold at 12:41.”
- Slippage line: fill at displayed conservative price; **optimistic vs latency**; no extra tick.

---

## 5. Exit rules — proposed defaults (not user facts, not a trained model)

After fill, first matching rule on a valid tick wins:

1. **Target:** bid ≥ entry_ask + **8¢** → `exit_target`
2. **Trail:** after bid has been ≥ entry + **5¢**, exit if bid drops **3¢** from the hold-high bid → `exit_trail`
3. **Adverse tape:** **5** new known-aggressor prints on the opposite outcome → `exit_adverse_tape`
4. **Adverse book:** bid ≤ entry_ask − **10¢** → `exit_adverse_book`
5. Else **hold** → official settlement (`official_settlement`, not a sale)

These numbers are a transparent starting line so the bot is reproducible. They are **not** claimed optimal. No promise the market “starts going back down.”

---

## 6. Runner — GET vs WebSocket

| Option | How | Verdict |
|---|---|---|
| **A. 15–20s public GET tick** (recommended) | Parent systemd/cron: `openexit-tick`. Paths already proven unauth this session: series, markets, orderbook, `/markets/trades`. | Fits “watch live” without keys. Still not the first millisecond. |
| **B. A few extra 15-min crons** | Open + mid-window only. | Will miss most opens and most early exits. Weak. |
| **C. Kalshi WebSocket** | Official live WS is **authenticated**. | **Out of scope.** Needs API keys; this project is public-GET paper only. Do not add auth to “see the tape faster.” |

**Lifecycle (after approval, parent-owned — not started now):** install program copy → create **new** empty openexit dir → parent enables 20s timer → 15-min `cycle` on the **old** dir keeps running → 15-min `compare` reads both. Stop timer = strategy stops; baseline keeps its pending. Crash/restart: resume from sqlite; no invented missed fills.

15-min cron **cannot** run this strategy. It **can** report.

---

## 7. 15-minute compare report (in force now)

`observed_at` = actual run/snapshot time, **not** the window’s `close_time`.

Until this strategy is deployed, its block is required and must say **`not_running`**. Do not invent ticks.

```json
{
  "report_kind": "kxbtc15m_15min",
  "schema_version": "2026-11-05.report.v2",
  "observed_at": "2026-11-05T19:42:11Z",
  "observed_at_denver": "2026-11-05 12:42:11 MST",
  "market": {"ticker": "…", "open_time": "…", "close_time": "…", "status": "active"},
  "baseline": {
    "running": true,
    "model_version": "exp-baseline-v1@2026-11-05",
    "cash_cents": null,
    "pending_exposure_cents": null,
    "realized_pnl_cents": null,
    "this_window": {
      "actions": ["entry|skip|already_done|official_settlement"],
      "side": "yes|no|null",
      "signal": "momentum|seeded_control|…",
      "outcome": "yes|no|pending|null",
      "exit": "hold_official|null",
      "cycle_pnl_cents": null,
      "win_loss": "win|loss|none",
      "reason": "…"
    }
  },
  "open_exit": {
    "running": false,
    "status": "not_running",
    "detail": "architecture not approved; no second ledger or timer"
  },
  "loss_analysis": {
    "cause": "unknown",
    "hypotheses": [{"id": "H1", "text": "…", "status": "unproven"}]
  }
}
```

Rules: `win_loss` / `cycle_pnl_cents` only after a **realized** close. Pending ≠ profit. Official settlement ≠ `exit_target`. Hypotheses stay `unproven`; `cause` stays `unknown` unless a log proves the mechanism. No story-telling.

**This cycle (chat, 2026-11-05 12:42 MST):** public book on `KXBTC15M-26NOV051445-45` was ~YES 99¢ / NO 0.7¢. Baseline first paper (parent): NO×15, 99¢ incl. 7¢ fee at ~12:39 MST — **ledger not in this workspace, do not reset**. Open-and-watch: **not running**.

---

## 8. Tests (when building, not now)

Isolation (original file bytes unchanged); no lookahead on last-10; tie/history/missed_open/ask_no_room; aggressor_unknown ignored; gap does not invent fills; target/trail/tape/book exits only on observed ticks; hold → official_settlement not a sale; fees both live legs, one fee if held; $1 / $5 / 1 pending; compare `not_running`; `observed_at` ≠ close_time; original cycle tests still pass.

---

## 9. Limits

Not exchange-matched. Cannot promise the first second or that an “up move then down” happens. 20s polls skip through levels. Last-10 + tape counts are crude. No 75% / calibrated edge. 403 on `external-api`: keep elections host; do not bypass. Build ≠ deployed ≠ timer.

---

## 10. Approval question

**Approve Option A** (20s public GET runner, separate $100 `openexit` ledger, last-10 majority entry at real ask, proposed exits +8¢ / trail +5/−3 / 5 opposite prints / −10¢ book, 15-min compare, original book untouched)?

Or change the proposed numbers / pick Option B / reject the second strategy.
