# Stage 2 Step 7: Account Tracking

## Purpose

This step values the complete spot account after every raw one-minute SOL candle. It applies the frozen portfolio rule: start with $100, open at most two positions, and allocate 25% of current marked equity to each entry.

Each row records cash, SOL quantity, position cost, open position value, cumulative realized PnL, unrealized PnL, total PnL, total equity, equity peak, drawdown, and open-position count. Open SOL is valued at the current candle close. No future candle is used.

## Results

| Strategy | Trades | Wins | Losses | Final equity | Net PnL | Return | Maximum drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|
| Primary | 152 | 82 | 70 | $108.33 | +$8.33 | +8.33% | -12.16% |
| Control | 209 | 106 | 103 | $102.74 | +$2.74 | +2.74% | -15.24% |

The primary account's lowest equity was $89.08. Its worst drawdown occurred on 2025-05-07 at 18:09 UTC with two positions open. The prior event-only calculation estimated -11.20%; minute-close marking found a deeper -12.16% decline.

The final primary result changed slightly from $108.35 to $108.33 because each new 25% allocation now uses the account's currently marked value while another position is open.

## Validation

The replay tracked 1,006,560 consecutive candles per strategy from 2024-09-01 through 2026-07-31. On every row:

`cash + open position value = $100 + realized PnL + unrealized PnL = total equity`

The largest reconciliation error was below $0.000000000001. Cash never became negative, no leverage was used, no more than two positions were open, and all selected positions closed before the dataset ended.

## Simple Explanation

If the account has $75 cash and an open SOL position worth $27, total equity is $102. A new trade uses 25% of $102, or $25.50. As SOL moves, the account curve changes every minute even before a trade closes. This exposes temporary losses that completed-trade records cannot show.
