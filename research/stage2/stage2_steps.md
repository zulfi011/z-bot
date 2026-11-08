Stage 2 should follow these steps:
1. Freeze the strategy rules - done
   Write exact entry, market filter, exit, and timing rules.
2. Build the chronological backtester - done
   Phase-aware open/close replay processes candles in time order and blocks future-candle access.
3. Implement entries - done
   Frozen primary/control signals are generated causally and filled at the next raw 1-minute open with adverse slippage.
4. Implement exits - done
   The primary uses its +4% activation/10% profit-giveback trail; the control uses its fixed +4% target. Both enforce the −4% stop and 24-hour timeout chronologically.
5. Add realistic costs - done
   Every completed trade records 2 bps adverse slippage and a 10 bps fee on both entry and exit, with raw and final returns kept separately.
6. Add position sizing - done
   Tested fixed $25/$50/$100, 25%/50%/100% equity, and 0.5%/1%/2% account-risk sizing from $100, all capped at available spot cash.
6b. Test concurrent positions and allocation together - done
   Tested limits of 1-5 open SOL lots across fixed, equity-percentage, and risk-based sizes. Selected a maximum of two positions using 25% of current equity per entry.
7. Track the account - done
   Recorded cash, marked open position value, realized and unrealized PnL, total equity, and drawdown after every raw one-minute candle for the primary and control.
8. Generate trade records - done
   Saved one reconciled CSV and Parquet record per trade with entry, exit, SOL size, allocation, fill prices, fees, slippage, exit reason, duration, returns, and net profit.
9. Calculate performance - done
   Produced daily equity and drawdown curves plus total PnL, return, win rate, profit factor, average trade, worst trade, and drawdown timing for the primary and control.
10. Validate strictly - done
    Independently confirmed look-ahead blocking, all 361 raw-candle exits, conservative same-candle handling, the two-position limit, every cost calculation, and 2,013,120 account balances.
11. Compare primary and control - done
    Rebuilt both strategies in earlier/later periods under five fee and slippage assumptions. The primary beat the control in all 15 matched comparisons and stayed positive through conservative 15/5 bps costs, but failed severe 20/10 bps stress.
12. Create the Stage 2 report - done
    Approved the frozen primary for simulated paper trading with guardrails. It is not approved for real-money trading because its validated historical edge remains small and cost-sensitive.
