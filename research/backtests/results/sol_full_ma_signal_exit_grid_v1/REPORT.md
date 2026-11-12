# SOL Full Moving-Average, Signal-Candle, and Exit Grid

## Search

The replay tested all **6,048** requested combinations across 1-, 3-, and 5-minute signal candles; twelve causal rolling simple moving averages from 1 minute through 30 days; immediate through +4% trailing activation; 10%, 15%, and 20% peak-profit giveback; and −1% through −4% protective stops. Every entry uses bullish confirmation, one 100%-equity spot position, realistic fees/slippage, and no time exit.

## Best in-sample result

- Signal candle: **1 minute**
- Rolling average: **30d**
- Trailing activation: **+4%**
- Giveback: **20%**
- Protective stop: **−3%**
- Final $100 account: **$141.32**
- Total return: **+41.32%**
- Completed trades: **50**
- Wins / losses: **28 / 22**
- Win rate: **56.00%**
- Maximum minute-marked drawdown: **-15.11%**
- Earlier / later return: **+54.96% / -8.80%**

## Best candidate positive in both periods

- Signal / average: **5m / 15d**; activation **3.5%**; giveback **15%**; stop **−4%**; full return **+7.44%**; earlier/later **+4.12% / +3.18%**; maximum minute-marked drawdown **−23.10%**.

## Top 20

| Rank | Candle | Average | Activate | Giveback | Stop | Trades | Win rate | Final $100 | Closed DD |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1m | 30d | +4% | 20% | −3% | 50 | 56.00% | $141.32 | -12.25% |
| 2 | 3m | 30d | +4% | 20% | −3.5% | 45 | 60.00% | $140.66 | -10.73% |
| 3 | 3m | 30d | +4% | 20% | −3% | 48 | 56.25% | $140.57 | -10.09% |
| 4 | 3m | 30d | +4% | 20% | −2.5% | 52 | 51.92% | $140.12 | -10.17% |
| 5 | 3m | 30d | +4% | 20% | −4% | 43 | 62.79% | $139.86 | -12.11% |
| 6 | 1m | 30d | +4% | 10% | −3% | 50 | 56.00% | $139.31 | -13.12% |
| 7 | 3m | 30d | +4% | 10% | −3.5% | 45 | 60.00% | $138.88 | -10.73% |
| 8 | 1m | 30d | +4% | 15% | −3% | 50 | 56.00% | $138.76 | -12.25% |
| 9 | 3m | 30d | +4% | 10% | −3% | 48 | 56.25% | $138.32 | -10.29% |
| 10 | 3m | 30d | +4% | 10% | −4% | 43 | 62.79% | $138.11 | -12.57% |
| 11 | 3m | 30d | +4% | 10% | −2.5% | 52 | 51.92% | $137.86 | -9.81% |
| 12 | 3m | 30d | +4% | 15% | −3.5% | 45 | 60.00% | $136.78 | -10.73% |
| 13 | 3m | 30d | +4% | 15% | −3% | 48 | 56.25% | $136.72 | -10.89% |
| 14 | 3m | 30d | +4% | 15% | −4% | 43 | 62.79% | $136.01 | -12.55% |
| 15 | 3m | 30d | +4% | 15% | −2.5% | 52 | 51.92% | $135.45 | -9.99% |
| 16 | 1m | 30d | +4% | 20% | −4% | 46 | 60.87% | $132.90 | -16.10% |
| 17 | 3m | 30d | +3.5% | 20% | −3.5% | 46 | 60.87% | $132.09 | -10.73% |
| 18 | 3m | 30d | +3.5% | 20% | −3% | 49 | 57.14% | $132.01 | -10.52% |
| 19 | 3m | 30d | +3.5% | 20% | −2.5% | 53 | 52.83% | $131.58 | -10.39% |
| 20 | 1m | 30d | +3.5% | 20% | −3% | 51 | 56.86% | $131.55 | -12.79% |

## Research limit

This is a large in-sample parameter search. The highest-ranked row is a hypothesis selected from 6,048 attempts, not a frozen strategy. It requires chronological holdout and forward-paper validation before use.
