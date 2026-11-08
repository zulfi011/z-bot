# ETH drop-rebound minimum-net exit experiment

## Result: **ACCEPT**

All variants are additions behind the unchanged current ETH strategy. A floor becomes active only after its price is actually reached; this avoids assuming an impossible above-market stop fill.

| Variant | Extra trades | Profit | Change | Overall WR | Add-on WR | Add-on avg win | Add-on avg loss | Later | WF change | WF wins | Pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_no_net_floor | +98 | $447.06 | $+16.90 | 80.4% | 57.1% | $0.54 | $-0.32 | $+3.87 | $+7.37 | 3/6 | no |
| minimum_net_0.10pct | +98 | $449.51 | $+19.35 | 83.3% | 73.5% | $0.48 | $-0.59 | $+4.49 | $+9.22 | 4/6 | yes |
| minimum_net_0.20pct | +98 | $453.25 | $+23.08 | 84.4% | 79.6% | $0.47 | $-0.69 | $+5.67 | $+12.47 | 4/6 | yes |
| minimum_net_0.30pct | +98 | $456.87 | $+26.71 | 85.1% | 83.7% | $0.49 | $-0.84 | $+7.41 | $+13.06 | 4/6 | yes |

## Current ETH base

Profit **$430.16**, 459 trades, 85.4% headline win rate, average win **$1.88** and average loss **$-4.55**.

A variant passes only if it keeps overall win rate at 75%+, adds at least 20 trades, improves full/later/walk-forward profit and at least four of six walk-forward windows, without worsening average loss or drawdown.

This is local ETH research only. No live bot or server files were changed.
