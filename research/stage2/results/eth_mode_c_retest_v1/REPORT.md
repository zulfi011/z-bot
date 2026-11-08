# ETH Mode C breakout-and-retest experiment

## Result

**Reject all three retest entries; keep current Mode C unchanged.**

| Rule | Profit | vs base | Trades | Mode C fills | Mode C profit | Economic win rate | Avg economic loss | Drawdown | Ex-Apr/May change | WF change | WF improved | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Current Mode C | $430.16 | $+0.00 | 459 (+0) | 45 | $30.79 | 71.0% | $-4.55 | -9.66% | $+0.00 | $+0.00 | 0/6 | CONTROL |
| Retest ±0.10% | $421.38 | $-8.78 | 445 (-14) | 32 | $23.19 | 71.2% | $-4.58 | -10.02% | $-10.27 | $-2.15 | 3/6 | FAIL |
| Retest ±0.25% | $429.71 | $-0.45 | 455 (-4) | 42 | $31.44 | 71.4% | $-4.55 | -9.82% | $-1.72 | $+4.33 | 5/6 | FAIL |
| Retest ±0.50% | $430.31 | $+0.14 | 456 (-3) | 43 | $32.04 | 71.5% | $-4.55 | -9.82% | $-1.12 | $+3.82 | 4/6 | FAIL |

Each retest rule uses the original frozen Mode C band, waits at most six hours, permits one entry per band, and buys after a completed bullish five-minute reclaim. All exits and non-Mode-C rules are unchanged.
