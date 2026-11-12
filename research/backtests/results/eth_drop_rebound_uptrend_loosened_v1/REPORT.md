# ETH drop-rebound loosened uptrend filters

## Result: **REJECT**

All rows are additions behind the unchanged current ETH strategy.

| Variant | Signals | Extra trades | Profit | Change | Overall WR | Add-on WR | Avg loss | Later | WF change | WF wins | Pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ema_rising_only | 19 | +16 | $435.64 | $+5.47 | 84.6% | 62.5% | $-4.20 | $+0.06 | $+2.00 | 3/6 | no |
| ema_rising_non_bearish | 11 | +8 | $432.35 | $+2.18 | 85.2% | 75.0% | $-4.42 | $+0.24 | $+2.18 | 3/6 | no |
| ema_rising_above_30d | 9 | +6 | $432.10 | $+1.94 | 85.4% | 83.3% | $-4.48 | $+0.00 | $+1.94 | 2/6 | no |

## Current base

Profit **$430.16**, 459 trades, 85.4% headline win rate and average loss **$-4.55**.

A variant passes only if it keeps overall win rate at 75%+, adds at least 20 trades, improves full/later/walk-forward profit and at least four of six walk-forward windows, without worsening average loss or drawdown.

This is local ETH research only. No live bot or server files were changed.
