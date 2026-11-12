# ETH fee-mode and break-even-floor experiment

## Result: MAINTAINING THE BNB RESERVE IS BEST

| Scenario | Profit | Change vs original | Floor exits | Negative floor exits | Floor-exit P&L |
|---|---:|---:|---:|---:|---:|
| Original: BNB fee + 0.19% floor | $430.16 | $0.00 | 49 | 0 | $0.96 |
| BNB missing; old 0.19% floor | $406.90 | $-23.26 | 49 | 49 | $-1.46 |
| USDT-fee-aware 0.24% floor | $408.66 | $-21.51 | 52 | 0 | $1.01 |
| USDT floor + 2bps buffer | $406.04 | $-24.12 | 56 | 0 | $2.19 |
| USDT + 5bps slippage; old floor | $379.02 | $-51.14 | 49 | 49 | $-4.35 |
| USDT + 5bps slippage; 0.30% floor | $377.43 | $-52.73 | 61 | 0 | $1.18 |

## What changed

- Losing the BNB discount while keeping the old floor reduces total profit by **$23.26**.
- At normal 2bps slippage, changing the USDT-fee floor from 0.19% to 0.24% recovers **$1.75** and prevents all 49 floor exits from being small losses.
- The extra 2bps buffer performs **$-0.86** versus the same-cost old floor and exits more trades early. It is not supported.
- Under the 5bps slippage stress, the 0.30% floor prevents negative floor exits but total profit is **$377.43** because higher costs affect every trade.

## BNB reserve

- One $100 ETH round trip uses approximately **$0.15** of BNB fees.
- Five simultaneous ETH lots require at least **$0.75** of BNB for their round trips.
- A simple two-times safety reserve is **$1.50** of BNB.

## Decision

Keep the trading rules unchanged and maintain the BNB reserve. Also report all `break_even` exits as **floor exits**, never as profitable winners. A fee-aware 0.24% floor is a sensible fallback when USDT fees are expected, but it still finishes **$21.51 below the BNB baseline** because the higher fee applies to every trade. Do not add the extra floor buffer from this test.
