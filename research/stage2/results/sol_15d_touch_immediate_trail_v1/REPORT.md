# SOL 15-day Touch with Immediate 15% Profit Trail

## Rules tested

This is a historical experiment and does not change the deployed frozen strategy. It uses completed 3-minute candles, a ±0.2% touch zone approached from below, the existing bullish-candle confirmation within 30 minutes, and the existing strong-bearish regime rejection. Entry uses the raw one-minute open at the confirmation boundary with 2 bps adverse slippage.

Only one long spot position may be open. Each entry allocates 100% of current equity. A −4% emergency stop and 24-hour maximum hold remain. Trailing activates when a post-entry candle first trades strictly above the slipped entry price. Starting with the following candle, the stop retains 85% of the highest open profit known before that candle. Fees are 10 bps per side.

## Result

- Starting equity: **$100.00**
- Ending equity: **$38.86**
- Net return: **-61.14%**
- Completed trades: **387** (16.85 per month)
- Wins / losses: **15 / 372**
- Net win rate: **3.88%**
- Gross win rate before fees and slippage: **69.51%**
- Hypothetical ending equity without either cost: **$98.36**
- Trailing activations / trailing exits: **382 / 382**
- Protective and ambiguous stops: **5**
- Time exits: **0**
- Maximum minute-marked drawdown: **-61.14%**
- Fees / slippage: **$50.90 / $10.18**
- Profit factor: **0.037**

## Interpretation

The win rate is measured after fees and slippage. Because the trail begins after any positive movement and keeps 85% of open profit, many grossly positive exits can still be net losses after the 24 bps modeled round-trip friction. The minute account curve supplies the drawdown and final marked-equity figures.
