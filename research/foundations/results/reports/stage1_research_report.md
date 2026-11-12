# V1 Stage 1 Research Report

## 1. Research Objective

Stage 1 investigated whether price interactions with completed-day 7D, 15D and 30D averages show repeatable forward behavior across BTCUSDT, ETHUSDT and SOLUSDT.

This is historical research only. Stage 1 does not constitute a live trading strategy.

## 2. Experiment Scope

- Exchange: Binance
- Market: Spot
- Assets: BTCUSDT, ETHUSDT, SOLUSDT
- Historical base data: 1-minute candles
- Derived timeframes: 1m, 3m, 5m
- Averages: 7D, 15D, 30D
- Touch zones: ±0.5%, ±1.0%, ±1.5%
- Configurations per asset: 27
- Total configurations: 81

All averages use completed previous daily closes, so the average calculations do not use future daily data.

## 3. Metrics Evaluated

- Forward returns at 5m, 15m, 30m, 1h, 4h and 24h
- +0.5%, +1%, +1.5%, +2%, +2.5%, +3% and +5% target reach
- Maximum adverse excursion (MAE)
- Maximum favorable excursion (MFE)
- MFE/MAE balance
- Target-vs-stop first-hit ordering
- Post +2.5% activation continuation
- Profit-giveback trailing behavior
- Bullish, Neutral and Bearish market regimes

## 4. Event Count Definitions

`forward_return_total_event_count` represents all touch events available for forward-return analysis.

`event_count` in the Stage 1 configuration summary represents observations with a valid complete 24-hour research window.

For all 81 configurations, `event_count` matches `return_24h_valid_count`.

## 5. Forward Returns

Forward-return statistics are available independently for every one of the 81 configurations.

### Current leading research candidate

SOLUSDT / 5m / 15D / ±0.5%

| Horizon | Valid events | Median return | Mean return |
| --- | --- | --- | --- |
| 5m | 11,867 | 0.000% | -0.001% |
| 15m | 11,867 | 0.000% | 0.003% |
| 30m | 11,867 | 0.008% | 0.007% |
| 1h | 11,867 | 0.017% | 0.010% |
| 4h | 11,867 | 0.049% | 0.007% |
| 24h | 11,865 | 0.307% | 0.213% |

Forward returns are descriptive outcomes after a touch. They are not equivalent to realized trade returns because Stage 1 does not yet define complete entry and exit state.

## 6. Average Comparison

| Average | +2.5% reach | Median MAE | Median MFE | MFE/MAE | Target-first | Mean metric rank |
| --- | --- | --- | --- | --- | --- | --- |
| 15d | 34.16% | -1.55% | 1.63% | 1.113 | 32.53% | 1.29 |
| 30d | 31.03% | -1.71% | 1.37% | 0.996 | 30.54% | 2.71 |
| 7d | 34.32% | -1.68% | 1.74% | 0.993 | 31.70% | 2.00 |

**Conclusion:** 15D remains the strongest supported primary average. It provides the strongest overall balance rather than merely the largest raw movement.

## 7. Timeframe Comparison

| Timeframe | +2.5% reach | Median MAE | Median MFE | MFE/MAE | Target-first | Median events | Mean metric rank |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5m | 33.09% | -1.65% | 1.63% | 1.040 | 31.62% | 24,935 | 1.86 |
| 1m | 32.98% | -1.64% | 1.63% | 1.039 | 31.51% | 111,573 | 2.00 |
| 3m | 33.02% | -1.65% | 1.63% | 1.039 | 31.54% | 39,754 | 2.14 |

**Conclusion:** 1m, 3m and 5m behave very similarly. The evidence does not justify claiming that 5m is statistically superior.

5m remains the primary operational candidate because it substantially reduces repeated touch observations while retaining nearly the same measured behavior.

## 8. Asset Comparison

| Asset | +2.5% reach | Median MAE | Median MFE | MFE/MAE | Target-first | Post-activation upside | 30% trail median |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SOLUSDT | 41.92% | -1.84% | 1.98% | 1.090 | 38.24% | 2.68% | 2.12% |
| ETHUSDT | 33.02% | -1.65% | 1.63% | 1.007 | 31.54% | 2.12% | 2.18% |
| BTCUSDT | 19.39% | -1.09% | 1.12% | 1.015 | 19.17% | 1.71% | 2.14% |

**Conclusion:** SOLUSDT is the strongest opportunity candidate in Stage 1, particularly for target reach, MFE and post-activation movement.

SOLUSDT is not universally the safest or best asset. BTCUSDT shows materially smaller downside excursions, while ETHUSDT remains an important secondary validation asset.

## 9. Touch-Zone Comparison

