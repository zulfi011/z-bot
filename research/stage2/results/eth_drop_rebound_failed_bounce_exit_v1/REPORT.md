# ETH drop-rebound failed-bounce time exit

## Result: **KEEP NO TIME EXIT**

Every variant uses the accepted 5%/60m entry, −2% stop, +0.19% arm, +0.30% minimum-net floor and 30% giveback.

| Rule | Filled time exits | Extra trades | Profit | vs base | vs control | Overall WR | Add-on WR | Add-on avg loss | Later vs control | WF vs control | WF wins | Replace? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| no_time_exit_control | 0 | +98 | $456.87 | $+26.71 | $+0.00 | 85.1% | 83.7% | $-0.84 | $+0.00 | $+0.00 | 4/6 | control |
| exit_unarmed_30m | 0 | +98 | $456.87 | $+26.71 | $+0.00 | 85.1% | 83.7% | $-0.84 | $+0.00 | $+0.00 | 4/6 | no |
| exit_unarmed_60m | 0 | +98 | $456.87 | $+26.71 | $+0.00 | 85.1% | 83.7% | $-0.84 | $+0.00 | $+0.00 | 4/6 | no |
| exit_unarmed_180m | 0 | +98 | $456.87 | $+26.71 | $+0.00 | 85.1% | 83.7% | $-0.84 | $+0.00 | $+0.00 | 4/6 | no |

## Current ETH base

Profit **$430.16**, 459 trades and 85.4% win rate.

A time exit replaces the accepted control only if it improves full, later and walk-forward profit, does not reduce add-on win rate or worsen add-on average loss, and retains the original base-safety requirements.

This is local ETH research only. No live bot or server files were changed.
