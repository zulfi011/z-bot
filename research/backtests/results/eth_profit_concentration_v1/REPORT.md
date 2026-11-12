# ETH profit-concentration stress test

## Verdict: CONCENTRATED, BUT NOT DEPENDENT ON ONE OUTLIER

The strategy is unchanged. These exclusions are diagnostics, not tradable backtests.

| Test | Profit remaining |
|---|---:|
| All data | $430.16 |
| Excluding 2025-05 | $208.08 |
| Excluding largest winning episode | $356.64 |
| Excluding five largest winning episodes | $220.06 |

## Concentration

- Best month: **2025-05**, $222.08, or **51.6%** of total profit.
- Largest episode: $73.52, or **17.1%** of total profit.
- Five largest episodes: $210.11, or **48.8%** of total profit.
- Median month: **$8.54**.
- Worst month: **2024-10**, **$-21.82**.
- Months: 16 profitable, 1 flat, 5 losing.

## Drawdown recovery

- Median completed drawdown: **0.2 days**.
- Longest time below a previous peak: **142.2 days**; recovery after its trough took **132.2 days**.
- The maximum drawdown recovered **3.9 days** after its trough.
- Unrecovered drawdown at the data endpoint: **4.6 days**.

## Decision

Keep the uncapped trend exit. The current strategy remains profitable after every requested exclusion, but its best month and five largest market episodes each supply about half of total profit. Future ETH candidates must improve ordinary periods as well as the full-history result; an improvement confined to the best month should be rejected.
