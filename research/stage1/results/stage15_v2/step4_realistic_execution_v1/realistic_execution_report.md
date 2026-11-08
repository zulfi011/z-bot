# Stage 1.5 v2 — Realistic Spot Execution Analysis

## Purpose and assumptions

This step replays long-only spot orders with one open position per configuration. Targets and stops are measured from the actual entry fill. Both entry and exit pay the stated fee and adverse slippage. Same-minute target/stop conflicts use the stop, stops gap adversely, and the maximum hold remains 24 hours.

The realistic assumption is 10 basis points fee plus 2 basis points slippage on each side. Stress cases increase slippage to 5 and 10 basis points per side. These are research assumptions, not a live exchange fee quote.

## Reference results

| setup | scenario | nonoverlap_trades_earlier | nonoverlap_trades_later | mean_return_pct_earlier | mean_return_pct_later | median_return_pct_earlier | median_return_pct_later | execution_drag_earlier_pp | execution_drag_later_pp | positive_quarters_pct | ci95_low_earlier | ci95_low_later | execution_pass | robust_pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3m / avoid_strong_bearish | gross | 42 | 40 | 0.5830 | 0.6010 | 0.5173 | 0.9243 | 0.0000 | 0.0000 | 75.0000 | -0.3376 | -0.3538 | True | False |
| 3m / avoid_strong_bearish | fee_only | 42 | 40 | 0.3820 | 0.4000 | 0.3165 | 0.7227 | -0.2010 | -0.2010 | 62.5000 | -0.5367 | -0.5528 | True | False |
| 3m / avoid_strong_bearish | realistic | 42 | 40 | 0.3530 | 0.3679 | 0.2763 | 0.6824 | -0.2300 | -0.2331 | 62.5000 | -0.5660 | -0.5852 | True | False |
| 3m / avoid_strong_bearish | stressed | 42 | 40 | 0.3093 | 0.3198 | 0.2162 | 0.6220 | -0.2737 | -0.2812 | 62.5000 | -0.6070 | -0.6336 | True | False |
| 3m / avoid_strong_bearish | severe | 42 | 40 | 0.1910 | 0.2397 | 0.1160 | 0.5214 | -0.3920 | -0.3614 | 62.5000 | -0.7014 | -0.7105 | False | False |
| 5m / all_market_conditions | gross | 62 | 55 | 0.4087 | 0.4401 | 0.2596 | 0.8225 | 0.0000 | 0.0000 | 77.7778 | -0.3957 | -0.4265 | True | False |
| 5m / all_market_conditions | fee_only | 62 | 55 | 0.2080 | 0.2394 | 0.0592 | 0.6211 | -0.2006 | -0.2007 | 77.7778 | -0.5947 | -0.6254 | True | False |
| 5m / all_market_conditions | realistic | 62 | 55 | 0.1793 | 0.2095 | 0.0192 | 0.5808 | -0.2294 | -0.2306 | 77.7778 | -0.6236 | -0.6560 | True | False |
| 5m / all_market_conditions | stressed | 62 | 55 | 0.1362 | 0.1647 | -0.0408 | 0.5205 | -0.2725 | -0.2753 | 77.7778 | -0.6668 | -0.7018 | False | False |
| 5m / all_market_conditions | severe | 62 | 55 | 0.0644 | 0.0901 | -0.1407 | 0.4200 | -0.3443 | -0.3500 | 66.6667 | -0.7382 | -0.7765 | False | False |

## Robustness result

- Execution comparisons: 270 (27 configurations x 2 market variants x 5 scenarios).
- Realistic scenarios positive in both periods: 5.
- Realistic execution-screen passes: 2.
- Realistic robust passes with positive block confidence bounds: 0.
- Audited reference event rows: 995.
- Protected earlier files verified unchanged: 537.

All results are spot-only. The historical later period is not untouched Stage 2 evidence.
