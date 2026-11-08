# SOL Confirmed Touch with Trailing-Only Exits

## Rules tested

The strategy waits for the existing bullish confirmation after a ±0.2% 15-day-average touch from below and buys at the raw one-minute open on the confirmation boundary. One position uses 100% of current equity. There is no hard stop and no time exit. The only permitted sale is a trailing stop after immediate/0% or +1% through +4% activation. The trail gives back 10%, 15%, or 20% of peak open profit. Fees and slippage remain 10 bps and 2 bps per side.

## Best full-history marked result

- Activation: **+2%**
- Giveback of peak open profit: **10%**
- Completed trades: **19.0**
- Wins / losses after costs: **19.0 / 0.0**
- Completed-trade win rate: **100.00%**
- Realized equity before the final open position: **$138.09**
- Final marked equity: **$53.00**
- Marked return: **-47.00%**
- Maximum minute-marked drawdown: **-68.27%**

The final position remains open from **2025-10-31 15:09:00+00:00**, entered with **$138.09**, and is worth **$53.00** at the final historical close.

## All 24 combinations

| Rank | Activate | Giveback | Completed | Wins | Losses | Win rate | Open | Final marked $100 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | +2% | 10% | 19 | 19 | 0 | 100.00% | 1 | $53.00 |
| 2 | +2% | 20% | 19 | 19 | 0 | 100.00% | 1 | $52.99 |
| 3 | +2% | 15% | 19 | 19 | 0 | 100.00% | 1 | $52.71 |
| 4 | +1.5% | 10% | 22 | 22 | 0 | 100.00% | 1 | $51.89 |
| 5 | +1.5% | 15% | 22 | 22 | 0 | 100.00% | 1 | $51.73 |
| 6 | +1.5% | 20% | 22 | 22 | 0 | 100.00% | 1 | $51.18 |
| 7 | +1% | 10% | 28 | 28 | 0 | 100.00% | 1 | $48.01 |
| 8 | +1% | 15% | 28 | 28 | 0 | 100.00% | 1 | $47.59 |
| 9 | +1% | 20% | 28 | 28 | 0 | 100.00% | 1 | $47.55 |
| 10 | Immediate | 15% | 378 | 15 | 363 | 3.97% | 1 | $46.42 |
| 11 | Immediate | 10% | 378 | 15 | 363 | 3.97% | 1 | $46.28 |
| 12 | Immediate | 20% | 378 | 15 | 363 | 3.97% | 1 | $46.18 |
| 13 | +3% | 20% | 11 | 11 | 0 | 100.00% | 1 | $45.46 |
| 14 | +2.5% | 20% | 13 | 13 | 0 | 100.00% | 1 | $45.11 |
| 15 | +3.5% | 20% | 9 | 9 | 0 | 100.00% | 1 | $44.76 |
| 16 | +4% | 20% | 7 | 7 | 0 | 100.00% | 1 | $44.33 |
| 17 | +3.5% | 15% | 9 | 9 | 0 | 100.00% | 1 | $43.17 |
| 18 | +3% | 10% | 11 | 11 | 0 | 100.00% | 1 | $42.81 |
| 19 | +3% | 15% | 11 | 11 | 0 | 100.00% | 1 | $42.72 |
| 20 | +2.5% | 10% | 13 | 13 | 0 | 100.00% | 1 | $42.26 |
| 21 | +3.5% | 10% | 9 | 9 | 0 | 100.00% | 1 | $42.14 |
| 22 | +2.5% | 15% | 13 | 13 | 0 | 100.00% | 1 | $41.94 |
| 23 | +4% | 15% | 7 | 7 | 0 | 100.00% | 1 | $41.77 |
| 24 | +4% | 10% | 7 | 7 | 0 | 100.00% | 1 | $41.49 |

## Measurement rule

Completed-trade win rate excludes the final open position. Because no loss or time exit is allowed, a position that never reaches activation remains invested indefinitely and blocks every later signal. Final ranking uses its marked value at the last SOL close; it does not fabricate a sale.
