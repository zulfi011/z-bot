# ETH repeated-exposure experiment

## Verdict: DOES NOT ROBUSTLY IMPROVE

Baseline: **$430.16** profit · **459** trades · **-9.66%** drawdown · **$410.14** walk-forward

| Variant | Profit change | Trades | Win rate | Avg loss | Drawdown | WF change | Windows improved | Retired-holdout change* | Blocks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| setup_max_1 | +1.65 | 456 (-3) | 85.5% | $-4.56 | -9.66% | +1.65 | 1/6 | -0.90 | 4 |
| setup_max_2 | +0.00 | 459 (+0) | 85.4% | $-4.55 | -9.66% | +0.00 | 0/6 | +0.00 | 0 |
| two_correlated_stops_cooldown_6h | +0.00 | 459 (+0) | 85.4% | $-4.55 | -9.66% | +0.00 | 0/6 | +0.00 | 0 |
| family_stop_cooldown_6h | -1.18 | 459 (+0) | 85.4% | $-4.55 | -9.66% | -1.18 | 0/6 | +0.00 | 1 |
| market_max_2 | -41.91 | 375 (-84) | 85.9% | $-4.50 | -7.71% | -33.16 | 1/6 | +2.06 | 169 |
| market_max_1 | -139.45 | 281 (-178) | 85.1% | $-4.46 | -5.45% | -125.69 | 1/6 | +2.27 | 315 |

*The August–September 2026 window is post-selection research data, not unseen evidence.

## Decision

**Keep the ETH strategy unchanged.** No repeated-exposure rule passed all robustness gates.

Native setup caps may show no effect because Dip and Pullback already emit one candidate per native setup. The cross-family market caps are the direct test of several labels representing the same ETH move.
