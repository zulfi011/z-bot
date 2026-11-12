# ETH drop-rebound higher-low confirmation

## Result: **REJECT**

Both versions use the accepted −2% stop, +0.19% arm, +0.30% minimum net floor and 30% giveback.

| Metric | Current ETH base | Immediate drop control | Higher-low confirmation |
|---|---:|---:|---:|
| Candidate signals | — | 102 | 57 |
| Total trades | 459 | 557 | 513 |
| Extra trades | — | +98 | +54 |
| Profit | $430.16 | $456.87 | $420.69 |
| Change vs base | — | $+26.71 | $-9.48 |
| Change vs immediate | — | — | $-36.19 |
| Overall win rate | 85.4% | 85.1% | 84.8% |
| Add-on win rate | — | 83.7% | 79.6% |
| Add-on average win | — | $0.49 | $0.33 |
| Add-on average loss | — | $-0.84 | $-2.17 |
| Later change vs immediate | — | — | $-9.91 |
| Walk-forward change vs immediate | — | — | $-17.27 |
| WF windows improved vs base | — | 4/6 | 2/6 |

The higher-low rule replaces the immediate entry only if it improves full, later and walk-forward
profit versus the accepted control, does not reduce add-on win rate, keeps at least 20 additional
trades and still improves at least four of six windows versus the original ETH base.

This is local ETH research only. No live bot or server files were changed.
