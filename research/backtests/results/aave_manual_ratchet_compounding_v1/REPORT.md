# AAVE manual upward-ratchet compounding replay

Local-only sizing experiment. It starts with one **$500 AAVE-only wallet** and five $100 slots. Every new $100 marked-equity high-water profit milestone permanently raises later requested orders by $20. Each actual order uses the lesser of that request and free cash; no leverage or borrowing is used. Current AAVE entries/exits and 7.5/2 bps BNB-fee/slippage assumptions are unchanged.

| Sizing | Profit | Ending equity | Trades | Win rate | Avg win | Avg loss | Max drawdown | Order range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed $100 | $195.94 | $695.94 | 342 | 81.3% | $1.64 | $-4.08 | $-54.35 (-9.09%) | $91.54–$100.00 |
| Manual ratchet | $215.92 | $715.92 | 342 | 81.3% | $1.77 | $-4.33 | $-54.35 (-9.09%) | $91.54–$140.00 |

Ratchet profit change: **$+19.98**. Walk-forward: better in **0/6** test windows; combined change **$+0.00**.
