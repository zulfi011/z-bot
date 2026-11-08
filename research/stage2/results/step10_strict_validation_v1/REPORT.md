# Stage 2 Step 10: Strict Validation

## Purpose

This audit independently checks whether the completed backtest obeys its rules and whether its reported dollars can be trusted. It covers causality, exits, position overlap, execution costs, and account balances.

## Results

| Check | Evidence | Result |
|---|---:|---|
| Look-ahead prevention | 20 prohibited future-data probes | PASS |
| Independent exit replay | 361 trades | PASS |
| Same-candle conservative policy | 3 targeted cases | PASS |
| Position selection and overlap | 361 trades; maximum 2 open | PASS |
| Fees, slippage, and cash flows | 361 trades | PASS |
| Account reconciliation | 2,013,120 minute rows | PASS |

The largest account reconciliation difference was $0.000000000000071, which is ordinary floating-point rounding and economically zero.

## What Was Checked

At a candle's opening, the engine could see only previously closed candles. Attempts to read the current or next candle were blocked. Every selected trade was replayed from raw one-minute OHLC data through a second exit implementation, reproducing its exit time, reason, raw price, slipped fill, and duration.

When a candle could hit both favorable and unfavorable levels, the stop won. A trailing exit could not trigger on its activation candle. Exits were processed before new entries at the same timestamp.

The audit reconstructed entry and exit slippage at 2 bps, fees at 10 bps per side, position quantities, cash paid, cash received, and net profit. It also confirmed that cash never became negative, no leverage appeared, at most two positions were open, and the final account equaled $100 plus all trade profits.

## Simple Explanation

Imagine checking every receipt with a second calculator. We rebuilt each trade from the original candles, recalculated every cost, and then added all cash and open SOL value again. The second calculation produced the same result.

The simple result is: **we found no calculation, future-data, overlap, exit-order, fee, or balance error. The +$8.33 result is correctly calculated under the tested rules. This validation confirms the backtest mechanics, but it does not guarantee future profit.**
