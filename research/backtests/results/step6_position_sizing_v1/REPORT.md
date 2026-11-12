# Stage 2 Step 6 — Position Sizing

## Method

All variants start with $100 and replay the same chronological, after-cost trades. Fixed sizing requests $25, $50, or $100 per trade and caps the request at current cash. Equity sizing invests 25%, 50%, or 100% of current equity. Risk sizing targets 0.5%, 1%, or 2% of equity at the planned stop.

The −4% stop becomes a **4.2110% planned cash loss** after exit slippage and both fees. Therefore the three risk settings allocate approximately 11.87%, 23.75%, and 47.49% of equity. Gaps can still exceed the planned risk.

## Primary full-history results

| Sizing | Final equity | PnL | Return | Realized drawdown | Mean allocation | Fees paid |
|---|---:|---:|---:|---:|---:|---:|
| equity_100% | $130.84 | $+30.84 | +30.84% | -17.73% | 100.00% | $18.54 |
| equity_25% | $107.69 | $+7.69 | +7.69% | -4.70% | 25.00% | $4.24 |
| equity_50% | $115.44 | $+15.44 | +15.44% | -9.21% | 50.00% | $8.74 |
| fixed_$100 | $129.12 | $+29.12 | +29.12% | -17.63% | 88.91% | $15.98 |
| fixed_$25 | $107.63 | $+7.63 | +7.63% | -4.75% | 24.29% | $4.11 |
| fixed_$50 | $115.27 | $+15.27 | +15.27% | -9.42% | 47.40% | $8.22 |
| risk_0.5% | $103.64 | $+3.64 | +3.64% | -2.25% | 11.87% | $1.98 |
| risk_1% | $107.30 | $+7.30 | +7.30% | -4.46% | 23.75% | $4.02 |
| risk_2% | $114.66 | $+14.66 | +14.66% | -8.77% | 47.49% | $8.28 |

## Interpretation

Higher allocation produced more profit and more drawdown because every variant used the same trades. The 100% equity variant is the most aggressive. Risk-based sizing ties exposure directly to the known stop: 1% account risk uses about 23.75% of equity per trade, while keeping the rest in cash.

The **1% risk** variant is the balanced provisional candidate. It ended at **$107.30**, with **+$7.30 PnL** and **−4.46% maximum realized drawdown**. When each historical period was independently reset to $100, it ended at **$103.61 earlier** and **$103.57 later**, so the result did not depend on only one period. A gap through the stop can still lose more than the planned 1%.

For comparison, 100% equity ended at **$130.84** but exposed the account to a **−17.73% realized drawdown**. The 0.5% risk variant limited realized drawdown to **−2.25%** and ended at **$103.64**.

Drawdown here uses equity after each completed trade. Step 7 will add minute-by-minute mark-to-market equity, which can reveal deeper temporary drawdowns while positions are open.

Every allocation was capped at available cash. No leverage, borrowing, short selling, or simultaneous position was used.
