# TRX manual upward-ratchet compounding replay

## Exact model

- Start with a **$500 TRX-only wallet**, five configured **$100** lots, and no leverage.
- At every new marked-equity high-water profit milestone of $100, increase the requested lot permanently by $20: $100 → $120 → $140 and so on.
- The configured size never falls. A later order spends the smaller of the configured lot and actual free cash, so a loss can shrink the final remaining order.
- Same current TRX signals and exits; BNB fee 7.5 bps and slippage 2 bps per side.

## Full-period result

| Sizing | Profit | Ending equity | Trades | Win rate | Avg win | Avg loss | Max drawdown | Order range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed $100 | $301.48 | $801.48 | 333 | 93.7% | $1.17 | $-2.99 | $-20.44 (-3.69%) | $100.00–$100.00 |
| Manual ratchet | $372.99 | $872.99 | 333 | 93.7% | $1.47 | $-4.05 | $-22.98 (-3.69%) | $100.00–$160.00 |

The ratchet changed profit by **$+71.51**, and improved **1/6** walk-forward test windows (combined change **$+1.67**).
