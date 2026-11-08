# Stage 1.5 Step 6 — Robustness and Candidate Selection

## Purpose and frozen design

This final Stage 1.5 step applies realistic sensitivity checks to the complete Step 5 grid. It does not change touch generation, entries, market context, stops, or exits. Four predeclared condition variants are evaluated separately: all entries, bullish regime, approach from below, and rising average.

Each setup allows one open position at a time, keeping the earliest eligible signal and ignoring new signals until its actual exit. Results are tested at 0%, 0.10%, and 0.20% assumed round-trip cost. Selection uses the conservative 0.20% result, earlier and later periods, quarterly consistency, worst-decile outcome, adjacent timeframe/zone behavior, and seven-day block resampling.

A provisional candidate must have at least 100 opportunities and 40 non-overlapping trades in each period; positive raw mean and median in both; positive non-overlapping mean after 0.20% cost in both; at least 60% positive quarters; worst-decile mean no lower than -5%; and a majority of nearby parameter settings positive in both periods. A robust candidate must additionally have a positive 95% block interval in both periods.

This is a historical selection exercise. The later period was already visible during Stage 1 and is not untouched out-of-sample evidence.

## Main SOL reference audit

| asset | timeframe | average_type | touch_zone | policy | condition_variant | strategy | entries_earlier | entries_later | nonoverlap_trades_earlier | nonoverlap_trades_later | nonoverlap_net_0_2_mean_pct_earlier | nonoverlap_net_0_2_mean_pct_later | median_pct_earlier | median_pct_later | positive_quarters_pct | nonoverlap_expected_shortfall_10_pct_earlier | nonoverlap_expected_shortfall_10_pct_later | positive_neighbors_earlier | positive_neighbors_later | neighbor_count | net_0_2_ci95_low_earlier | net_0_2_ci95_low_later | robust_selection |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | bullish_regime | trail_50_no_stop | 239 | 152 | 37 | 27 | 0.3070 | 0.0293 | 1.4031 | 0.9952 | 57.1429 | -5.1020 | -4.7108 | 2 | 1 | 2 | — | — | False |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | all_entries | target_4_stop_4 | 568 | 577 | 87 | 92 | -0.1056 | -0.0245 | 0.1251 | 0.8454 | 44.4444 | -4.0000 | -4.0000 | 0 | 0 | 2 | — | — | False |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | all_entries | time_1440_no_stop | 568 | 577 | 76 | 89 | 0.1799 | -0.1144 | 0.0857 | 0.5125 | 33.3333 | -7.0485 | -5.3666 | 1 | 0 | 2 | — | — | False |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | all_entries | trail_50_no_stop | 568 | 577 | 96 | 101 | 0.0459 | -0.1491 | 1.3123 | 1.2578 | 44.4444 | -7.1565 | -5.1744 | 0 | 0 | 2 | — | — | False |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | all_entries | time_1440_stop_4 | 568 | 577 | 82 | 89 | -0.0073 | -0.1608 | -0.0605 | 0.5125 | 44.4444 | -4.0000 | -4.0000 | 1 | 0 | 2 | — | — | False |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | bullish_regime | target_4_stop_4 | 239 | 152 | 33 | 24 | 0.0520 | -0.1679 | 1.3776 | 0.7465 | 42.8571 | -4.0000 | -4.0000 | 1 | 0 | 2 | — | — | False |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | bullish_regime | time_1440_stop_4 | 239 | 152 | 32 | 24 | -0.2107 | -0.2351 | 0.5336 | 0.7465 | 42.8571 | -4.0000 | -4.0000 | 0 | 0 | 2 | — | — | False |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | bullish_regime | time_1440_no_stop | 239 | 152 | 30 | 24 | 0.1113 | -0.3239 | 0.7755 | 0.7465 | 42.8571 | -5.8448 | -4.7108 | 2 | 0 | 2 | — | — | False |

## ETH trailing candidate across timeframes

