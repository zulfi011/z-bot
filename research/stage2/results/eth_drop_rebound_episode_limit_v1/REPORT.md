# ETH drop-rebound episode-limit experiment

## Result: **REJECT**

Both versions use the accepted 5%/60m entry, −2% stop, +0.19% arm,
+0.30% minimum-net floor and 30% giveback.

| Metric | Current ETH base | Unlimited add-on | One per fall episode |
|---|---:|---:|---:|
| Candidate signals | — | 102 | 48 |
| Signals removed | — | 0 | 54 |
| Extra filled trades | — | +98 | +45 |
| Total profit | $430.16 | $456.87 | $442.56 |
| Change vs base | — | $+26.71 | $+12.40 |
| Change vs unlimited | — | — | $-14.31 |
| Overall win rate | 85.4% | 85.1% | 84.9% |
| Add-on win rate | — | 83.7% | 80.0% |
| Add-on average loss | — | $-0.84 | $-1.16 |
| Later change vs unlimited | — | — | $-3.25 |
| Walk-forward change vs unlimited | — | — | $-6.43 |
| WF windows improved vs base | — | 4/6 | 4/6 |

The episode limit replaces the accepted control only if it improves full, later and walk-forward
profit, does not reduce add-on win rate or worsen its average loss, and retains all base-safety rules.

This is local ETH research only. No live bot or server files were changed.
