# SOL ±0.2% Touch — Trailing Grid

## Scope

This causal historical grid keeps the modified ±0.2% from-below entry, existing confirmation and market filter, −4% emergency stop, and 24-hour cap. It tests all 45 requested combinations of +1% through +5% activation in 0.5-point steps and 10% through 30% open-profit giveback. One position uses 100% of current equity. Results include 10 bps fees and 2 bps adverse slippage on each side.

## Best in-sample combination

- Activation: **+3%**
- Open-profit giveback: **25%**
- Final $100 account: **$128.16** (+28.16%)
- Trades: **82.0**
- Wins / losses: **44.0 / 38.0**
- Win rate: **53.66%**
- Trailing activations / exits: **35.0 / 33.0**
- Protective or ambiguous stops: **11.0**
- Time exits: **38.0**
- Maximum minute-marked drawdown: **-25.44%**
- Fees / slippage: **$18.14 / $3.63**
- Profit factor: **1.296**
- Earlier-period independent return: **+10.78%** on **46** trades
- Later-period independent return: **+15.69%** on **36** trades

## Top ten

| Rank | Activate | Giveback | Trades | Win rate | Final $100 | Return | Closed DD |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | +3% | 25% | 82 | 53.66% | $128.16 | +28.16% | -23.51% |
| 2 | +3.5% | 25% | 82 | 52.44% | $127.75 | +27.75% | -23.08% |
| 3 | +3% | 15% | 82 | 53.66% | $125.19 | +25.19% | -23.41% |
| 4 | +3% | 10% | 82 | 53.66% | $124.34 | +24.34% | -23.98% |
| 5 | +3.5% | 10% | 82 | 52.44% | $123.87 | +23.87% | -22.02% |
| 6 | +3.5% | 15% | 82 | 52.44% | $123.62 | +23.62% | -22.80% |
| 7 | +3.5% | 30% | 82 | 52.44% | $122.83 | +22.83% | -23.66% |
| 8 | +3% | 20% | 82 | 53.66% | $122.75 | +22.75% | -24.07% |
| 9 | +5% | 25% | 79 | 48.10% | $121.96 | +21.96% | -22.25% |
| 10 | +3% | 30% | 82 | 53.66% | $121.85 | +21.85% | -24.18% |

## Selection limit

The winner is selected on the same history used to compare the grid, so it is an in-sample research candidate. It should not replace the frozen forward strategy until it passes a chronological holdout or forward paper test.
