# Stage 2 Step 4 — Exit Execution

## Result

The chronological engine managed each strategy as a separate one-position spot account. It completed **82 primary trades** and **117 control trades**. It ignored 338 primary and 372 control signals received while their positions were open. One final control entry lacked the complete 24-hour path and remains explicitly incomplete.

## Primary exits

The primary keeps its −4% hard stop. Reaching +4% activates the 10% giveback-of-open-profit trail, which begins on the following raw minute using the previously known peak. Results: **24 trailing exits**, **15 hard/ambiguous stops**, and **43 24-hour exits**.

| Period | Trades | Trailing exits | Hard stops | 24h exits |
|---|---:|---:|---:|---:|
| Earlier | 42 | 14 | 9 | 19 |
| Later | 40 | 10 | 6 | 24 |

## Control exits

The control retains its fixed +4% profit target and −4% hard stop. Results: **36 targets**, **27 hard/ambiguous stops**, and **54 24-hour exits**.

| Period | Trades | Profit targets | Hard stops | 24h exits |
|---|---:|---:|---:|---:|
| Earlier | 62 | 20 | 15 | 27 |
| Later | 55 | 16 | 12 | 27 |

## Execution rules

Targets, stops, and trailing levels are calculated from the slipped entry fill. Same-minute conflicts resolve to the hard stop. Stop and trail gaps use the worse of the level or candle open; favorable target gaps use the candle open. Exit fills include 2 bps adverse sell slippage. Trading fees are intentionally deferred to Step 5.

All 199 completed trades matched the independent Stage 1.5/Stage 2 trailing analysis for entry, exit type, duration, raw exit, and slipped exit fill.
