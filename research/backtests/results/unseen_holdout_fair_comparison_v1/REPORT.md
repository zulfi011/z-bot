# Fair Unseen Holdout Comparison

## Holdout

This test uses 57,600 continuous public Binance SOLUSDT one-minute candles from **2026-08-01 through 2026-09-09 UTC**. The earlier research ended on 2026-07-31. Earlier candles are used only to warm indicators; every entry starts inside the unseen holdout.

Both strategies are limited to one position and are compared separately at identical 25% and 100% current-equity allocation. Both use the same 10 bps fee and 2 bps adverse slippage per side.

## Result

| Allocation | Strategy | Trades | Wins / losses | Win rate | Final $100 | Return | Max drawdown |
|---:|---|---:|---:|---:|---:|---:|---:|
| 25% | current_frozen_3m_daily15d_a4_g10_s4_t24h | 1 | 1 / 0 | 100.00% | $99.93 | -0.07% | -0.78% |
| 25% | new_candidate_1m_rolling30d_a4_g20_s3_no_time | 1 | 1 / 0 | 100.00% | $101.03 | +1.03% | -0.99% |
| 100% | current_frozen_3m_daily15d_a4_g10_s4_t24h | 1 | 1 / 0 | 100.00% | $99.71 | -0.29% | -3.07% |
| 100% | new_candidate_1m_rolling30d_a4_g20_s3_no_time | 1 | 1 / 0 | 100.00% | $104.12 | +4.12% | -3.87% |

The 40-day holdout is genuinely later but short. A result with few or zero trades is inconclusive rather than proof of superiority.
