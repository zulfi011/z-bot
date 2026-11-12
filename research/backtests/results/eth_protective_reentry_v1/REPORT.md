# ETH Dip protective-stop re-entry experiment

## Result

**Reject both re-entry windows; keep the current no-re-entry rule.**

| Rule | Profit | vs base | Trades | Economic win rate | Avg win | Avg loss | Drawdown | Re-entry fills | Re-entry profit | Re-entry stops | Ex-Apr/May change | WF change | WF improved | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| No re-entry control | $430.16 | $+0.00 | 459 (+0) | 71.0% | $1.88 | $-4.55 | -9.66% | 0 | $0.00 | 0 | $+0.00 | $+0.00 | 0/6 | CONTROL |
| One re-entry within 24h | $430.16 | $+0.00 | 459 (+0) | 71.0% | $1.88 | $-4.55 | -9.66% | 0 | $0.00 | 0 | $+0.00 | $+0.00 | 0/6 | FAIL |
| One re-entry within 48h | $425.50 | $-4.66 | 460 (+1) | 70.9% | $1.88 | $-4.55 | -9.66% | 1 | $-4.66 | 1 | $-4.66 | $-4.66 | 0/6 | FAIL |

Only Dip protective-stop episodes can re-enter. Each episode gets at most one attempt after a bullish five-minute close above both its original frozen zone top and the prior five-minute high. The parent must have been actually filled and stopped in that replay.