| asset | timeframe | average_type | touch_zone | policy | condition_variant | strategy | entries_earlier | entries_later | nonoverlap_trades_earlier | nonoverlap_trades_later | nonoverlap_net_0_2_mean_pct_earlier | nonoverlap_net_0_2_mean_pct_later | median_pct_earlier | median_pct_later | positive_quarters_pct | nonoverlap_expected_shortfall_10_pct_earlier | nonoverlap_expected_shortfall_10_pct_later | positive_neighbors_earlier | positive_neighbors_later | neighbor_count | net_0_2_ci95_low_earlier | net_0_2_ci95_low_later | robust_selection |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETHUSDT | 1m | 15d | 0.5000 | first_touch_0m | all_entries | trail_50_stop_4 | 1153 | 1209 | 91 | 101 | -0.2895 | -0.2195 | 0.2333 | 0.6571 | 55.5556 | -4.0000 | -4.0000 | 0 | 0 | 2 | — | — | False |
| ETHUSDT | 3m | 15d | 0.5000 | first_touch_0m | all_entries | trail_50_stop_4 | 688 | 714 | 90 | 102 | -0.4779 | -0.0880 | 0.2491 | 0.5512 | 44.4444 | -4.0000 | -4.0000 | 0 | 0 | 3 | — | — | False |
| ETHUSDT | 5m | 15d | 0.5000 | first_touch_0m | all_entries | trail_50_stop_4 | 544 | 552 | 91 | 100 | -0.3271 | -0.1846 | 0.1032 | 0.5337 | 55.5556 | -4.0000 | -4.0000 | 0 | 0 | 2 | — | — | False |

## Provisional selections

19 of 24,624 evaluated combinations pass every non-bootstrap gate. The leading 20 by their weaker period's net mean are shown.

