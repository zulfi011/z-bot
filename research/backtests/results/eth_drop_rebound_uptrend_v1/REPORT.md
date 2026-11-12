# ETH drop-rebound uptrend-filter experiment

## Result: **REJECT**

The filter requires all three conditions at the completed drop candle: the 24-hour EMA is above
its value six hours earlier, the 7/15/30-day averages are not bearishly stacked, and price is
above the completed-day 30-day average.

| Metric | Current ETH base | Unfiltered add-on | Uptrend-filtered add-on |
|---|---:|---:|---:|
| Profit | $430.16 | $447.06 | $432.10 |
| Profit change vs base | — | $+16.90 | $+1.94 |
| Trades | 459 | 557 | 465 |
| Extra trades | — | +98 | +6 |
| Headline win rate | 85.4% | 80.4% | 85.4% |
| Economic win rate | 71.0% | 64.1% | 70.8% |
| Average loss | $-4.55 | $-2.92 | $-4.48 |
| Add-on trades / profit | — | 98 / $16.90 | 6 / $1.94 |
| Add-on win rate | — | 57.1% | 83.3% |
| Later-period change | — | $+3.87 | $+0.00 |
| Walk-forward change | — | $+7.37 | $+1.94 |
| Walk-forward windows improved | — | 3/6 | 2/6 |

## Signal funnel

- Original drop signals: 102
- EMA rising: 19
- Non-bearish daily stack: 42
- Above 30-day average: 12
- Passed all three: 9

The filtered add-on is worth adding only if it remains above 75% combined win rate, adds at least
20 trades, improves full/later/walk-forward profit and at least four of six walk-forward windows,
without worsening average loss or drawdown.

This is local ETH research only. No live bot or server files were changed.
