# Stage 1.5 Step 2 — Entry Conditions

## Objective and frozen design

Compare long-entry conditions across every one of the 81 Stage 1 configurations. SOL / 15D / 5m / ±0.5% is a reference, not a restriction. No stop, exit, regime-filter, or portfolio optimization is performed.

Seven entry rules: first touch; bullish candle (close > open); close above the current average; reclaim (previous close <= previous average AND current close > current average); bullish close above the average; close above the zone upper boundary; close above the first touch candle high. All comparisons are strict. A close above the average need not be a crossing; reclaim does.

Confirmation may occur on the first touch candle, a later touching candle, or the first non-touch candle. A pending confirmation is cancelled after that first exit candle. Wait limits are 15, 30 and 60 elapsed minutes after the first candle closes; 30 minutes is the prespecified main comparison. First touch has no wait. Daily average changes are used only when available; they can create an average-reclaim condition. No future episode end, peak, outcome, or best candle enters selection.

There are 19 policies (one baseline plus six confirmations × three waits), or 1,539 setup-policy combinations. Each original episode has a candidate row under every policy, including cancellations and expiry.

## Execution and comparable baseline

A decision is available only after its timeframe candle closes. Entry uses the open of the next raw 1-minute candle, with zero latency/slippage as a research assumption. Forward horizons end at the close of minute H from entry; the first entry minute is included. MAE/MFE and diagnostic +2.5% target versus five fixed stops are recomputed from that actual entry price. Same-minute target/stop ordering remains ambiguous.

The Step 1 baseline used the touch candle close and open-anchored forward returns. Therefore its old numbers must not be compared directly with delayed entries. step1_baseline_bridge.csv shows the timing/repricing difference on matched eligible episodes; the comparisons below use a newly computed first-touch baseline.

## Cohorts, denominators, and robustness

All policies share the same eligible origin episodes: exclude left-censored starts and require 60 minutes plus 24h of subsequent raw data. Earlier period ends before 2025-09-01 UTC; later begins on that date. Origins whose maximum evaluation window crosses the split are purged. This later period is a historical stability check, not untouched out-of-sample data: Stage 1 already examined the full history.

Entry rate uses every eligible episode as denominator. Return/MAE/MFE/target metrics condition on entered episodes with complete 24h data. Both all-entry and decisive-only first-hit denominators are retained. Paired change compares the confirmed entry against first touch on exactly the same origin episodes, separating the effect of timing from selecting different episodes. Paired differences compare equal-duration 24h windows from each entry, whose ending timestamps differ.

The cash-for-skips mean assigns zero to unconfirmed opportunities to expose frequency loss; it is not a portfolio return or a capital model. Seven-calendar-day block bootstrap intervals for paired means are exploratory; they do not remove all dependence or adjust for testing many setups. Approach direction and origin regime are descriptive slices, not new entry filters. Monthly summaries and 15/60-minute waits check sensitivity.

## Reference configuration — full eligible history

| rule | entries | confirmation_rate_pct | return_1440m_mean_pct | return_1440m_median_pct | mae_1440m_median_pct | mfe_mae_ratio | first_2.5_target_decisive_pct | paired_mean_24h_change_pp |
|---|---|---|---|---|---|---|---|---|
| break_touch_high | 449 | 39.2140 | 0.4236 | 0.3490 | -1.9023 | 1.3066 | 56.2327 | -0.2847 |
| bullish_above_average | 681 | 59.4760 | 0.1788 | 0.1681 | -1.8560 | 1.3286 | 58.6338 | -0.1335 |
| bullish_candle | 1075 | 93.8865 | 0.3327 | 0.3691 | -2.0200 | 1.2296 | 57.2609 | -0.0274 |
| close_above_average | 711 | 62.0961 | 0.1721 | 0.2285 | -1.9294 | 1.2889 | 59.0991 | -0.0836 |
| close_above_zone | 540 | 47.1616 | 0.2131 | 0.1723 | -1.8557 | 1.3206 | 60.1449 | -0.1758 |
| first_touch | 1145 | 100.0000 | 0.3364 | 0.3749 | -2.0200 | 1.2406 | 57.7093 | 0.0000 |
| reclaim_average | 172 | 15.0218 | -0.1795 | -0.1591 | -2.2206 | 1.2282 | 54.7297 | -0.2765 |