| asset | timeframe | average_type | touch_zone | policy | condition_variant | strategy | entries_earlier | entries_later | nonoverlap_trades_earlier | nonoverlap_trades_later | nonoverlap_net_0_2_mean_pct_earlier | nonoverlap_net_0_2_mean_pct_later | median_pct_earlier | median_pct_later | positive_quarters_pct | nonoverlap_expected_shortfall_10_pct_earlier | nonoverlap_expected_shortfall_10_pct_later | positive_neighbors_earlier | positive_neighbors_later | neighbor_count | net_0_2_ci95_low_earlier | net_0_2_ci95_low_later | robust_selection |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOLUSDT | 5m | 15d | 0.5000 | bullish_candle_30m | from_below | target_4_stop_4 | 278 | 211 | 62 | 55 | 0.2087 | 0.2401 | 0.3690 | 1.3138 | 77.7778 | -4.0000 | -4.0000 | 1 | 1 | 2 | -0.6053 | -0.6883 | False |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | from_below | target_4_stop_4 | 302 | 234 | 62 | 56 | 0.2119 | 0.1688 | 0.3161 | 1.2864 | 66.6667 | -4.0000 | -4.0000 | 1 | 1 | 2 | -0.6020 | -0.7119 | False |
| SOLUSDT | 3m | 15d | 1.5000 | first_touch_0m | bullish_regime | target_1_5_no_stop | 290 | 184 | 55 | 43 | 0.0984 | 0.1466 | 1.5000 | 1.5000 | 71.4286 | -4.3847 | -3.9908 | 2 | 3 | 3 | -0.5328 | -0.8601 | False |
| SOLUSDT | 1m | 15d | 1.5000 | first_touch_0m | bullish_regime | target_1_5_no_stop | 518 | 329 | 60 | 45 | 0.2477 | 0.0892 | 1.5000 | 1.5000 | 71.4286 | -4.4273 | -4.1359 | 2 | 2 | 2 | -0.3883 | -0.9226 | False |
| ETHUSDT | 1m | 15d | 1.0000 | bullish_candle_30m | bullish_regime | time_480_no_stop | 418 | 330 | 70 | 50 | 0.2479 | 0.0760 | 0.3585 | 0.1853 | 71.4286 | -3.5776 | -1.8043 | 2 | 2 | 3 | -0.3551 | -0.3515 | False |
| ETHUSDT | 1m | 15d | 1.0000 | bullish_candle_30m | bullish_regime | time_480_stop_4 | 418 | 330 | 70 | 50 | 0.2227 | 0.0760 | 0.3585 | 0.1853 | 71.4286 | -3.6772 | -1.8043 | 2 | 2 | 3 | -0.3905 | -0.3515 | False |
| SOLUSDT | 1m | 15d | 1.5000 | bullish_candle_30m | bullish_regime | target_1_5_no_stop | 507 | 317 | 59 | 44 | 0.2039 | 0.0721 | 1.5000 | 1.5000 | 71.4286 | -4.4638 | -4.1295 | 2 | 2 | 2 | -0.3221 | -0.9728 | False |
| ETHUSDT | 3m | 15d | 1.0000 | bullish_candle_30m | bullish_regime | time_480_stop_4 | 244 | 214 | 69 | 48 | 0.0936 | 0.0697 | 0.4211 | 0.3097 | 85.7143 | -3.7388 | -1.7514 | 3 | 3 | 4 | -0.5468 | -0.3152 | False |
| ETHUSDT | 3m | 15d | 1.0000 | bullish_candle_30m | bullish_regime | time_480_no_stop | 244 | 214 | 69 | 48 | 0.1090 | 0.0697 | 0.4211 | 0.3097 | 71.4286 | -3.6824 | -1.7514 | 3 | 2 | 4 | -0.5558 | -0.3152 | False |
| ETHUSDT | 5m | 15d | 1.0000 | bullish_candle_30m | bullish_regime | time_480_stop_4 | 185 | 162 | 68 | 46 | 0.0622 | 0.0473 | 0.3695 | 0.2453 | 71.4286 | -4.0000 | -1.8564 | 2 | 2 | 3 | -0.5535 | -0.2562 | False |
| SOLUSDT | 5m | 15d | 0.5000 | bullish_candle_30m | from_below | target_3_stop_4 | 278 | 211 | 67 | 56 | 0.0467 | 0.0995 | 1.4852 | 1.4946 | 66.6667 | -4.0000 | -4.0000 | 1 | 1 | 2 | -0.6539 | -0.7285 | False |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | from_below | target_3_stop_4 | 302 | 234 | 67 | 57 | 0.0692 | 0.0449 | 1.1432 | 1.4052 | 66.6667 | -4.0000 | -4.0000 | 1 | 1 | 2 | -0.6364 | -0.7640 | False |
| ETHUSDT | 5m | 7d | 0.5000 | first_touch_0m | from_below | trail_40_stop_4 | 486 | 506 | 106 | 103 | 0.0937 | 0.0375 | 0.7168 | 0.5554 | 66.6667 | -4.0000 | -4.0000 | 1 | 1 | 2 | -0.5745 | -0.5996 | False |
| SOLUSDT | 5m | 15d | 0.5000 | bullish_candle_30m | from_below | target_5_stop_4 | 278 | 211 | 62 | 53 | 0.0335 | 0.1656 | 0.0857 | 0.9670 | 66.6667 | -4.0000 | -4.0000 | 1 | 1 | 2 | -0.7765 | -0.6962 | False |
| SOLUSDT | 5m | 15d | 0.5000 | first_touch_0m | from_below | target_5_stop_4 | 302 | 234 | 62 | 54 | 0.0330 | 0.1581 | 0.0857 | 0.9791 | 66.6667 | -4.0000 | -4.0000 | 1 | 1 | 2 | -0.7796 | -0.6709 | False |
| ETHUSDT | 5m | 7d | 0.5000 | first_touch_0m | from_below | time_1440_stop_4 | 486 | 506 | 100 | 97 | 0.0477 | 0.0250 | 0.0933 | 0.1681 | 66.6667 | -4.0000 | -4.0000 | 1 | 1 | 2 | -0.7997 | -0.6506 | False |
| ETHUSDT | 3m | 7d | 0.5000 | bullish_candle_30m | from_below | time_1440_stop_4 | 575 | 615 | 99 | 99 | 0.0212 | 0.0608 | 0.1446 | 0.2415 | 66.6667 | -4.0000 | -4.0000 | 2 | 2 | 3 | -0.8197 | -0.6006 | False |
| SOLUSDT | 5m | 15d | 0.5000 | bullish_candle_30m | from_below | trail_50_stop_4 | 278 | 211 | 67 | 58 | 0.0058 | 0.0983 | 1.3336 | 1.3520 | 66.6667 | -4.0000 | -4.0000 | 1 | 1 | 2 | -0.7207 | -0.5745 | False |
| ETHUSDT | 5m | 7d | 0.5000 | bullish_candle_30m | from_below | time_1440_stop_4 | 445 | 475 | 100 | 97 | 0.0965 | 0.0030 | 0.1344 | 0.1861 | 66.6667 | -4.0000 | -4.0000 | 2 | 1 | 2 | -0.7771 | -0.6639 | False |

