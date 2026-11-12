# ETH continuous-compounding replay

## Result

This is a local ETH-only sizing simulation. It does not modify the live bot or server.

| sizing | profit | ending_equity | return_pct | trades | average_order | minimum_order | maximum_order | average_win | average_loss | drawdown_pct | drawdown_usd | profit_factor |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed_$100_control | 430.1634 | 930.1634 | 86.0327 | 459 | 99.6178 | 67.7100 | 100.0000 | 1.8751 | -4.5505 | -9.6622 | -48.6618 | 2.4109 |
| continuous_20pct_equity | 600.6584 | 1100.6584 | 120.1317 | 459 | 157.7361 | 92.2460 | 221.9868 | 2.6990 | -6.8258 | -9.5033 | -92.1866 | 2.3134 |

## What continuous compounding means here

Start with **$500** and five **$100** slots. Before each new entry, the simulator values all earlier closed trades and marks any open ETH positions at the entry minute's completed close. The new order is **20% of that equity**. Therefore a loss lowers later order sizes and a gain raises them. Open positions are never resized; available cash and five slots remain hard limits.

The compounded replay changed full-period profit by **$170.49** and ending equity by the same amount. It improved **4/6** walk-forward windows (walk-forward combined change **$23.77**).

This does not prove a better strategy: it changes risk exposure. Compare the higher/lower dollar drawdown and the profit-to-drawdown relationship before any live sizing change.
