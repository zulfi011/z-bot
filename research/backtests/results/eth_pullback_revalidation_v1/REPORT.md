# ETH pullback clean revalidation

## Original 24h/180m control

**$430.16 profit · 459 trades · 85.4% headline wins · $-4.55 average loss · -9.66% drawdown**

Pullback filled **105 trades**, contributed **$185.47**, and averaged **$1.77 per filled pullback**.

## Frozen neighbourhood

| Variant | Total profit | Change vs control | Ex-Apr/May profit | Ex-Apr/May change | Trades | Pullbacks | Pullback $/trade | Win rate | Avg loss | Drawdown | WF change | WF improved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pullback_24h_240m | $445.87 | $+15.71 | $198.18 | $+5.70 | 453 | 91 | $1.77 | 85.9% | $-4.55 | -9.71% | $+17.49 | 2/6 |
| pullback_24h_180m (control) | $430.16 | $+0.00 | $192.48 | $+0.00 | 459 | 105 | $1.77 | 85.4% | $-4.55 | -9.66% | $+0.00 | 0/6 |
| no_pullback | $428.22 | $-1.95 | $192.09 | $-0.39 | 384 | 0 | $0.00 | 86.7% | $-4.52 | -6.27% | $-16.40 | 1/6 |
| pullback_16h_180m | $426.78 | $-3.38 | $187.31 | $-5.17 | 484 | 129 | $1.09 | 85.1% | $-4.56 | -11.59% | $+2.62 | 4/6 |
| pullback_16h_240m | $423.80 | $-6.37 | $175.97 | $-16.51 | 470 | 108 | $0.94 | 84.9% | $-4.56 | -11.16% | $+1.72 | 3/6 |
| pullback_16h_120m | $416.12 | $-14.05 | $170.71 | $-21.77 | 509 | 159 | $0.84 | 85.1% | $-4.58 | -12.44% | $+1.56 | 4/6 |
| pullback_32h_240m | $415.26 | $-14.91 | $168.54 | $-23.94 | 448 | 79 | $1.59 | 85.0% | $-4.52 | -8.61% | $-12.64 | 3/6 |
| pullback_24h_120m | $411.99 | $-18.17 | $165.86 | $-26.62 | 486 | 135 | $1.24 | 84.6% | $-4.56 | -10.59% | $-12.57 | 3/6 |
| pullback_32h_180m | $409.08 | $-21.08 | $165.34 | $-27.14 | 449 | 88 | $1.83 | 84.9% | $-4.52 | -8.55% | $-19.40 | 2/6 |
| pullback_32h_120m | $390.98 | $-39.19 | $148.68 | $-43.81 | 472 | 114 | $1.27 | 83.7% | $-4.54 | -9.47% | $-36.27 | 1/6 |

April–May exclusion uses the entry month of each actually filled shared-slot trade. It is a concentration diagnostic, not a separately tradable backtest.

## Opportunity per occupied slot in the unchanged control

| Family | Trades | Profit | Profit/trade | Profit/slot-day | Ex-Apr/May $/trade | Ex-Apr/May $/slot-day |
|---|---:|---:|---:|---:|---:|---:|
| pullback | 105 | $185.47 | $1.77 | $1.26 | $0.34 | $0.29 |
| dip | 309 | $213.91 | $0.69 | $0.85 | $0.49 | $0.60 |
| breakout | 45 | $30.79 | $0.68 | $0.83 | $0.68 | $0.84 |

## Decision

**Keep the live 24h/180m rule unchanged for now, but do not grant pullback priority or retune it.** Removing pullback changes portfolio profit by only **$-1.95** and profit excluding April–May by **$-0.39**. Only **2/9** pullback settings beat no-pullback on full history, and only **2/9** beat it after excluding April–May.

Pullback has the best full-history profit per trade and slot-day, but **84.1%** of its labeled profit came from April–May 2025. Outside those months it falls to **$0.29 per occupied slot-day**, below both Dip and Mode C. It therefore does **not** cleanly remain the best ordinary-period opportunity, so this test does not support priority allocation, a separate sleeve, or additional slots.

The August–September 2026 period remains post-selection data and is excluded from acceptance.
