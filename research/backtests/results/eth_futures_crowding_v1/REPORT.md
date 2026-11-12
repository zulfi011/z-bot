# ETH futures-crowding sizing experiment

## Result

**Reject both crowding overlays; keep fixed $100 orders.**

| Sizing | Profit | vs base | Profit retained | Avg win | Avg loss | Drawdown | Profit/drawdown | Crowded fills | Their profit | Ex-Apr/May change | WF change | Risk-adjusted WF improved | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Fixed $100 control | $430.16 | $+0.00 | 100.0% | $1.88 | $-4.55 | -9.66% | 8.84 | 0 | $0.00 | $+0.00 | $+0.00 | 0/6 | CONTROL |
| Crowded q90 → $70 | $434.50 | $+4.34 | 101.0% | $1.88 | $-4.49 | -9.59% | 8.93 | 6 | $-9.04 | $+4.34 | $+0.00 | 0/6 | FAIL |
| Crowded q95 → $50 | $437.83 | $+7.67 | 101.8% | $1.88 | $-4.45 | -9.54% | 8.99 | 4 | $-6.89 | $+7.67 | $+0.00 | 0/6 | FAIL |

Every spot signal and exit is unchanged. Size is reduced only when the latest strictly prior ETH perpetual funding rate and causal 24-hour open-interest growth are both positive and above the same trailing 90-day percentile.

The q95 headline gain came from four directly resized fills, all on 1 October 2024. It did not reproduce in any of the six walk-forward windows, so it is not robust enough to replace the baseline.