## Robust selections

0 combinations also have a positive cost-adjusted seven-day block interval in both periods.

No combination passes the full robust-selection rule.

Because configurations share candles and many candidates were inspected, the provisional list is a shortlist for forward validation rather than proof of independent edges.

## Validation and preservation

The audit starts from 300,626 inherited episode-entry rows and evaluates one-position sequencing from actual exit durations. Unit tests cover overlap boundaries, cost application, conditions, compounding drawdown, and deterministic block intervals. Candidate cardinality, quarter reconstruction, neighbor counts, selected-event reconstruction, CSV/Parquet round trips, and source hashes are checked.

Before/after SHA-256 confirms 439 prior files are unchanged. The selected-event audit contains 2,533 rows and all outputs are isolated under Step 6 paths.

## Final Stage 1.5 decision

No strategy is historically robust enough to approve for trading: all block intervals include zero in at least one period. The original unfiltered SOL / 15D / 5m / ±0.5% setup and the ETH / 15D / ±0.5% trailing candidate are rejected from the Stage 2 shortlist because their one-position mean after 0.20% cost is negative in the later or both periods.

Select SOL / 15D / 5m / ±0.5%, approach from below, 30-minute bullish-candle entry, +4% target, and -4% stop as the primary provisional Stage 2 candidate. It retains 62 earlier and 55 later non-overlapping trades, averages +0.209% and +0.240% per trade after the 0.20% cost assumption, and has positive quarterly means in 7 of 9 quarters. Carry the first-touch version of the same setup as an entry sensitivity control; it averages +0.212% and +0.169% after cost.

Carry two distinct secondary families: SOL / 15D / 3m / ±1.5% in a bullish regime with first-touch entry and +1.5% target; and ETH / 15D / 3m / ±1.0% in a bullish regime with 30-minute bullish-candle entry and an 8-hour exit. Their weaker-period cost-adjusted means are +0.098% and +0.070%. Nearby timeframe variants are positive, which is why these families remain useful sensitivity candidates.

These four selections are forward-test candidates, not validated strategies. The primary candidate's block-interval lower bounds are -0.605% earlier and -0.688% later, so Stage 2 must use genuinely unseen data, one-position execution, and exchange-specific costs before any deployment decision.

## Artifacts

`selection.csv` contains every candidate and gate. `provisional_shortlist.csv`, `stage2_candidate_shortlist.csv`, `quarterly.csv`, and `validation.csv` provide the audit trail. `selected_candidate_events.parquet` reconstructs non-overlapping trades for shortlisted candidates. `SUCCESS.json` records completion. Run `python -B -m src.research.stage15_robustness.run` to reproduce into a new directory.
