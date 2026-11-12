# ETH causal volatility-sizing experiment

## Result

**Reject all three sizing schedules; keep fixed $100 orders.**

| Sizing | Profit | vs base | Profit retained | Avg win | Avg loss | Drawdown | Profit/drawdown | Ex-Apr/May change | WF change | Risk-adjusted WF improved | Avg order | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Fixed $100 control | $430.16 | $+0.00 | 100.0% | $1.88 | $-4.55 | -9.66% | 8.84 | $+0.00 | $+0.00 | 0/6 | $99.62 | CONTROL |
| Top 20% → $70 | $423.91 | $-6.26 | 98.5% | $1.83 | $-4.40 | -9.66% | 8.71 | $-6.64 | $+0.34 | 2/6 | $96.15 | FAIL |
| Top 10% → $50 | $421.84 | $-8.32 | 98.1% | $1.85 | $-4.52 | -9.66% | 8.67 | $-6.63 | $-3.38 | 1/6 | $97.33 | FAIL |
| Top 20% → $70; top 10% → $50 | $420.58 | $-9.59 | 97.8% | $1.82 | $-4.39 | -9.66% | 8.64 | $-9.29 | $-1.01 | 2/6 | $95.24 | FAIL |

All 459 signals and exits are unchanged. Current volatility uses the completed prior 24 hours; the 80th and 90th percentile thresholds use only the previous 90 completed UTC days. Smaller orders never create extra slots, leverage, or borrowing.
