# Stage 1.5 v2 — Strict Robustness Audit

## Scope

This audit uses the realistic long-only spot execution model: one position, 10 bps fee and 2 bps adverse slippage per side, +4% target, -4% stop, 24-hour maximum hold, and conservative same-minute stop priority. It compares the refined 3-minute bearish-filter candidate, the original 5-minute control, and the smaller 5-minute rising-average candidate.

## Final candidate comparison

| candidate | nonoverlap_trades_earlier | nonoverlap_trades_later | mean_pct_earlier | mean_pct_later | median_pct_earlier | median_pct_later | positive_quarters_pct | worst_quarter_mean_pct | worst_trade_pct_earlier | worst_trade_pct_later | expected_shortfall_10_pct_earlier | expected_shortfall_10_pct_later | max_drawdown_pct_earlier | max_drawdown_pct_later | positive_neighbors_both | neighbor_count | ci95_low_earlier | ci95_high_earlier | ci95_low_later | ci95_high_later | provisional_pass | strict_robust_pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| refined_primary | 42 | 40 | 0.3530 | 0.3679 | 0.2763 | 0.6824 | 66.6667 | -1.6777 | -4.2110 | -4.2110 | -4.2110 | -4.2110 | -17.7344 | -11.0422 | 2 | 3 | -0.5939 | 1.2862 | -0.5681 | 1.2815 | True | False |
| current_control | 62 | 55 | 0.1793 | 0.2095 | 0.0192 | 0.5808 | 80.0000 | -1.7293 | -4.2110 | -4.2110 | -4.2110 | -4.2110 | -32.8144 | -23.1206 | 1 | 2 | -0.6790 | 1.0051 | -0.7157 | 1.1157 | False | False |
| rising_average_secondary | 30 | 26 | 0.5898 | 0.5976 | 0.2078 | 0.9286 | 60.0000 | -1.7169 | -4.2110 | -4.2110 | -4.2110 | -4.2110 | -10.6794 | -8.7624 | 1 | 2 | -0.4025 | 1.5307 | — | — | False | False |

## Quarter-by-quarter results

| candidate | period | quarter | trades | mean_pct | median_pct | positive_pct |
|---|---|---|---|---|---|---|
| refined_primary | earlier | 2024Q4 | 14 | -0.8880 | -0.5833 | 28.5714 |
| refined_primary | earlier | 2025Q1 | 9 | -0.1244 | 0.6384 | 55.5556 |
| refined_primary | earlier | 2025Q2 | 13 | 1.2408 | 2.1667 | 61.5385 |
| refined_primary | earlier | 2025Q3 | 6 | 2.0412 | 2.6825 | 83.3333 |
| refined_primary | later | 2025Q3 | 4 | 0.9595 | 2.1387 | 75.0000 |
| refined_primary | later | 2025Q4 | 6 | 0.2003 | 0.2560 | 50.0000 |
| refined_primary | later | 2026Q1 | 12 | 1.4579 | 1.7989 | 75.0000 |
| refined_primary | later | 2026Q2 | 12 | 0.1874 | 0.2801 | 58.3333 |
| refined_primary | later | 2026Q3 | 6 | -1.6777 | -1.5437 | 16.6667 |
| current_control | earlier | 2024Q3 | 3 | 0.9006 | -0.1411 | 33.3333 |
| current_control | earlier | 2024Q4 | 19 | -1.5141 | -2.2089 | 26.3158 |
| current_control | earlier | 2025Q1 | 15 | 0.0892 | 0.7012 | 53.3333 |
| current_control | earlier | 2025Q2 | 19 | 1.2467 | 2.5686 | 63.1579 |
| current_control | earlier | 2025Q3 | 6 | 2.0259 | 2.6653 | 83.3333 |
| current_control | later | 2025Q3 | 4 | 0.9782 | 2.1761 | 75.0000 |
| current_control | later | 2025Q4 | 13 | 0.3043 | 0.0343 | 53.8462 |
| current_control | later | 2026Q1 | 17 | 0.2900 | 1.1599 | 58.8235 |
| current_control | later | 2026Q2 | 15 | 0.6067 | 0.6972 | 60.0000 |
| current_control | later | 2026Q3 | 6 | -1.7293 | -1.7169 | 16.6667 |
| rising_average_secondary | earlier | 2024Q3 | 1 | -0.5048 | -0.5048 | 0.0000 |
| rising_average_secondary | earlier | 2024Q4 | 8 | 0.5435 | -0.0897 | 50.0000 |
| rising_average_secondary | earlier | 2025Q1 | 6 | -1.5502 | -4.2110 | 33.3333 |
| rising_average_secondary | earlier | 2025Q2 | 10 | 1.2556 | 1.8132 | 60.0000 |
| rising_average_secondary | earlier | 2025Q3 | 5 | 2.1192 | 3.7714 | 80.0000 |
| rising_average_secondary | later | 2025Q3 | 3 | 0.0471 | 0.5808 | 66.6667 |
| rising_average_secondary | later | 2025Q4 | 3 | -0.1351 | 0.0343 | 66.6667 |
| rising_average_secondary | later | 2026Q1 | 10 | 1.4626 | 2.5189 | 70.0000 |
| rising_average_secondary | later | 2026Q2 | 8 | 0.5761 | 1.1795 | 75.0000 |
| rising_average_secondary | later | 2026Q3 | 2 | -1.7169 | -1.7169 | 0.0000 |

## Nearby-parameter results

| candidate | neighbor_timeframe | neighbor_touch_zone | changed_parameter | trades_earlier | mean_pct_earlier | trades_later | mean_pct_later | positive_both |
|---|---|---|---|---|---|---|---|---|
| refined_primary | 1m | 0.5000 | timeframe | 42 | 0.2109 | 44 | 0.1169 | True |
| refined_primary | 5m | 0.5000 | timeframe | 42 | 0.3526 | 35 | 0.2791 | True |
| refined_primary | 3m | 1.0000 | touch_zone | 40 | -0.2106 | 32 | -0.6058 | False |
| current_control | 3m | 0.5000 | timeframe | 62 | 0.2054 | 61 | 0.2901 | True |
| current_control | 5m | 1.0000 | touch_zone | 63 | -0.2706 | 53 | -0.5497 | False |
| rising_average_secondary | 3m | 0.5000 | timeframe | 29 | 0.7056 | 30 | 0.7360 | True |
| rising_average_secondary | 5m | 1.0000 | touch_zone | 29 | 0.2572 | 22 | -0.5776 | False |

## Decision

- Provisional passes before the confidence requirement: 1.
- Strict robust passes: 0.
- Protected earlier files verified unchanged: 556.

A strict pass requires enough independent trades in both periods, positive mean and median returns, at least 60% positive quarters, worst trade and expected shortfall above -5%, compounded drawdown above -20%, majority support from adjacent timeframes/zones, and positive lower 95% seven-day-block confidence bounds in both periods.

The later historical period is already observed and cannot replace official Stage 2 forward validation. Drawdown assumes equal-notional returns are compounded sequentially and is a comparison measure rather than a proposed portfolio sizing model.
