# Stage 1.5 v2 — ATR Spot Exit Analysis

## Purpose and execution model

This analysis replaces fixed percentages with volatility-adjusted exits for long-only SOL spot purchases. It uses the last completed one-hour candle's 14-period Wilder ATR. Stops are 1.5x, 2x, or 2.5x ATR from entry; targets are 1.5R, 2R, or 2.5R. Every trade has a 24-hour maximum hold, conservative same-minute stop priority, one open position per configuration, and 0.2% round-trip cost. There are no shorts, leverage, liquidation, or futures funding.

Median ATR at studied entries was 1.0246% of spot price (10th–90th percentile: 0.6528%–1.5190%).

## Current 5-minute reference setup

| strategy | nonoverlap_trades_earlier | nonoverlap_trades_later | median_stop_distance_pct_earlier | median_target_distance_pct_earlier | net_0_2_mean_pct_earlier | net_0_2_mean_pct_later | net_0_2_median_pct_earlier | net_0_2_median_pct_later | positive_quarters_pct | net_ci95_low_earlier | net_ci95_low_later | provisional_pass | robust_pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed_target_4_stop_4 | 62 | 55 | 4.0000 | 4.0000 | 0.2087 | 0.2401 | 0.0596 | 0.6225 | 77.7778 | -0.6053 | -0.6883 | False | False |
| atr_stop_2_5_rr_1_5 | 69 | 60 | 2.8369 | 4.2553 | -0.1284 | 0.2063 | -0.4736 | -0.2539 | 44.4444 | -0.9008 | -0.4914 | False | False |
| atr_stop_2_5_rr_2_5 | 68 | 58 | 2.8258 | 7.0644 | -0.1468 | 0.0964 | -1.0936 | -1.0493 | 66.6667 | -0.9363 | -0.5499 | False | False |
| atr_stop_2_rr_1_5 | 76 | 65 | 2.3132 | 3.4698 | -0.1581 | 0.1447 | -1.6157 | -0.4852 | 44.4444 | -0.6961 | -0.4421 | False | False |
| atr_stop_1_5_rr_2 | 87 | 74 | 1.7316 | 3.4632 | -0.1709 | 0.0857 | -1.6651 | -0.9325 | 44.4444 | -0.6317 | -0.3624 | False | False |
| atr_stop_1_5_rr_2_5 | 87 | 74 | 1.7316 | 4.3289 | -0.2065 | 0.1926 | -1.7052 | -0.9399 | 55.5556 | -0.6931 | -0.3220 | False | False |
| atr_stop_2_5_rr_2 | 68 | 58 | 2.8258 | 5.6515 | -0.2951 | 0.1251 | -1.0936 | -0.7616 | 66.6667 | -1.0474 | -0.5371 | False | False |
| atr_stop_2_rr_2 | 75 | 64 | 2.3140 | 4.6281 | -0.3098 | 0.1910 | -1.9186 | -0.8795 | 44.4444 | -0.9114 | -0.4104 | False | False |
| atr_stop_1_5_rr_1_5 | 89 | 78 | 1.7342 | 2.6014 | -0.3344 | 0.0065 | -1.6102 | -0.7818 | 44.4444 | -0.7506 | -0.3375 | False | False |
| atr_stop_2_rr_2_5 | 75 | 64 | 2.3140 | 5.7851 | -0.4396 | 0.1432 | -1.9247 | -0.9269 | 55.5556 | -1.0981 | -0.4235 | False | False |

## Previous step's 3-minute bearish-filter setup

| strategy | nonoverlap_trades_earlier | nonoverlap_trades_later | median_stop_distance_pct_earlier | median_target_distance_pct_earlier | net_0_2_mean_pct_earlier | net_0_2_mean_pct_later | net_0_2_median_pct_earlier | net_0_2_median_pct_later | positive_quarters_pct | net_ci95_low_earlier | net_ci95_low_later | provisional_pass | robust_pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed_target_4_stop_4 | 42 | 40 | 4.0000 | 4.0000 | 0.3830 | 0.4010 | 0.3173 | 0.7243 | 62.5000 | -0.5486 | -0.5513 | False | False |
| atr_stop_2_5_rr_2_5 | 49 | 43 | 2.9433 | 7.3584 | 0.0135 | 0.5913 | -0.9305 | 0.2333 | 62.5000 | -0.9313 | -0.2351 | False | False |
| atr_stop_2_rr_1_5 | 52 | 47 | 2.3638 | 3.5457 | -0.0546 | 0.3466 | -0.9212 | 0.2333 | 50.0000 | -0.7946 | -0.3159 | False | False |
| atr_stop_2_5_rr_1_5 | 49 | 44 | 2.9433 | 4.4150 | -0.0889 | 0.4929 | -0.6152 | 0.4781 | 50.0000 | -0.9774 | -0.2484 | False | False |
| atr_stop_2_5_rr_2 | 49 | 43 | 2.9433 | 5.8867 | -0.1070 | 0.5712 | -0.9305 | 0.4088 | 62.5000 | -0.9887 | -0.1722 | False | False |
| atr_stop_2_rr_2 | 51 | 46 | 2.3681 | 4.7361 | -0.1676 | 0.3388 | -1.5391 | -0.6889 | 62.5000 | -0.9806 | -0.3467 | False | False |
| atr_stop_2_rr_2_5 | 51 | 46 | 2.3681 | 5.9202 | -0.1793 | 0.4080 | -1.6788 | -0.8785 | 62.5000 | -1.0022 | -0.3398 | False | False |
| atr_stop_1_5_rr_2 | 61 | 53 | 1.7761 | 3.5521 | -0.2194 | 0.2527 | -1.6128 | -0.7739 | 62.5000 | -0.9216 | -0.2800 | False | False |
| atr_stop_1_5_rr_1_5 | 64 | 54 | 1.7803 | 2.6704 | -0.2982 | 0.0946 | -1.6294 | -0.7449 | 50.0000 | -0.9280 | -0.3425 | False | False |
| atr_stop_1_5_rr_2_5 | 61 | 53 | 1.7761 | 4.4401 | -0.3095 | 0.3096 | -1.6655 | -0.7885 | 62.5000 | -1.0042 | -0.2896 | False | False |

## Provisional ATR candidates

No ATR strategy passed the provisional screen.

## Robustness result

- Comparisons evaluated: 540 (27 SOL configurations x 2 market variants x 10 exits).
- Provisional ATR passes: 0.
- Robust ATR passes with positive block confidence bounds in both periods: 0.
- Reference event rows audited: 4,828.
- Protected earlier files verified unchanged: 516.

These are historical spot results. The later period has already been inspected and is not untouched Stage 2 evidence.
