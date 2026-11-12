# SOL +2%/10% Trail — Protective Stop Grid

## Scope

This experiment keeps the confirmed ±0.2% from-below touch entry, +2% trailing activation, 10% giveback of peak open profit, one 100%-equity position, and realistic fees/slippage. It adds protective stops from −1% through −4% in 0.5-point steps. There is no time exit.

## Best full-history result

- Protective stop: **−4%**
- Final $100 account: **$87.08** (-12.92%)
- Completed trades: **76.0**
- Wins / losses: **51.0 / 25.0**
- Win rate: **67.11%**
- Trailing exits: **51.0**
- Protective or ambiguous stop exits: **25.0**
- Profit factor: **0.871**
- Maximum minute-marked drawdown: **-22.01%**
- Average winner / loser: **+1.86% / -4.21%**
- Earlier / later period return: **-7.40% / -5.96%**

## All stops

| Rank | Stop | Trades | Wins | Losses | Win rate | Trail exits | Stop exits | Final $100 | Return |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | −4% | 76 | 51 | 25 | 67.11% | 51 | 25 | $87.08 | -12.92% |
| 2 | −2.5% | 91 | 51 | 40 | 56.04% | 51 | 40 | $84.13 | -15.87% |
| 3 | −3.5% | 79 | 50 | 29 | 63.29% | 50 | 29 | $84.07 | -15.93% |
| 4 | −3% | 84 | 50 | 34 | 59.52% | 50 | 34 | $82.44 | -17.56% |
| 5 | −2% | 101 | 51 | 50 | 50.50% | 51 | 50 | $82.03 | -17.97% |
| 6 | −1.5% | 120 | 52 | 68 | 43.33% | 52 | 68 | $78.04 | -21.96% |
| 7 | −1% | 147 | 52 | 95 | 35.37% | 52 | 95 | $77.84 | -22.16% |

This is an in-sample stop comparison and has not changed the deployed frozen strategy.
