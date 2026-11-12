# ETH allocation experiment

## Verdict: DOES NOT ROBUSTLY IMPROVE

Baseline: **$430.16** profit · **147** blocked signals · **1** minutes with simultaneous cross-family signals

## Blocked-signal evidence

| Family | Blocked | Hypothetical winners | Hypothetical win rate | Hypothetical P&L* | Duplicate market episode |
|---|---:|---:|---:|---:|---:|
| breakout | 8 | 7 | 87.5% | $5.73 | 2 |
| dip | 123 | 109 | 88.6% | $219.00 | 75 |
| pullback | 16 | 15 | 93.8% | $70.29 | 10 |

\* Hypothetical blocked-trade P&L is diagnostic and is not additive portfolio profit.

## Portfolio tests

| Variant | Profit change | Trades | Win rate | Avg loss | Drawdown | WF change | Windows improved | Retired-holdout change* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| reserve_final_slot_for_pullback | +5.41 | 449 (-10) | 85.7% | $-4.56 | -9.66% | +3.30 | 2/6 | +0.00 |
| priority_pullback_dip_modec | +0.00 | 459 (+0) | 85.4% | $-4.55 | -9.66% | +0.00 | 0/6 | +0.00 |

*The August–September 2026 window is post-selection research data, not unseen evidence.

## Decision

**Keep first-come-first-served allocation unchanged.** Neither preregistered change passed.
