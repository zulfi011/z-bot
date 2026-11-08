# ETH rolling-drop add-on confirmation experiment

## Result: **REJECT**

The current ETH strategy remains unchanged and receives same-minute slot priority.

| Variant | Profit | Change | Trades | Extra | Win rate | Add-on WR | Avg loss | WF change | WF wins | Pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| immediate_addon | $447.06 | $+16.90 | 557 | +98 | 80.4% | 57.1% | $-2.92 | $+7.37 | 3/6 | no |
| green_1m_10m | $429.23 | $-0.93 | 556 | +97 | 81.1% | 60.8% | $-3.05 | $-2.80 | 2/6 | no |
| rebound_025_30m | $427.21 | $-2.95 | 546 | +87 | 80.6% | 55.2% | $-3.01 | $-2.84 | 2/6 | no |
| rebound_050_60m | $432.04 | $+1.88 | 537 | +78 | 81.2% | 56.4% | $-3.11 | $+0.21 | 3/6 | no |

## Current base

Profit **$430.16**, 459 trades, 85.4% headline win rate, average loss **$-4.55**, walk-forward profit **$410.14**.

A variant passes only if it keeps combined win rate at 75%+, adds at least 20 trades, improves full/later/walk-forward profit, improves at least four of six walk-forward windows, and does not worsen average loss or drawdown.

This is local ETH research only; no live files or server deployment were changed.
