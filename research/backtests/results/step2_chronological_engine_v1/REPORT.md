# Stage 2 Step 2 — Chronological Engine Validation

The engine processed all **1,006,560** validated SOLUSDT 1-minute candles from **2024-09-01 00:00:00+00:00** through the final close at **2026-08-01 00:00:00+00:00**. Each candle produced one open callback and one close callback in order.

At candle open, strategies receive only the opening price and previously closed history. The full current candle becomes available at its close. Both deliberate future-data requests were rejected, and 21 sampled history-boundary checks passed. Input validation also rejects missing columns, invalid OHLC values, duplicate timestamps, unordered timestamps, and candle gaps.

This step supplies the causal event loop and immutable candle/history views. Trading entries, exits, costs, position sizing, and account balances attach through the strategy callbacks in the following Stage 2 steps.
