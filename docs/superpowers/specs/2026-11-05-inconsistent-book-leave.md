# Readonly — baseline `inconsistent_book` (leave)

**Pass:** no quote-threshold or strategy change.  
**Observed_at:** 2026-11-05T20:49:36Z

## Question

Are repeated baseline `inconsistent_book` skips a parser/units bug, or the written 2¢ safety check firing on a real market-vs-book disagreement?

## Live official GET (elections host)

Open market `KXBTC15M-26NOV051600-00` (`status=active`, `close_time=2026-11-05T21:00:00Z`):

| Field | Value | Units |
|---|---|---|
| `yes_ask` | absent | — |
| `yes_ask_dollars` | `0.5900` | dollars, dotted string |
| `no_ask_dollars` | `0.4200` | dollars, dotted string |
| book envelope | `orderbook_fp` only | — |
| best YES bid | `0.4800` | dollars |
| best NO bid | `0.5100` | dollars |
| implied YES ask (`1 −` best NO) | `0.4900` | dollars |
| implied NO ask (`1 −` best YES) | `0.5200` | dollars |
| Δ YES (market − implied) | **+10.0¢** | |
| Δ NO (market − implied) | **−10.0¢** | |

`evaluate_quote` → `inconsistent_book` (`ask_epsilon=0.02`). Same dollar units on both sides. No integer-cent / missing-`_dollars` mixup.

## Conclusion

**Leave.** This is a real quote mismatch, not a schema or units error. The 2¢ check is doing what the frozen baseline says. Relaxing it would change strategy rules to force trades. Not done.