| Touch zone | Configurations | Median +2.5% reach | Median MAE | Median MFE | Median MFE/MAE | Median target-first | Median post-activation upside |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ±0.5% | 27 | 32.50% | -1.69% | 1.52% | 1.090 | 30.54% | 2.12% |
| ±1.0% | 27 | 34.16% | -1.68% | 1.64% | 1.041 | 31.70% | 2.11% |
| ±1.5% | 27 | 33.02% | -1.63% | 1.63% | 0.996 | 31.54% | 2.16% |

**Conclusion:** ±0.5% remains the leading touch-zone candidate, particularly for the SOL / 15D setup, but it is not treated as a finalized trading threshold.

## 10. Current Leading Research Configuration

- Asset: SOLUSDT
- Average: 15D
- Timeframe: 5m
- Touch zone: ±0.5%

- Complete 24h events: 11,865
- All forward-return touch events: 11,867
- +2.5% reach probability: 45.933%
- Median time to +2.5%: 548.0 minutes
- Median 24h MAE: -1.849%
- Median 24h MFE: 2.256%
- Median MFE/MAE ratio: 1.220
- +2.5% target before -2.5% stop, all-confirmed basis: 42.555%
- Median post-activation extra upside: 2.835%
- 30% profit-giveback median resolved return: 2.074%

This is a leading hypothesis configuration, not a completed strategy.

## 11. Market-Regime Findings

SOLUSDT / 5m / 15D / ±0.5%:

| Regime | Events | 24h median return | +2.5% reach | Median MAE | Median MFE | MFE/MAE | Target-first decisive | Post-activation upside | 30% trail locked |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Bearish | 2,489 | 0.26% | 55.09% | -2.07% | 2.78% | 1.344 | 59.69% | 2.86% | 2.07% |
| Bullish | 4,309 | 0.12% | 41.73% | -2.14% | 1.67% | 0.782 | 49.60% | 2.51% | 2.08% |
| Neutral | 4,760 | 0.51% | 45.57% | -1.38% | 2.31% | 1.668 | 62.92% | 3.50% | 2.08% |

**Neutral:** strongest balanced behavior, including better MFE/MAE balance, target-first behavior and post-activation continuation.

**Bearish:** strongest rebound/target-reach behavior but accompanied by larger adverse excursions.

**Bullish:** weaker risk/reward balance for this specific average-touch hypothesis.

## 12. +2.5% Activation and Trailing Research

+2.5% remains a useful Stage 2 activation candidate.

A 30% giveback of accumulated profit remains the most practical trailing candidate identified in Stage 1: it greatly reduces the same-candle ambiguity seen with tighter trails while retaining meaningful locked profit.

It is not yet proven to be the mathematically optimal exit.

## 13. Interpretation of the Asset Ranking

Several Stage 1 opportunity metrics are related to one another. Target reach, MFE and target-first behavior all partly reflect the strength and volatility of subsequent price movement.

Therefore SOLUSDT's multiple metric wins should not be treated as completely independent confirmations.

The correct interpretation is that SOLUSDT is the strongest opportunity candidate found by Stage 1, while its higher downside excursion remains an important risk consideration for Stage 2.

## 14. Important Limitations

- Touch-event observations are not independent trades.
- Consecutive candles can represent the same underlying market interaction.
- The ±0.5%, ±1.0% and ±1.5% touch zones are nested and therefore correlated.
- 1m, 3m and 5m represent heavily overlapping underlying market behavior.
- Several opportunity metrics are correlated and should not be treated as independent evidence.
- Same-candle OHLC ambiguity prevents exact intraminute ordering in some trailing and first-hit situations.
- Stage 1 does not yet model actual strategy state, signal deduplication or overlapping positions.
- Stage 1 does not yet model fees, slippage, position sizing, capital allocation or portfolio exposure.
- The current results are based on the researched historical period and still require robust strategy backtesting and out-of-sample validation.

## 15. Stage 2 Research Candidates

- Primary opportunity asset: SOLUSDT
- Secondary validation asset: ETHUSDT
- Lower-volatility reference asset: BTCUSDT
- Primary average: 15D
- Operational timeframe candidate: 5m
- Leading touch-zone candidate: ±0.5%
- Preferred balanced regime candidate: Neutral
- Higher-risk rebound regime: Bearish
- Activation candidate: +2.5%
- Trailing candidate: 30% profit giveback

## 16. Final Stage 1 Conclusion

Stage 1 provides sufficient evidence to continue researching the average-touch hypothesis.

The strongest direction identified is SOLUSDT interacting with the 15D completed-close average. A ±0.5% touch zone and 5-minute operational timeframe are the leading practical candidates, particularly in Neutral market structure.

However, the evidence does not establish SOL / 15D / 5m / ±0.5% as a finished or universally optimal strategy.

Stage 2 must convert these research observations into actual trade-state rules and test whether the apparent edge survives deduplication, entry/exit rules, fees, slippage and out-of-sample evaluation.