# ETH Pullback quality filter

## Result

**Reject all three filters; keep the current Pullback rule unchanged.**

| Rule | Profit | vs base | Trades | Economic win rate | Avg economic loss | Ex-Apr/May profit | Ex-Apr/May change | WF change | WF improved | Drawdown | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Current pullback | $430.16 | $+0.00 | 459 (+0) | 71.0% | $-4.55 | $192.48 | $+0.00 | $+0.00 | 0/6 | -9.66% | CONTROL |
| 24h EMA above 6h ago | $423.56 | $-6.61 | 385 (-74) | 75.3% | $-4.52 | $187.43 | $-5.05 | $-21.06 | 0/6 | -6.27% | FAIL |
| 24h EMA above 12h ago | $423.95 | $-6.21 | 401 (-58) | 74.1% | $-4.53 | $187.58 | $-4.91 | $-17.54 | 0/6 | -7.11% | FAIL |
| Reclaim above EMA + previous 5m high | $426.20 | $-3.96 | 453 (-6) | 71.3% | $-4.55 | $190.79 | $-1.69 | $-3.66 | 0/6 | -9.71% | FAIL |

Economic winners are trades above +0.25%; economic losses are below -0.25%. April–May exclusion uses the filled trade's entry month. Filters were tested separately, with unchanged entries and exits for Dip and Mode C and unchanged Pullback exits.
