# ETH drop-rebound volatility-adjusted fall experiment

## Result: **KEEP FIXED 5% FALL**

Every variant uses the accepted −2% stop, +0.19% arm, +0.30% minimum-net floor and 30% giveback.

| Entry | Signals | Extra trades | Profit | vs base | vs fixed | Overall WR | Add-on WR | Add-on avg loss | Later vs fixed | WF vs fixed | WF wins | Replace? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fixed_5pct_control | 102 | +98 | $456.87 | $+26.71 | $+0.00 | 85.1% | 83.7% | $-0.84 | $+0.00 | $+0.00 | 4/6 | control |
| fall_2x_hourly_vol | 102 | +98 | $456.87 | $+26.71 | $+0.00 | 85.1% | 83.7% | $-0.84 | $+0.00 | $+0.00 | 4/6 | no |
| fall_3x_hourly_vol | 97 | +93 | $455.25 | $+25.09 | $-1.62 | 85.0% | 82.8% | $-0.84 | $+0.00 | $-1.29 | 4/6 | no |

## Current ETH base

Profit **$430.16**, 459 trades and 85.4% win rate.

A volatility filter replaces the fixed fall only if it improves full, later and walk-forward profit versus the accepted control, does not reduce add-on win rate, keeps at least 20 extra trades and improves at least four of six windows versus the original base.

This is local ETH research only. No live bot or server files were changed.
