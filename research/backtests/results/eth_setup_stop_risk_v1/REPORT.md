# ETH setup-based Dip stop with fixed maximum dollar risk

## Verdict: DOES NOT ROBUSTLY IMPROVE

Baseline: **$430.16 profit · 459 trades · 71.0% economic winners · $-4.55 average loss · -9.66% drawdown**

Each Dip stop sits below the episode low, is restricted to 1.5%–4.5%, and sizes toward $4.50 planned price risk with a $130 cap. Mode C and Pullback remain unchanged.

| Structural rule | Profit | Change | Trades | Economic wins | Avg win | Avg loss | Stop rate | Drawdown | WF change | WF improved | Rejected setups | Avg Dip order / risk | Pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Episode low −0.20% | $355.59 | $-74.57 | 492 (+33) | 56.1% | $2.15 | $-2.53 | 150/492 (30.5%) | -13.12% | $-64.16 | 2/6 | 0 | $128.53 / $1.94 | NO |
| Episode low −0.25% | $359.94 | $-70.22 | 492 (+33) | 56.3% | $2.15 | $-2.53 | 149/492 (30.3%) | -13.12% | $-60.49 | 2/6 | 0 | $128.53 / $1.94 | NO |
| Episode low −0.30% | $359.71 | $-70.45 | 492 (+33) | 56.3% | $2.15 | $-2.53 | 149/492 (30.3%) | -13.12% | $-60.71 | 2/6 | 0 | $128.52 / $1.94 | NO |

## Decision

**Keep the live fixed −4.5% Dip stop and $100 order size unchanged.**

The best full-history variant was **Episode low −0.25%**: profit changed **$-70.22**, economic win rate changed **-14.7 points**, average loss changed **$+2.02**, drawdown changed **-3.46 points**, and walk-forward profit changed **$-60.49** across **2/6** improved windows.

For that variant, the 1.5% minimum distance controlled **486/492** Dip candidates. Its structural stop cut **77** baseline recoveries and admitted **40** replacement trades.

The August–September 2026 period is diagnostic only and was not used for acceptance.
