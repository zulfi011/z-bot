# Stage 2 Step 8: Trade Records

## Purpose

This step creates one auditable ledger row for every completed trade selected by the frozen two-position, 25%-per-entry spot portfolio. Records are available as CSV for inspection and Parquet for later calculations.

Each row includes entry and exit times, SOL quantity, dollar allocation, raw prices, slipped fill prices, entry and exit fees, slippage, exit reason, holding time, gross return, net return, and net dollar profit.

## Results

| Strategy | Trades | Wins | Losses | Win rate | Average size | Fees | Slippage | Net profit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Primary | 152 | 82 | 70 | 53.95% | $25.35 | $7.71 | $1.54 | +$8.33 |
| Control | 209 | 106 | 103 | 50.72% | $24.57 | $10.27 | $2.05 | +$2.74 |

Primary exits consisted of 42 trailing stops, 30 protective stops, and 80 time exits. Its average holding time was 1,057 minutes, or about 17.6 hours. The median was the full 24-hour limit.

The primary produced $17.59 before execution costs. Across all trades, fees removed $7.71 and slippage removed $1.54, leaving $8.33 net profit.

## Validation

All 361 combined records have unique signal IDs. For every trade:

`exit cash received - entry cash paid = net profit`

The primary ledger's 152 records and +$8.33 summed profit exactly match the Step 7 account. The control ledger also matches. All timestamps, durations, fees, returns, and cash flows were independently recalculated before saving.

## Simple Explanation

The ledger works like a receipt book. One example records how much SOL was bought, the price paid, when it was sold, why it closed, all costs, and the money gained or lost. Adding every primary receipt together gives the same final account result: $100 became $108.33.
