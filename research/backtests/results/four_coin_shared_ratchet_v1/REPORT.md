# Four-coin, five-slot shared-pot replay (local only)

## Exact model

- One **$500** wallet; at most **five open positions total** across ETH, TRX, BTC and AAVE.
- Signal order is first-come-first-served. Ties use ETH → TRX → BTC → AAVE.
- Manual sizing starts at $100. Each new $100 marked-equity high-water profit step permanently adds $20 to the requested lot. Actual spending is the smaller of the requested lot and free wallet cash.
- No leverage, borrowing, per-coin reservation, or priority rule. Fees/slippage are 7.5/2 bps per side.
- Common evaluation window: 2024-10-01 to 2026-08-01 (end exclusive). Positions still open at the end are marked closed at the final completed price.

## Result

| Case | Profit | Ending equity | Trades | Win rate | Avg loss | Max drawdown | Orders | Blocked signals |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| eth_only_fixed | $430.16 | $930.16 | 459 | 85.4% | $-4.55 | $-48.66 (-9.66%) | $67.71–$100.00 | 147 |
| eth_only_ratchet | $561.22 | $1061.22 | 459 | 85.4% | $-6.37 | $-86.18 (-9.66%) | $67.71–$200.00 | 147 |
| four_coin_fixed | $673.59 | $1173.59 | 1021 | 85.5% | $-3.93 | $-67.45 (-10.10%) | $78.80–$100.00 | 999 |
| four_coin_ratchet | $1260.03 | $1760.03 | 1021 | 85.5% | $-7.33 | $-143.81 (-12.53%) | $78.80–$360.00 | 999 |


Adding TRX, BTC and AAVE to the ratcheted ETH wallet changed profit by **$+698.81** versus the same ETH-only ratchet control. This is an allocation simulation, not evidence that the current live app already has one global five-slot pool.

## Four-coin ratchet contribution

| Coin | Trades | Profit | Win rate | Average loss | Average order |
|---|---:|---:|---:|---:|---:|
| AAVE | 230 | $278.47 | 80.9% | $-7.09 | $193.73 |
| BTC | 174 | $138.00 | 82.2% | $-5.43 | $172.62 |
| ETH | 328 | $361.72 | 83.2% | $-8.64 | $196.13 |
| TRX | 289 | $481.85 | 93.8% | $-7.18 | $198.76 |
