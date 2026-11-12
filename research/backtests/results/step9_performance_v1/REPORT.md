# Stage 2 Step 9: Performance

## Purpose

This step converts the reconciled account curve and trade ledger into final performance measurements. The calculation uses the frozen $100 spot account, maximum two positions, 25% equity per entry, and all recorded fees and slippage.

## Results

| Metric | Primary | Control |
|---|---:|---:|
| Final equity | $108.33 | $102.74 |
| Total PnL | +$8.33 | +$2.74 |
| Total return | +8.33% | +2.74% |
| Trades | 152 | 209 |
| Win rate | 53.95% | 50.72% |
| Profit factor | 1.18 | 1.04 |
| Average trade | +$0.055 / +0.231% | +$0.013 / +0.072% |
| Worst trade | -$1.18 / -4.21% | -$1.13 / -4.21% |
| Maximum drawdown | -$12.33 / -12.16% | -$15.53 / -15.24% |
| Lowest equity | $89.08 | $86.38 |

The primary's largest drawdown ran from its 2024-11-29 equity peak to its 2025-05-07 trough. It recovered that prior peak on 2025-08-22. The primary finished above the control with fewer trades, a higher win rate, a higher profit factor, and a smaller drawdown.

## Interpretation

A 1.18 profit factor means winning trades earned $1.18 for every $1.00 lost. This is profitable, but the margin is small. The account gained $8.33 over approximately 23 months while temporarily declining by $12.33 from a previous peak.

## Validation

Every metric was calculated from the Step 7 minute equity and Step 8 trade ledger. Final PnL equals the sum of all trade profits. The equity curve includes unrealized changes at every one-minute close. Daily equity and drawdown data, machine-readable metrics, and the plotted chart are saved with this report.

## Simple Explanation

Imagine the winning trades together made $54.20 while the losing trades lost $45.87. The difference is the final $8.33 profit. At one point, however, the account fell about $12.33 from an earlier high before recovering.

The simple result is: **the strategy made money and beat the control, but the profit was small compared with the drawdown and time required. Its advantage exists, but it is not yet strong.**
