# Stage 1.5 v2 — Market Filter Analysis

## Purpose and fixed definitions

This step tests whether causal market context can remove weak SOL entries from the current candidate. The entry remains bullish-candle confirmation within 30 minutes after a deduplicated touch from below. The exit remains +4% target, -4% stop, and a 24-hour maximum hold.

The 15-day trend compares the average known at the signal with the value known 24 hours earlier. Joint trend requires both SOL and BTC to rise. Strongly bearish means 7-day < 15-day < 30-day averages. Extreme volatility means the previous 24-hour range exceeded the earlier-period 90th-percentile threshold of 9.4113% fitted from 10,109 unique signal times.

## Reference SOL setup

| filter_variant | entries_earlier | entries_later | nonoverlap_trades_earlier | nonoverlap_trades_later | retention_pct_earlier | retention_pct_later | net_0_2_mean_pct_earlier | net_0_2_mean_pct_later | target_pct_earlier | target_pct_later | stop_pct_earlier | stop_pct_later | positive_quarters_pct | net_ci95_low_earlier | net_ci95_low_later | provisional_pass | robust_pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all_market_conditions | 278 | 211 | 62 | 55 | 100.0000 | 100.0000 | 0.2087 | 0.2401 | 32.2581 | 29.0909 | 24.1935 | 21.8182 | 77.7778 | -0.6053 | -0.6883 | False | False |
| rising_15d | 142 | 89 | 30 | 26 | 51.0791 | 42.1801 | 0.6207 | 0.6299 | 36.6667 | 30.7692 | 16.6667 | 15.3846 | 55.5556 | -0.3505 | — | False | False |
| sol_and_btc_rising_15d | 108 | 66 | 27 | 20 | 38.8489 | 31.2796 | 0.4400 | -0.0019 | 33.3333 | 20.0000 | 18.5185 | 20.0000 | 44.4444 | — | — | False | False |
| avoid_strong_bearish | 182 | 140 | 42 | 35 | 65.4676 | 66.3507 | 0.3827 | 0.3132 | 33.3333 | 20.0000 | 21.4286 | 14.2857 | 50.0000 | -0.5270 | -0.7246 | False | False |
| avoid_extreme_volatility | 252 | 203 | 55 | 53 | 90.6475 | 96.2085 | 0.1380 | 0.1341 | 30.9091 | 26.4151 | 23.6364 | 22.6415 | 66.6667 | -0.7872 | -0.7872 | False | False |
| avoid_bearish_and_extreme | 164 | 133 | 38 | 34 | 58.9928 | 63.0332 | 0.3717 | 0.1656 | 34.2105 | 17.6471 | 21.0526 | 14.7059 | 50.0000 | -0.6403 | -0.8444 | False | False |
| rising_15d_and_safe | 121 | 66 | 26 | 19 | 43.5252 | 31.2796 | 0.4976 | 0.4197 | 38.4615 | 21.0526 | 19.2308 | 10.5263 | 57.1429 | — | — | False | False |
| all_filters | 90 | 51 | 23 | 16 | 32.3741 | 24.1706 | 0.2695 | 0.1849 | 34.7826 | 18.7500 | 21.7391 | 12.5000 | 42.8571 | — | — | False | False |

## Robustness result

- SOL configurations evaluated: 27 across 8 predefined filter variants (216 comparisons).
- Comparisons retaining the required samples: 62.
- Sample-qualified comparisons profitable after costs in both periods: 6.
- Provisional passes that also improved the unfiltered baseline in both periods: 1.
- Robust passes with positive 95% block confidence bounds in both periods: 0.
- Audited reference event rows: 561.
- Protected earlier files verified unchanged: 493.

The later period was used in earlier research and is not untouched out-of-sample evidence.
