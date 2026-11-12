# ETH conditional setup-failure exit

## Verdict: DOES NOT ROBUSTLY IMPROVE

Baseline profit: **$430.16** · walk-forward: **$410.14** · drawdown: **-9.66%**

| Variant | Profit | Change | Avg loss | Win rate | Drawdown | Walk-forward change | Windows improved | Retired-holdout change* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| dip 12h | $439.11 | +8.94 | $-3.13 | 80.2% | -7.91% | +0.19 | 3/6 | -15.61 |
| pullback 24h | $425.61 | -4.56 | $-4.28 | 84.3% | -9.02% | -8.06 | 0/6 | -1.51 |
| breakout 24h | $423.55 | -6.62 | $-4.48 | 85.0% | -9.66% | -6.64 | 0/6 | +0.00 |
| dip 24h | $421.90 | -8.26 | $-3.66 | 81.8% | -9.68% | -8.09 | 1/6 | -6.65 |
| breakout 12h | $420.95 | -9.21 | $-4.24 | 84.1% | -9.66% | -11.49 | 0/6 | +2.94 |
| pullback 6h | $415.34 | -14.83 | $-3.51 | 81.3% | -8.80% | -19.56 | 1/6 | -8.71 |
| breakout 6h | $414.98 | -15.18 | $-4.16 | 83.7% | -9.66% | -15.18 | 0/6 | +3.11 |
| pullback 12h | $413.24 | -16.92 | $-3.88 | 82.8% | -8.97% | -20.68 | 1/6 | -5.37 |
| dip 6h | $411.62 | -18.54 | $-2.25 | 72.9% | -11.69% | -8.76 | 3/6 | -14.24 |

## Best full-history variant

**dip at 12 hours:** profit changed by **$+8.94**. It made 43 early exits, cut 27 trades that would later have recovered, and admitted 22 replacement trades.

Its average loss improved from **$-4.55** to **$-3.13** and drawdown improved from **-9.66%** to **-7.91%**, but win rate fell to **80.2%**. Walk-forward changed only **$+0.19**. The retired holdout changed **$-15.61**, but is diagnostic only.

*The August–September 2026 window is post-selection research data, not unseen evidence.

**Decision: do not deploy any of these nine variants.** The Dip 12h rule is useful as a risk-reduction lead, but its profit improvement is not stable enough yet.
