# ETH monthly controlled-compounding experiment

## Result

**Reject both monthly compounding schedules.**

| Sizing | Profit | vs base | Trades | Avg order | Avg win | Avg loss | Drawdown | Profit/drawdown | WF change | WF improved | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| fixed_100_control | $430.16 | $+0.00 | 459 | $99.62 | $1.88 | $-4.55 | -9.66% | 8.84 | $+0.00 | 0/6 | CONTROL |
| monthly_symmetric_20pct | $495.43 | $+65.26 | 459 | $119.51 | $2.18 | $-5.36 | -9.55% | 8.79 | $+6.39 | 3/6 | FAIL |
| monthly_profit_only_20pct | $495.21 | $+65.04 | 459 | $119.57 | $2.18 | $-5.36 | -9.66% | 8.79 | $+6.68 | 3/6 | FAIL |

Sizes are frozen once per UTC month from marked strategy equity. Existing positions are never resized, and cash remains a hard limit.
