# BTC manual upward-ratchet compounding replay

Local-only sizing experiment. It starts with one **$500 BTC-only wallet** and five $100 slots. Every new $100 marked-equity high-water profit milestone permanently raises later requested orders by $20. Each actual order uses the lesser of that request and free cash; no leverage or borrowing is used. Current BTC entries/exits and 7.5/2 bps BNB-fee/slippage assumptions are unchanged.

| Sizing | Profit | Ending equity | Trades | Win rate | Avg win | Avg loss | Max drawdown | Order range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed $100 | $118.73 | $618.73 | 258 | 81.8% | $1.27 | $-3.16 | $-35.58 (-6.00%) | $93.30–$100.00 |
| Manual ratchet | $122.13 | $622.13 | 258 | 81.8% | $1.35 | $-3.46 | $-35.58 (-6.00%) | $93.30–$120.00 |

Ratchet profit change: **$+3.40**. Walk-forward: better in **0/6** test windows; combined change **$+0.00**.
