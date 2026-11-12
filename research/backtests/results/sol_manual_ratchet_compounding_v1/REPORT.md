# SOL manual upward-ratchet compounding replay

Local-only sizing experiment. It starts with one **$500 SOL-only wallet** and five $100 slots. Every new $100 marked-equity high-water profit milestone permanently raises later requested orders by $20. Each actual order uses the lesser of that request and free cash; no leverage or borrowing is used. Current SOL entries/exits and 7.5/2 bps BNB-fee/slippage assumptions are unchanged.

| Sizing | Profit | Ending equity | Trades | Win rate | Avg win | Avg loss | Max drawdown | Order range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed $100 | $81.39 | $581.39 | 316 | 70.9% | $1.23 | $-2.10 | $-45.42 (-9.05%) | $60.87–$100.00 |
| Manual ratchet | $81.39 | $581.39 | 316 | 70.9% | $1.23 | $-2.10 | $-45.42 (-9.05%) | $60.87–$100.00 |

Ratchet profit change: **$+0.00**. Walk-forward: better in **0/6** test windows; combined change **$+0.00**.
