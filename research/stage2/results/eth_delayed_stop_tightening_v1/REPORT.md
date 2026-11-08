# ETH delayed stop-tightening experiment

## Verdict: DOES NOT ROBUSTLY IMPROVE

Baseline: **$430.16 profit · 459 trades · 71.0% economic winners · $-4.55 average loss · -9.66% drawdown**

At 12 hours, only unarmed Dip/Pullback lots with MFE below +0.5% and a failed original setup receive the tighter stop.

| Tightened stop | Profit | Change | Trades | Economic wins | Avg win | Avg loss | Stop rate | Drawdown | WF change | WF improved | Eligible / hit | Recoveries cut | Pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Tighten to -3.0% | $411.55 | $-18.61 | 472 (+13) | 68.2% | $1.87 | $-3.95 | 81/472 (17.2%) | -10.00% | $-11.69 | 3/6 | 117/47 | 14 | NO |
| Tighten to -2.5% | $410.61 | $-19.55 | 474 (+15) | 67.5% | $1.88 | $-3.71 | 86/474 (18.1%) | -9.25% | $-17.10 | 3/6 | 117/54 | 19 | NO |
| Swing low -0.25%, capped at -3.0% | $400.04 | $-30.13 | 478 (+19) | 66.5% | $1.89 | $-3.54 | 93/478 (19.5%) | -8.65% | $-30.84 | 2/6 | 117/83 | 25 | NO |

## Decision

**Keep the live −4.5% Dip/Pullback stop behavior unchanged.**

The best full-history variant was **Tighten to -3.0%**: profit changed **$-18.61**, economic win rate changed **-2.8 points**, average loss changed **$+0.60**, drawdown changed **-0.33 points**, and walk-forward profit changed **$-11.69** across **3/6** improved windows.

The August–September 2026 period is diagnostic only and was not used for acceptance.
