# ETH portfolio-risk throttle experiment

## Original baseline

**$430.16 profit · 459 trades · 71.0% economic winners · $-4.55 average loss · -9.66% drawdown**

| Variant | Profit change | Trades | Economic win rate | Avg loss | Drawdown | Worst MTM day | WF change | Windows improved | Blocks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bearish_maximum_lots_3 | $+3.66 | 458 (-1) | 71.2% | $-4.56 | -9.66% | $-23.31 | $+3.66 | 1/6 | 1 |
| bearish_maximum_lots_2 | $+3.66 | 458 (-1) | 71.2% | $-4.56 | -9.66% | $-23.31 | $+3.66 | 1/6 | 1 |
| realized_daily_25 | $+0.00 | 459 (+0) | 71.0% | $-4.55 | -9.66% | $-23.31 | $+0.00 | 0/6 | 0 |
| mtm_daily_15 | $+0.00 | 459 (+0) | 71.0% | $-4.55 | -9.66% | $-23.31 | $+0.00 | 0/6 | 0 |
| market_episode_loss_7_5 | $+0.00 | 459 (+0) | 71.0% | $-4.55 | -9.66% | $-23.31 | $+0.00 | 0/6 | 0 |
| total_open_loss_10 | $-1.18 | 459 (+0) | 71.0% | $-4.55 | -9.66% | $-23.31 | $-1.18 | 0/6 | 1 |
| maximum_unarmed_3 | $-146.17 | 374 (-85) | 69.0% | $-4.53 | -8.52% | $-14.37 | $-134.24 | 1/6 | 223 |
| conservative_bundle | $-146.17 | 374 (-85) | 69.0% | $-4.53 | -8.52% | $-14.37 | $-134.24 | 1/6 | 223 |
| maximum_unarmed_2 | $-233.21 | 299 (-160) | 66.9% | $-4.52 | -6.63% | $-9.89 | $-217.09 | 1/6 | 307 |

## Decision

**Do not change the ETH allocation rules from this experiment.**

- The current $25 realized-loss rule and the new $15 marked-daily and $7.50 episode limits blocked no historical entry. They are safety guards, but they do not improve this backtest.
- The $10 total-open-loss rule blocked one signal and changed profit by **$-1.18** without improving drawdown.
- A three-unarmed-lot cap improved drawdown from **-9.66%** to **-8.52%** and the worst marked day from **$-23.31** to **$-14.37**, but sacrificed **$146.17** of profit.
- A two-unarmed-lot cap improved drawdown to **-6.63%**, but sacrificed **$233.21**. Reject both caps.
- The bearish slot cap avoided one losing trade and added **$3.66**, but improved only **1/6** walk-forward windows and did not reduce maximum drawdown. It is too weak to adopt.
- The combined rule is identical to the three-unarmed-lot cap because that condition dominates its decisions.

No throttle force-closes an existing position. The marked-loss checks should remain available as operational safeguards, but this history does not justify presenting them as a strategy improvement.
