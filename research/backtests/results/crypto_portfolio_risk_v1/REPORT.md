# Four-coin shared-wallet portfolio-risk experiment

## Original references

- Canonical ETH alone: **$430.16 profit · 459 trades · -9.66% maximum drawdown** on $500.
- Unchanged ETH + BTC + SOL + AAVE in one $1,400 wallet: **$722.17 profit · 1178 trades · 80.6% headline wins · $-3.46 average loss · -3.60% drawdown**.

This is the first valid shared-wallet baseline. The ETH-only 9.66% drawdown must not be treated as the whole trading account's risk.

## Where the shared result came from

| Coin | Trades | Profit | Headline win rate | Average loss |
|---|---:|---:|---:|---:|
| AAVE | 271 | $117.36 | 79.3% | $-4.09 |
| BTC | 192 | $85.15 | 81.8% | $-3.16 |
| ETH | 459 | $433.13 | 85.4% | $-4.55 |
| SOL | 256 | $86.53 | 72.3% | $-2.10 |

Maximum simultaneous exposure was **$1300** across **4 coins**. The worst common crypto episode was **crypto:0075**, losing **$-27.24** across **3 coin(s)** and 9 trades.

## Frozen correlated-exposure tests

| Rule | Profit | Change vs shared control | Trades | Drawdown | DD change | WF windows improved | Risk-rule blocks |
|---|---:|---:|---:|---:|---:|---:|---:|
| global_open_1000 | $714.47 | $-7.70 | 1174 | -3.60% | +0.00 pp | 0/6 | 11 |
| episode_max_2_coins | $654.97 | $-67.21 | 1136 | -3.59% | +0.01 pp | 2/6 | 75 |
| episode_open_300 | $564.78 | $-157.39 | 995 | -3.70% | -0.10 pp | 2/6 | 343 |
| combined_correlated_cap | $559.97 | $-162.20 | 985 | -3.70% | -0.10 pp | 2/6 | 356 |

## Stops slipping together

| Extra slippage on every protective stop | Profit | Change | Drawdown |
|---|---:|---:|---:|
| +25 bps | $668.63 | $-53.54 | -4.03% |
| +50 bps | $615.09 | $-107.09 | -4.46% |

## Decision

**Do not deploy a correlated-exposure rule from this experiment.** The best percentage-drawdown rule was `episode_max_2_coins`, changing drawdown from **-3.60%** to **-3.59%**, but the worst dollar drawdown remained **$53.46**. It changed profit by **$-67.21** and improved only **2/6** walk-forward windows.

The useful change is measurement: future live risk reporting should use one shared marked-to-market equity curve and common crypto episode exposure. This local test does not alter ETH or any other live strategy, and it does not use the retired August-September period as acceptance evidence.
