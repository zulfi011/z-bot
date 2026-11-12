# V1 Stage 2 Backtesting Report

## Decision

**GO WITH GUARDRAILS for simulated paper trading. NO-GO for real-money trading.**

The primary strategy is ready to be tested against live market data without capital. It is not yet proven strongly enough for real money. Its historical edge is positive but small, and prior statistical confidence intervals crossed zero.

## Frozen Paper Strategy

- Trade SOLUSDT spot, long only; no leverage or shorting.
- Use the 3-minute touch-from-below signal around the completed-close 15-day SMA with a ±0.5% zone.
- Require a bullish confirmation within 30 minutes and reject the strongly bearish 7D < 15D < 30D condition.
- Enter at the next signal boundary with adverse slippage.
- Use a -4% protective stop and a 24-hour maximum hold.
- At +4% open profit, activate a trail that gives back 10% of the peak open profit.
- Allow at most two positions; allocate 25% of current marked equity to each.
- Baseline execution assumes 10 bps fee and 2 bps slippage per side.

## Baseline Performance

| Metric | Primary | Control |
|---|---:|---:|
| Starting equity | $100.00 | $100.00 |
| Final equity | $108.33 | $102.74 |
| Net PnL | +$8.33 | +$2.74 |
| Trades | 152 | 209 |
| Win rate | 53.95% | 50.72% |
| Profit factor | 1.18 | 1.04 |
| Average trade return | +0.231% | +0.072% |
| Worst trade | -4.21% | -4.21% |
| Maximum drawdown | -12.16% | -15.24% |

The primary won 82 of 152 trades. Its lowest marked equity was $89.08. The largest drawdown took approximately nine months to recover, showing that profitable results may still include long weak periods.

## Period and Cost Robustness

At baseline costs, the primary returned +3.76% in the earlier period and +4.41% in the later period. Under conservative 15 bps fees and 5 bps slippage per side, it remained positive at **+0.62% earlier** and **+1.61% later**. The control lost money in both conservative periods.

The primary beat the control in all 15 matched strategy, period, and cost comparisons. Under severe 20/10 bps costs, the primary lost **-6.15%**, so its advantage is sensitive to poor execution.

## Validation Evidence

- 1,006,560 raw one-minute candles processed chronologically.
- 20 future-data access probes blocked.
- All 361 primary and control exits independently reconstructed from raw candles.
- Fees, slippage, and cash flows recalculated for all 361 trades.
- 2,013,120 account rows reconciled with an economically zero maximum error.
- Two-position, spot-cash, and conservative same-candle rules passed.
- Baseline cost comparison exactly reproduced the final performance result.

## Risks and Limits

The strategy was selected after substantial historical refinement, creating selection-bias risk. One-minute OHLC cannot reproduce order-book depth, latency, outages, or exact intraminute order. Modeled costs consumed much of the gross advantage. The 1.18 baseline profit factor and 8.33% return over roughly 23 months leave little room for worse live execution.

## Paper-Trading Gate

Run the frozen rules without changes for at least 180 calendar days and 50 completed trades. Before considering real capital, require positive net PnL, profit factor above 1.0, drawdown no worse than 15%, average round-trip execution cost no higher than 40 bps, and zero strategy-rule mismatches. Any strategy change restarts the paper sample.

## Simple Example

Historically, the primary changed $100 into $108.33. Under conservative costs it changed $100 into only $102.25, while the control lost money. This shows a small advantage that needs a live-data test.

The simple result is: **Stage 2 passed and the primary may move to simulated paper trading. Do not use real money yet. Paper trading must show that the small historical advantage survives real signals, latency, and execution costs.**
