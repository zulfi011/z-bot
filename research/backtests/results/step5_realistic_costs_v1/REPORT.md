# Stage 2 Step 5 — Realistic Trading Costs

## Cost model

Each trade uses the already recorded 2 bps adverse buy fill and 2 bps adverse sell fill. A 10 bps spot fee is then charged on the slipped entry value and another 10 bps on the slipped exit value. There is no leverage, funding, borrowing, or liquidation cost.

## Results after all costs

| Strategy | Trades | Wins | Win rate | Mean raw | After slippage | After fees | Profit factor |
|---|---:|---:|---:|---:|---:|---:|---:|
| Primary | 82 | 45 | 54.88% | +0.614% | +0.573% | +0.372% | 1.336 |
| Control | 117 | 61 | 52.14% | +0.434% | +0.394% | +0.193% | 1.150 |

The primary's average execution drag was 0.241 percentage points per trade: approximately 0.040 from slippage and 0.201 from fees.

## Accounting

The output retains per-unit entry fee, exit fee, entry slippage, exit slippage, cash paid, cash received, and net PnL for every trade. Dollar PnL is deferred until Step 6 defines position size. The illustrative compounded return assumes the full account is reinvested each time and is not yet the final account simulation.

All 199 final net returns matched the independent realistic-cost analysis exactly.
