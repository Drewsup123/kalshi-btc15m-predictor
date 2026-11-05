# Readonly diagnosis — KXBTC15M-26NOV051445-45

**Pass:** no baseline code changes.  
**Observed_at:** 2026-11-05T20:35:29Z (13:35:29 MST)

## Official API (elections host, GET only)

`GET /markets/KXBTC15M-26NOV051445-45` → HTTP 200, envelope **`{"market": {…}}`** (not a bare market).

Inner market:

| Field | Value |
|---|---|
| status | `finalized` |
| result | **`yes`** |
| close_time | 2026-11-05T19:45:00Z |
| settlement_ts | **2026-11-05T19:45:02.127035Z** |
| settlement_value_dollars | 1.0000 |
| expiration_value | 76263.33 |

Official outcome was available ~2 seconds after close. This check is ~50 minutes later. **Not a live settlement delay at this hour.**

This workspace has **no** file at `/workspace/personal-finance/kalshi-paper/state/ledger.sqlite`. That book was not opened, copied, or reset here.

## Hypothesis (labeled, not a claimed root cause of parent skips)

- **H-envelope (observed fact, unproven as the parent’s exact runtime cause):** baseline `_settle_pending` reads `payload.get("result")` on the GET body. On this official envelope the `result` lives at `payload["market"]["result"]`. A wrapper-unaware reader would treat the market as `result_not_ready` and leave a pending row.
- **H-inconsistent_book (plausible, unproven):** baseline skips when market ask and `1−opposite bid` differ by >2¢. Live books in this series often sit at that edge. **Not changed this pass.**
- Parent-reported first fill (NO × 15, 99¢ incl. 7¢, ~12:39 MST) on that ticker: if still pending on the parent box after 19:45Z, official YES means that paper NO would be a **realized loss** once settled — only after the parent process actually sees `result`.

New open-exit parser must unwrap `market` / `markets[]` before reading `result`.
