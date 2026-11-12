# ETH time-to-arm experiment

## Result

**Reject every unconditional unarmed time-stop.**

| Rule | Profit | vs base | Trades | Economic win | Avg win | Avg loss | Drawdown | WF change | WF improved | Timeout fills | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | $430.16 | $+0.00 | 459 | 71.0% | $1.88 | $-4.55 | -9.66% | $+0.00 | 0/6 | 0 | CONTROL |
| unarmed_3h | $39.26 | $-390.90 | 604 | 29.0% | $1.08 | $-0.75 | -9.36% | $-320.22 | 0/6 | 459 | FAIL |
| unarmed_6h | $235.96 | $-194.21 | 585 | 39.3% | $1.54 | $-0.95 | -6.81% | $-167.53 | 0/6 | 361 | FAIL |
| unarmed_12h | $313.87 | $-116.29 | 551 | 49.0% | $1.69 | $-1.49 | -6.23% | $-108.21 | 0/6 | 226 | FAIL |
| unarmed_24h | $342.42 | $-87.75 | 517 | 55.1% | $1.79 | $-2.22 | -8.53% | $-60.45 | 1/6 | 133 | FAIL |
| unarmed_48h | $397.23 | $-32.93 | 482 | 65.8% | $1.86 | $-3.50 | -9.70% | $-14.52 | 2/6 | 39 | FAIL |

## What historically happened to filled trades still unarmed

| Still unarmed after | Trades | Later armed | Eventual economic winners | Eventual stops | Direct P&L if exited there |
|---|---:|---:|---:|---:|---:|
| 3h | 346 | 82.1% | 69.7% | 17.9% | $-459.42 |
| 6h | 284 | 79.9% | 68.3% | 20.1% | $-387.75 |
| 12h | 193 | 76.7% | 66.3% | 23.3% | $-303.07 |
| 24h | 126 | 78.6% | 69.0% | 21.4% | $-288.62 |
| 48h | 39 | 79.5% | 69.2% | 20.5% | $-209.26 |

The direct P&L column ignores replacement trades; the portfolio table above includes freed-slot effects and is the decision source.
