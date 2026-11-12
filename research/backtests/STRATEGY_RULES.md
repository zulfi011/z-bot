# Frozen Strategy Rules — Stage 2

This document freezes the Stage 1.5 v2 primary candidate and its control for chronological spot backtesting. Stage 2 must implement these rules without tuning them against the same historical results. The machine-readable source is `config/strategies/sol_15d_touch_v1.yaml`.

## Shared Data Rules

Use UTC timestamps and raw 1-minute candles for fills and exit monitoring. Calculate 7-day, 15-day, and 30-day simple averages from completed UTC daily closes only. Attach the latest average already available at each signal candle; future daily closes are prohibited.

A candle touches the 15-day average when its range overlaps the ±0.5% band: `high >= average × 0.995` and `low <= average × 1.005`. Consecutive touching candles form one episode. Only the first candle can originate a signal. “From below” requires the preceding signal-timeframe candle's high to be strictly below its lower band.

## Primary Entry

Trade `SOLUSDT` on 3-minute signal candles. From the first touch candle, find the first bullish candle (`close > open`) no later than the inclusive 30-minute boundary. The search may include the first touch candle and the first candle after the touch run ends; cancel it after that first non-touch candle or when 30 minutes expires. Enter at the raw 1-minute open corresponding to the confirming candle's closing boundary.

Reject a primary signal when, on the first touch candle, `7D average < 15D average < 30D average`. Reject missing market context.

## Control Entry

Use the same rules on 5-minute signal candles and accept every market condition. Run the control separately from the primary so each has its own one-position account.

## Exit and Execution

Model long-only spot trading with no leverage or short selling. Allow one open position per strategy and ignore signals received while it is open. Charge 10 basis points per side and apply 2 basis points of adverse slippage per side.

For the primary, set a −4% hard stop from the actual entry fill. When price first reaches +4%, activate a trailing stop instead of selling. The trail protects 90% of the highest open profit known before the current 1-minute candle, meaning it allows a 10% giveback of open profit. The activation candle cannot trigger the trail because its intraminute price order is unknown. If activation and the hard stop occur in that candle, the stop wins.

A stop or trailing gap fills at the worse of its level or the candle open, before exit slippage and fees. If no exit occurs, sell at the close of the 1,440th raw 1-minute candle, counting the entry minute. The control continues to sell at its fixed +4% target with the same −4% stop and 24-hour cap.

## Research Status

The 4%/10% trail improved primary mean return by 0.014 percentage points earlier and 0.010 later. These small differences were statistically uncertain, and that uncertainty remains recorded in the analysis. The variant is frozen because it improved in both periods and was selected after review. The primary strategy itself remains provisional; Stage 3 paper trading must supply unseen forward evidence.