## Reference configuration — later period

| rule | entries | confirmation_rate_pct | return_1440m_mean_pct | return_1440m_median_pct | mae_1440m_median_pct | mfe_mae_ratio | first_2.5_target_decisive_pct | paired_mean_24h_change_pp |
|---|---|---|---|---|---|---|---|---|
| break_touch_high | 217 | 37.6083 | 0.2907 | 0.6367 | -1.4867 | 1.5976 | 60.5096 | -0.2700 |
| bullish_above_average | 369 | 63.9515 | 0.2378 | 0.4675 | -1.5865 | 1.5184 | 63.6719 | -0.0998 |
| bullish_candle | 540 | 93.5875 | 0.3528 | 0.5462 | -1.5731 | 1.5275 | 61.7801 | -0.0221 |
| close_above_average | 384 | 66.5511 | 0.1391 | 0.4387 | -1.5632 | 1.4837 | 63.7037 | -0.0674 |
| close_above_zone | 301 | 52.1664 | 0.1969 | 0.3920 | -1.5607 | 1.5463 | 66.3507 | -0.1422 |
| first_touch | 577 | 100.0000 | 0.3185 | 0.5125 | -1.5613 | 1.4730 | 61.9855 | 0.0000 |
| reclaim_average | 73 | 12.6516 | 0.0026 | 0.4429 | -1.8488 | 1.3941 | 58.6207 | -0.2850 |

## Cross-grid rule effects — later period, main wait

| rule | configurations | median_confirmation_rate_pct | configs_mean_return_higher | configs_mae_improved | median_paired_mean_change_pp | positive_paired_ci95_count |
|---|---|---|---|---|---|---|
| break_touch_high | 81 | 41.7202 | 34 | 31 | -0.1721 | 0 |
| bullish_above_average | 81 | 50.5300 | 46 | 40 | -0.0486 | 0 |
| bullish_candle | 81 | 95.4774 | 39 | 31 | -0.0059 | 0 |
| close_above_average | 81 | 52.1201 | 46 | 39 | -0.0384 | 0 |
| close_above_zone | 81 | 41.9660 | 41 | 41 | -0.0766 | 0 |
| first_touch | 81 | 100.0000 | 0 | 0 | 0.0000 | 0 |
| reclaim_average | 81 | 2.7187 | 49 | 23 | -0.4480 | 0 |

The higher-return count compares each rule with its own setup baseline. Positive paired CI counts are unadjusted exploratory diagnostics, not discoveries or proof of an edge.

## Candidate screen across all assets, averages, timeframes, and zones

69 main-wait/baseline combinations pass the prespecified descriptive screen: at least 100 entries in each period and positive mean AND median 24h returns in both periods. The threshold controls tiny samples but is not a statistical power guarantee. The table is sorted by later-period mean return for inspection, not an optimality or tradability ranking.

