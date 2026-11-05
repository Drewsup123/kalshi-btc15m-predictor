# Official Kalshi fee source (verified this build session)

**Status:** verified 2026-11-05 in this implementation session.  
**Fail-closed rule:** paper fills must not be booked unless this excerpt is present and the code constant matches.

## Primary source

- **Document:** Fee Schedule for July 2026 — 7.7.26 Update
- **URL:** https://kalshi.com/docs/kalshi-fee-schedule.pdf
- **Opened this session:** yes (public search extract of that PDF). Direct PDF download from this environment returned HTTP 429 HTML, so the numeric formula below is taken from the official PDF text extract, not from a third-party blog.

### General trading fee (taker)

Quoted from that official schedule:

> Trading fees are charged as a variable percentage fee of the expected earnings on an individual contract […] The current general fee charged for a trade in dollars is given by the following formula:
>
> `fees = round up(M × 0.07 × C × P × (1 − P))`
>
> `P` = the price of a contract in dollars (50 cents is 0.5)  
> `C` = the number of contracts being traded  
> `M` = the multiplier for each contract (default is 1 unless otherwise indicated)

Trading fees are charged for orders that are immediately matched (takers). This paper simulator treats every simulated fill as a **taker**. No maker rebate is assumed.

## Corroborating official API fields (same session)

`GET https://api.elections.kalshi.com/trade-api/v2/series/KXBTC15M` returned HTTP 200:

| Field | Live value |
|---|---|
| `ticker` | `KXBTC15M` |
| `frequency` | `fifteen_min` |
| `fee_type` | `quadratic` |
| `fee_multiplier` | `1` |
| `title` | BTC 15 min |

Official Get Series docs (`https://docs.kalshi.com/api-reference/market/get-series`) state that `quadratic` is described by the General Trading Fees Table in `https://kalshi.com/docs/kalshi-fee-schedule.pdf`, and that `fee_multiplier` is applied to the fee calculation.

Help Center (`https://help.kalshi.com/en/articles/13823805-fees`, dated April 19, 2026) points back to that same complete Fee Schedule for the math.

## Pinned constants for this build

```
FEE_KIND = quadratic_taker
FEE_CONSTANT = 0.07
DEFAULT_MULTIPLIER = 1
ROUNDING = round_up_to_next_cent_on_order_total
```

If a later official schedule changes the constant, halt paper entries until this excerpt is updated from a newly opened official source.
