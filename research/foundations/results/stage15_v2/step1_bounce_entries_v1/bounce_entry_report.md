# Stage 1.5 v2 — Confirmed Bounce Entry Analysis

## Purpose and rule

This step tests whether waiting for visible buyer confirmation improves entries after a deduplicated moving-average touch from below. A valid setup must reclaim the average within 30 minutes. A later candle must remain above the average and trade strictly above the reclaim candle's high. Execution occurs at the next source-candle boundary, priced at the corresponding raw 1-minute open. The immediate policy permits only the next candle; the other policies permit 15 or 30 minutes. A close at or below the average before breakout cancels the setup.

All policies use the frozen +4% target, -4% stop, 24-hour maximum hold, conservative same-minute stop priority, one position at a time, and 0.2% round-trip cost.

## Reference setup

| policy | confirmed_entries_earlier | confirmed_entries_later | nonoverlap_trades_earlier | nonoverlap_trades_later | net_0_2_mean_pct_earlier | net_0_2_mean_pct_later | target_pct_earlier | target_pct_later | stop_pct_earlier | stop_pct_later | positive_quarters_pct | net_ci95_low_earlier | net_ci95_low_later | provisional_pass | robust_pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bounce_break_15m | 39 | 32 | 31 | 23 | -0.4571 | 0.9895 | 35.4839 | 43.4783 | 35.4839 | 13.0435 | 66.6667 | -1.5132 | — | False | False |
| bounce_break_30m | 39 | 32 | 31 | 23 | -0.4571 | 0.9895 | 35.4839 | 43.4783 | 35.4839 | 13.0435 | 66.6667 | -1.5132 | — | False | False |
| bounce_break_immediate | 35 | 29 | 28 | 21 | -0.7899 | 1.1028 | 32.1429 | 42.8571 | 39.2857 | 9.5238 | 55.5556 | — | — | False | False |

## Comparison with the current candidate

| entry_method | nonoverlap_trades_earlier | nonoverlap_trades_later | net_0_2_mean_pct_earlier | net_0_2_mean_pct_later | target_pct_earlier | target_pct_later | stop_pct_earlier | stop_pct_later | positive_quarters_pct |
|---|---|---|---|---|---|---|---|---|---|
| bounce_break_15m | 31 | 23 | -0.4571 | 0.9895 | 35.4839 | 43.4783 | 35.4839 | 13.0435 | 66.6667 |
| bounce_break_30m | 31 | 23 | -0.4571 | 0.9895 | 35.4839 | 43.4783 | 35.4839 | 13.0435 | 66.6667 |
| bounce_break_immediate | 28 | 21 | -0.7899 | 1.1028 | 32.1429 | 42.8571 | 39.2857 | 9.5238 | 55.5556 |
| current_bullish_candle_30m | 62 | 55 | 0.2087 | 0.2401 | 32.2581 | 29.0909 | 24.1935 | 21.8182 | 77.7778 |

## Cross-grid robustness

- Configurations evaluated: 243 (81 configurations x 3 bounce windows).
- Provisional passes: 0.
- Robust passes with positive 95% block confidence bounds in both periods: 0.
- Candidate rows audited: 226,320.
- Protected pre-existing files verified unchanged: 466.

The later period has already been inspected during Stage 1.5 and is not untouched out-of-sample evidence. Any surviving rule still requires official Stage 2 forward validation.
