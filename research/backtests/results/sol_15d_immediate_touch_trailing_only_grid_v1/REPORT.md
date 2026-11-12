# SOL Immediate Touch, Trailing-Only Exit Grid

> **Superseded:** This run omitted bullish confirmation and does not represent the corrected request. Use `sol_15d_confirmed_trailing_only_grid_v1` instead.

## Rules

Buy at the raw one-minute open immediately after the first completed 3-minute candle touches the ±0.2% zone from below. The existing strong-bearish market filter remains. There is no bullish confirmation, hard stop, or time exit. One position receives 100% of current equity. The only sale is a causal trailing stop after the selected activation threshold. Results include 10 bps fees and 2 bps adverse slippage per side.

## Best full-history marked result

- Activation: **+2%**
- Giveback of peak open profit: **10%**
- Completed trades: **20.0**
- Wins / losses after costs: **20.0 / 0.0**
- Completed-trade win rate: **100.00%**
- Realized equity before the open final position: **$140.27**
- Final marked equity: **$53.84**
- Marked return: **-46.16%**
- Maximum minute-marked drawdown: **-68.28%**

The final position remains open from **2025-10-31 15:09:00+00:00** and is marked at **$53.84** at the last SOL close.

## All combinations

| Rank | Activate | Giveback | Completed | Wins | Losses | Win rate | Open at end | Final marked $100 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | +2% | 10% | 20 | 20 | 0 | 100.00% | 1 | $53.84 |
| 2 | +2% | 15% | 20 | 20 | 0 | 100.00% | 1 | $53.51 |
| 3 | +2% | 20% | 20 | 20 | 0 | 100.00% | 1 | $53.31 |
| 4 | +1.5% | 10% | 22 | 22 | 0 | 100.00% | 1 | $52.02 |
| 5 | +1.5% | 15% | 22 | 22 | 0 | 100.00% | 1 | $51.77 |
| 6 | +1.5% | 20% | 22 | 22 | 0 | 100.00% | 1 | $51.21 |
| 7 | +1% | 10% | 29 | 29 | 0 | 100.00% | 1 | $48.72 |
| 8 | +1% | 20% | 29 | 29 | 0 | 100.00% | 1 | $48.44 |
| 9 | +1% | 15% | 29 | 29 | 0 | 100.00% | 1 | $48.39 |
| 10 | +3% | 20% | 11 | 11 | 0 | 100.00% | 1 | $45.71 |
| 11 | +2.5% | 20% | 13 | 13 | 0 | 100.00% | 1 | $45.06 |
| 12 | +4% | 20% | 7 | 7 | 0 | 100.00% | 1 | $44.57 |
| 13 | +3.5% | 20% | 9 | 9 | 0 | 100.00% | 1 | $44.47 |
| 14 | +3% | 10% | 11 | 11 | 0 | 100.00% | 1 | $42.99 |
| 15 | +3% | 15% | 11 | 11 | 0 | 100.00% | 1 | $42.97 |
| 16 | +3.5% | 15% | 9 | 9 | 0 | 100.00% | 1 | $42.84 |
| 17 | +2.5% | 10% | 13 | 13 | 0 | 100.00% | 1 | $42.07 |
| 18 | +4% | 15% | 7 | 7 | 0 | 100.00% | 1 | $42.02 |
| 19 | +2.5% | 15% | 13 | 13 | 0 | 100.00% | 1 | $41.89 |
| 20 | +3.5% | 10% | 9 | 9 | 0 | 100.00% | 1 | $41.76 |
| 21 | +4% | 10% | 7 | 7 | 0 | 100.00% | 1 | $41.75 |

## Interpretation limit

Completed-trade win rate excludes the final open position. Because this strategy forbids every other exit, an unactivated position can remain invested indefinitely and block all later signals. Final ranking therefore uses marked account value, not a fabricated data-end sale.
