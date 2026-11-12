# ETH stronger Dip-confirmation experiment

## Verdict: DOES NOT ROBUSTLY IMPROVE

Baseline: **$430.16 profit · 459 trades · 71.0% economic winners · $-4.55 average loss · -9.66% drawdown**

Only Dip confirmation changes. Mode C, Pullback, exits, costs, blocked hours and five shared slots are unchanged.

| Confirmation | Profit | Change | Trades | Economic wins | Avg win | Avg loss | Stop rate | Unarmed | Drawdown | WF change | WF improved | Removed profitable Dip trades | Pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Current green candle | $430.16 | $+0.00 | 459 (+0) | 71.0% | $1.88 | $-4.55 | 67/459 (14.6%) | 67 | -9.66% | $+0.00 | 0/6 | 0 ($0.00) | NO |
| Green + close above zone midpoint | $316.64 | $-113.52 | 250 (-209) | 63.6% | $2.32 | $-4.44 | 39/250 (15.6%) | 39 | -6.86% | $-125.57 | 1/6 | 210 ($341.89) | NO |
| Green + close above zone top | $278.57 | $-151.59 | 196 (-263) | 61.2% | $2.65 | $-4.41 | 34/196 (17.3%) | 34 | -9.52% | $-124.95 | 1/6 | 250 ($389.89) | NO |
| Green + close above previous 5m high | $425.25 | $-4.92 | 438 (-21) | 69.9% | $1.91 | $-4.53 | 64/438 (14.6%) | 64 | -9.53% | $-3.75 | 1/6 | 33 ($38.09) | NO |

## Decision

**Keep the live green-candle confirmation unchanged.**

The best full-history alternative was **Green + close above previous 5m high**, changing profit by **$-4.92**, economic win rate by **-1.2 points**, average loss by **$+0.02**, and walk-forward profit by **$-3.75** while improving **1/6** windows.

The August–September 2026 result is diagnostic only; it was not used for acceptance.
