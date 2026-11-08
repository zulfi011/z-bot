# Stage 2 Step 3 — Entry Generation

## Result

The frozen entry logic was regenerated causally across all 1,006,560 raw SOLUSDT minutes. The primary produced **420** fills (231 earlier and 189 later). The control produced **490** fills (278 earlier and 212 later). Every candidate status, confirmation time, entry time, raw opening price, and slipped fill matched the validated Stage 1.5 reference.

## Timing and price rules

Only a completed 3-minute or 5-minute candle can confirm an entry. A confirmed order waits for the raw 1-minute opening event at that same closing boundary. The simulated spot buy fills at `raw open × 1.0002`, applying 2 bps of adverse slippage. Fees remain separate for Step 5.

This step generates every qualifying entry independently. Signals that occur while a position is open will be removed only after exits determine the actual occupied interval.

## Validation

- 994 candidate rows matched Stage 1.5.
- 910 entry fills matched Stage 1.5.
- Signal feeds were released only at their closing boundaries.
- The chronological engine processed each raw minute once.
- Stage 1 source files were read-only and are recorded by SHA-256.
