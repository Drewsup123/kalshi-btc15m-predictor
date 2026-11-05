# Observational note — monitor investigation (no rule change this release)

**Source:** attached monitor write-up (~14:53 MST).  
**This risk release:** open-exit $10 / no daily cap only. **No** baseline quote-rule change. **No** host migration. **No** watcher started here.

## Confirmed from the write-up (labeled)

- **H1 baseline `inconsistent_book`:** 9/10 recent baseline skips. Market flat ask vs `1 −` opposite **book** bid routinely differs 3–12¢ while `yes_bid+no_bid≈0.99` (normal 1¢ binary structure). The only baseline fill (`…1445-45`) had a 0.6¢ mix. Mixing **two quote sources** (market snapshot vs book complement) is the evidenced mechanism. **Not** “no markets.” **Not** applied as a code change here.
- **H4 watcher wall gaps:** same PID 2477494 stayed alive (`hrtimer_nanosleep`) with `observed_at` gaps up to **669s (~11 min)**. GET timeouts cannot explain that. After the gap, first look on `…1700-00` was +371s → mandatory `missed_open` (180s door). **Alive ≠ 20s wall sampling.**

## Safe observations only (not implemented here)

- Baseline: if a later pass changes quotes, compare **same-source** market ask vs `1 −` market opposite bid, and keep conservative executable `max(market, 1−book)`. Do **not** silently widen `ask_epsilon` to force trades.
- Watcher: deadline wakeups + explicit `gap` when `now - last_tick > 45s`; run on a host that does not suspend. Product choice: align first poll to `open_time` after a stall — that is **not** a lean/tape relax.
- Reporting: surface open-exit entries/exits/P&L so “nothing happened” is not confused with baseline skips. Duplicate `watch.log` lines are stdout+file, not double trades.

No parent files were edited. No cloud watcher was started.