| asset | timeframe | average_type | touch_zone | rule | entries_earlier | entries_later | return_1440m_mean_pct_earlier | return_1440m_mean_pct_later | return_1440m_median_pct_later | mae_1440m_median_pct_later |
|---|---|---|---|---|---|---|---|---|---|---|
| SOLUSDT | 1m | 15d | 0.5000 | first_touch | 1183 | 1233 | 0.3280 | 0.4067 | 0.5703 | -1.5919 |
| SOLUSDT | 5m | 15d | 0.5000 | bullish_candle | 535 | 540 | 0.3125 | 0.3528 | 0.5462 | -1.5731 |
| ETHUSDT | 5m | 7d | 0.5000 | close_above_zone | 495 | 389 | 0.1255 | 0.3275 | 0.0217 | -1.8688 |
| ETHUSDT | 5m | 7d | 1.0000 | break_touch_high | 452 | 338 | 0.2678 | 0.3215 | 0.1550 | -1.6511 |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch | 568 | 577 | 0.3545 | 0.3185 | 0.5125 | -1.5613 |
| ETHUSDT | 5m | 7d | 0.5000 | bullish_candle | 1005 | 929 | 0.3225 | 0.2750 | 0.1255 | -1.6885 |
| ETHUSDT | 5m | 7d | 0.5000 | first_touch | 1070 | 981 | 0.2865 | 0.2741 | 0.1214 | -1.6504 |
| BTCUSDT | 1m | 30d | 0.5000 | bullish_candle | 781 | 824 | 0.2528 | 0.2730 | 0.0483 | -1.2749 |
| ETHUSDT | 5m | 7d | 0.5000 | close_above_average | 666 | 546 | 0.2562 | 0.2687 | 0.0414 | -1.8165 |
| ETHUSDT | 5m | 7d | 0.5000 | bullish_above_average | 622 | 520 | 0.2257 | 0.2454 | 0.0397 | -1.8051 |
| BTCUSDT | 1m | 30d | 0.5000 | first_touch | 806 | 855 | 0.2548 | 0.2353 | 0.0117 | -1.3291 |
| BTCUSDT | 3m | 30d | 1.5000 | bullish_above_average | 297 | 176 | 0.1816 | 0.2264 | 0.4512 | -1.0124 |

## Validation and preservation

Synthetic tests cover signal timing, crossing versus level conditions, fixed first-touch-high references, exit-candle cancellation, elapsed wait limits, future-data invariance, exact next-open pricing, window endpoints, ambiguous barriers, and incomplete data. Every episode has 19 unique candidates. Per dataset, 40 sampled episodes × 19 policies are independently replayed with a scalar scanner; 160 complete entry timestamps are checked against direct raw-price window scans. Signal bounds, cohort completeness, matched baseline coverage, exact Parquet and numeric CSV round trips are checked.

Before/after SHA-256 confirms 315 protected Stage 1 and Step 1 files are unchanged. New outputs reside only under the Step 2 data/results directories. A completed run has SUCCESS.json.

## Limitations and next decision

These remain overlapping research observations. Nested zones, averages, timeframes and adjacent episodes share data; confirmation can select volatility and change the sample. Fees, slippage, latency, stop fills, position overlap, sizing and portfolio return are not modeled. Larger forward return or MFE alone does not establish an entry rule. Prefer improvements that survive matched-episode comparisons, downside checks, coverage, both historical periods, and nearby wait settings. Keep alternative configurations under consideration.

This run stops at entry-condition analysis. No rule is promoted to a final strategy and no further refinement step is executed.

## Step 2 decision

Retain first-touch-at-next-open as the primary entry baseline. None of the tested confirmation rules showed a reliable improvement from waiting on matched episodes across the grid; every confirmation rule had a negative median paired 24h timing effect in the later period, and none produced a positive exploratory paired interval in any configuration. Bullish-candle confirmation is the only practical secondary candidate: it keeps roughly 95% of episodes, loses very little from waiting, and was slightly stronger in the later period for the reference setup. Stronger confirmations discarded many episodes and their attractive conditional subsets did not survive the matched timing comparison. Reclaim-average is rejected for this formulation due to very low coverage and weak reference results. This decision applies only to entry refinement; it does not establish profitability.

## Reproduction and artifacts

`python -B -m src.research.stage15_entry.run` (uses the repository Python environment; refuses existing output directories). `python -B -m pytest tests/test_stage15_entries.py` runs synthetic tests.

summary.csv: all 1,539 combinations × three periods. comparisons.csv: own-baseline differences. rule_effects.csv: cross-grid counts and paired effects. leaderboard.csv: all main candidates and screening flags. segments.csv: approach/regime slices. monthly.csv: monthly outcomes. step1_baseline_bridge.csv: matched timing bridge. exclusions.csv and validation.csv: eligibility and audit results. Per-dataset Parquet files retain every candidate, including failed confirmations, signal/entry timestamps, entry price, and recomputed outcomes.
