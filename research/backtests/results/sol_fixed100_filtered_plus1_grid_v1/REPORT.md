# SOL Fixed-$100 Grid + Filters — Break-even + 1% Trail Starts

Same as `sol_fixed100_filtered_grid_v1` but trail start = break-even + 1% (+1.245% … +1.315%).
**23,760 combinations.**

**1,212 profitable**; **83 profitable in both periods** (none 6, above 30d 19, skip 06–12 31, both 27).
Median by filter: none −$67.5, above 30d −$52.1, skip 06–12 −$47.5, both −$37.3.

Best (exact = fast): **3m, 12-day average, ±0.5%, −2% stop, trail +1.251% / 12%, skip entries 06–12 UTC**

| Window | Trades | Win rate | Profit on $300 | Max DD | Profit factor |
|---|---:|---:|---:|---:|---:|
| Full | 239 | 74.1% | +$51.94 (+17.3%) | −9.79% | 1.38 |
| Earlier | 130 | 73.1% | +$22.61 | −9.79% | 1.29 |
| Later | 109 | 75.2% | +$29.34 | −5.55% | 1.49 |
| Unseen | 21 | 81.0% | +$8.02 | −2.70% | 1.91 |

Fees + slippage $57.19; 10.9 trades/month. With both filters (rank 7): +$44.77, −8.51% DD, PF 1.47.

The consistent group is dominated by the 12-day / ±0.5% / −2% setup, which is profitable in both periods on
1m, 3m and 5m candles once filtered. Other consistent setups: 3m / 8-day / ±0.1% / skip 06–12 (+$22.93),
1m / 9-day / ±0.2% / both (+$27.87, unseen −$3.20).
