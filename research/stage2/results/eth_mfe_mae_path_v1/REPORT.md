# ETH MFE/MAE path experiment

## Result

**Reject both path-failure exits.**

| Rule | Profit | vs base | Trades | Economic win | Avg win | Avg loss | Drawdown | WF change | WF improved | Path exits | Later armed | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | $430.16 | $+0.00 | 459 | 71.0% | $1.88 | $-4.55 | -9.66% | $+0.00 | 0/6 | 0 | 0.0% | CONTROL |
| path_failure_6h | $420.12 | $-10.04 | 466 | 68.9% | $1.90 | $-3.91 | -10.05% | $-7.85 | 2/6 | 18 | 72.2% | FAIL |
| path_failure_12h | $415.36 | $-14.80 | 479 | 66.4% | $1.87 | $-3.36 | -10.33% | $-12.45 | 3/6 | 40 | 62.5% | FAIL |
