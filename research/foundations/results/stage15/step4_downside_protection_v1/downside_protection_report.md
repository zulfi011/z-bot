# Stage 1.5 Step 4 — Downside Protection

## Scope and execution

This step tests fixed long-position stops across all 81 configurations for the retained first-touch entry and the secondary 30-minute bullish-candle entry. Stops are 0.5%, 1%, 1.5%, 2%, 2.5%, 3%, 4%, and 5% below the actual inherited entry price. No market condition is adopted as a filter; bullish-regime results are retained as a descriptive secondary segment.

Each stop watches raw 1-minute lows from the entry minute through minute 1,440. A triggered stop fills at the worse of its threshold and that minute's open, which accounts for a gap through the stop. An untriggered trade exits at the existing minute-1,440 close. Fees, slippage beyond gap handling, overlapping positions, profit exits, and trailing rules are outside this step.

## Reference setup: SOL / 15D / 5m / ±0.5%, first-touch entry

| period | protection | entries | stop_hit_pct | return_24h_mean_pct | return_24h_median_pct | return_24h_p10_pct | expected_shortfall_10_pct | mean_change_vs_hold_pp | stopped_then_24h_positive_pct | stopped_before_later_target_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| all | no_stop | 1145 | 0.0000 | 0.3364 | 0.3749 | -3.9486 | -6.9040 | 0.0000 | — | — |
| all | stop_0.5 | 1145 | 85.2402 | 0.1460 | -0.5000 | -0.5000 | -0.5001 | -0.1903 | 46.9262 | 38.2172 |
| all | stop_1 | 1145 | 71.7031 | 0.2024 | -1.0000 | -1.0000 | -1.0000 | -0.1340 | 38.3678 | 28.7454 |
| all | stop_1.5 | 1145 | 59.9127 | 0.2199 | -1.5000 | -1.5000 | -1.5000 | -0.1165 | 30.6122 | 21.5743 |
| all | stop_2 | 1145 | 50.3930 | 0.2565 | -2.0000 | -2.0000 | -2.0000 | -0.0798 | 23.9168 | 16.4645 |
| all | stop_2.5 | 1145 | 39.3013 | 0.4054 | -0.0877 | -2.5000 | -2.5000 | 0.0690 | 13.5556 | 11.7778 |
| all | stop_3 | 1145 | 32.4017 | 0.3823 | 0.0753 | -3.0000 | -3.0000 | 0.0460 | 11.0512 | 10.2426 |
| all | stop_4 | 1145 | 22.1834 | 0.4232 | 0.2961 | -4.0000 | -4.0000 | 0.0869 | 4.3307 | 4.7244 |
| all | stop_5 | 1145 | 13.7118 | 0.3879 | 0.3190 | -5.0000 | -5.0000 | 0.0515 | 2.5478 | 5.0955 |
| earlier | no_stop | 568 | 0.0000 | 0.3545 | 0.0857 | -4.1821 | -7.4887 | 0.0000 | — | — |
| earlier | stop_0.5 | 568 | 87.8521 | 0.1439 | -0.5000 | -0.5000 | -0.5000 | -0.2106 | 44.4890 | 43.0862 |
| earlier | stop_1 | 568 | 77.6408 | 0.1758 | -1.0000 | -1.0000 | -1.0000 | -0.1787 | 37.8685 | 32.1995 |
| earlier | stop_1.5 | 568 | 68.3099 | 0.1470 | -1.5000 | -1.5000 | -1.5001 | -0.2075 | 31.4433 | 25.2577 |
| earlier | stop_2 | 568 | 58.8028 | 0.1820 | -2.0000 | -2.0000 | -2.0000 | -0.1724 | 24.2515 | 18.8623 |
| earlier | stop_2.5 | 568 | 46.8310 | 0.3224 | -1.1637 | -2.5000 | -2.5000 | -0.0321 | 15.4135 | 15.0376 |
| earlier | stop_3 | 568 | 38.7324 | 0.3012 | -0.6532 | -3.0000 | -3.0000 | -0.0533 | 13.6364 | 14.0909 |
| earlier | stop_4 | 568 | 24.4718 | 0.4624 | -0.0605 | -4.0000 | -4.0000 | 0.1079 | 6.4748 | 7.9137 |
| earlier | stop_5 | 568 | 16.1972 | 0.4159 | 0.0674 | -5.0000 | -5.0000 | 0.0614 | 3.2609 | 8.6957 |
| later | no_stop | 577 | 0.0000 | 0.3185 | 0.5125 | -3.6380 | -6.2810 | 0.0000 | — | — |
| later | stop_0.5 | 577 | 82.6690 | 0.1482 | -0.5000 | -0.5000 | -0.5001 | -0.1704 | 49.4759 | 33.1237 |
| later | stop_1 | 577 | 65.8579 | 0.2285 | -1.0000 | -1.0000 | -1.0000 | -0.0900 | 38.9474 | 24.7368 |
| later | stop_1.5 | 577 | 51.6464 | 0.2917 | -1.5000 | -1.5000 | -1.5000 | -0.0269 | 29.5302 | 16.7785 |
| later | stop_2 | 577 | 42.1144 | 0.3298 | -0.1754 | -2.0000 | -2.0000 | 0.0113 | 23.4568 | 13.1687 |
| later | stop_2.5 | 577 | 31.8891 | 0.4871 | 0.3896 | -2.5000 | -2.5000 | 0.1686 | 10.8696 | 7.0652 |
| later | stop_3 | 577 | 26.1698 | 0.4623 | 0.4536 | -3.0000 | -3.0000 | 0.1437 | 7.2848 | 4.6358 |
| later | stop_4 | 577 | 19.9307 | 0.3847 | 0.5125 | -4.0000 | -4.0000 | 0.0661 | 1.7391 | 0.8696 |
| later | stop_5 | 577 | 11.2652 | 0.3603 | 0.5125 | -5.0000 | -5.0000 | 0.0418 | 1.5385 | 0.0000 |

`stopped_then_24h_positive_pct` is the share of stopped trades whose original 24-hour close was positive. `stopped_before_later_target_pct` is the share stopped before price later reached +2.5%. These expose the opportunity cost of protection. Same-minute target/stop order remains explicitly ambiguous.

## Reference bullish-regime segment — full history

| protection | entries | stop_hit_pct | return_24h_mean_pct | return_24h_median_pct | return_24h_p10_pct | expected_shortfall_10_pct | mean_change_vs_hold_pp | stopped_then_24h_positive_pct | stopped_before_later_target_pct |
|---|---|---|---|---|---|---|---|---|---|
| no_stop | 391 | 0.0000 | 0.9561 | 0.7603 | -2.8940 | -3.9406 | 0.0000 | — | — |
| stop_0.5 | 391 | 86.4450 | 0.0334 | -0.5000 | -0.5000 | -0.5002 | -0.9227 | 53.2544 | 42.6036 |
| stop_1 | 391 | 74.4246 | -0.0047 | -1.0000 | -1.0000 | -1.0000 | -0.9608 | 47.0790 | 34.0206 |
| stop_1.5 | 391 | 59.3350 | 0.1531 | -1.5000 | -1.5000 | -1.5000 | -0.8030 | 37.9310 | 27.5862 |
| stop_2 | 391 | 50.1279 | 0.2024 | -2.0000 | -2.0000 | -2.0000 | -0.7536 | 30.6122 | 20.4082 |
| stop_2.5 | 391 | 37.8517 | 0.4185 | 0.2415 | -2.5000 | -2.5000 | -0.5376 | 21.6216 | 14.8649 |
| stop_3 | 391 | 27.1100 | 0.5057 | 0.4203 | -3.0000 | -3.0000 | -0.4504 | 21.6981 | 16.0377 |
| stop_4 | 391 | 15.0895 | 0.7329 | 0.6503 | -4.0000 | -4.0000 | -0.2232 | 15.2542 | 8.4746 |
| stop_5 | 391 | 6.9054 | 0.8188 | 0.6999 | -3.3014 | -4.5279 | -0.1373 | 11.1111 | 11.1111 |

This segment is descriptive because Step 3 did not validate a hard regime filter.

## Cross-grid later-period evidence: first-touch entry

| protection | configurations | median_stop_hit_pct | configs_mean_improved | median_mean_change_vs_hold_pp | median_stopped_then_positive_pct | median_stopped_before_later_target_pct | median_expected_shortfall_10_pct |
|---|---|---|---|---|---|---|---|
| stop_0.5 | 81 | 82.3755 | 46 | 0.0309 | 40.3226 | 24.3070 | -0.5000 |
| stop_1 | 81 | 66.6667 | 44 | 0.0205 | 30.6288 | 17.5583 | -1.0000 |
| stop_1.5 | 81 | 52.6696 | 44 | 0.0102 | 22.0615 | 12.6344 | -1.5000 |
| stop_2 | 81 | 39.4495 | 49 | 0.0256 | 14.5985 | 9.1205 | -2.0000 |
| stop_2.5 | 81 | 31.8396 | 46 | 0.0430 | 9.6154 | 4.4444 | -2.5000 |
| stop_3 | 81 | 25.8974 | 48 | 0.0332 | 5.6180 | 1.9139 | -3.0000 |
| stop_4 | 81 | 16.0213 | 30 | -0.0149 | 3.0189 | 0.7752 | -4.0000 |
| stop_5 | 81 | 9.3838 | 34 | -0.0068 | 0.0000 | 0.0000 | -4.9573 |

The configurations overlap in episodes and price paths, so counts measure consistency across research setups, not 81 independent experiments.

## Stability screen

102 stop/setup/entry/segment combinations pass the prespecified descriptive screen: at least 100 entries in each period, positive protected mean return in both periods, higher mean return than holding in both periods, and controlled worst-decile loss in both periods. The first 15 are shown.

| asset | timeframe | average_type | touch_zone | policy | segment | protection | entries_earlier | entries_later | mean_change_vs_hold_pp_earlier | mean_change_vs_hold_pp_later | expected_shortfall_10_pct_later | stopped_then_24h_positive_pct_later | positive_block_ci_both |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETHUSDT | 5m | 15d | 1.0000 | first_touch_0m | all_entries | stop_2.5 | 516 | 538 | 0.0949 | 0.4011 | -2.5000 | 4.1916 | False |
| ETHUSDT | 5m | 15d | 1.0000 | bullish_candle_30m | all_entries | stop_2.5 | 481 | 497 | 0.1571 | 0.3990 | -2.5000 | 5.2288 | False |
| ETHUSDT | 3m | 15d | 1.0000 | first_touch_0m | all_entries | stop_2.5 | 654 | 689 | 0.0470 | 0.3722 | -2.5000 | 3.9409 | False |
| ETHUSDT | 1m | 15d | 1.0000 | first_touch_0m | all_entries | stop_2.5 | 1083 | 1142 | 0.0089 | 0.3665 | -2.5000 | 2.9240 | False |
| ETHUSDT | 5m | 15d | 1.0000 | first_touch_0m | all_entries | stop_2 | 516 | 538 | 0.0170 | 0.3547 | -2.0000 | 14.0187 | False |
| SOLUSDT | 5m | 15d | 1.0000 | bullish_candle_30m | all_entries | stop_3 | 582 | 616 | 0.0405 | 0.3523 | -3.0000 | 3.7736 | False |
| ETHUSDT | 3m | 15d | 1.0000 | bullish_candle_30m | all_entries | stop_2.5 | 624 | 658 | 0.0568 | 0.3499 | -2.5000 | 4.5685 | False |
| SOLUSDT | 5m | 15d | 1.0000 | first_touch_0m | all_entries | stop_3 | 615 | 648 | 0.0484 | 0.3442 | -3.0000 | 4.6243 | False |
| ETHUSDT | 5m | 15d | 1.0000 | bullish_candle_30m | all_entries | stop_2 | 481 | 497 | 0.0728 | 0.3420 | -2.0000 | 14.5833 | False |
| ETHUSDT | 1m | 15d | 1.0000 | first_touch_0m | all_entries | stop_2 | 1083 | 1142 | 0.0098 | 0.3322 | -2.0000 | 11.1617 | False |
| ETHUSDT | 5m | 15d | 1.0000 | bullish_candle_30m | all_entries | stop_3 | 481 | 497 | 0.1750 | 0.3186 | -3.0000 | 2.2727 | False |
| ETHUSDT | 5m | 15d | 1.0000 | first_touch_0m | all_entries | stop_3 | 516 | 538 | 0.1439 | 0.3151 | -3.0000 | 2.0833 | False |
| SOLUSDT | 1m | 15d | 1.0000 | bullish_candle_30m | all_entries | stop_3 | 1229 | 1367 | 0.0015 | 0.3143 | -3.0000 | 6.3830 | False |
| SOLUSDT | 1m | 15d | 1.0000 | first_touch_0m | all_entries | stop_3 | 1287 | 1411 | 0.0262 | 0.3116 | -3.0000 | 5.8824 | False |
| ETHUSDT | 3m | 15d | 1.0000 | first_touch_0m | all_entries | stop_3 | 654 | 689 | 0.1165 | 0.2785 | -3.0000 | 2.1978 | False |

Block intervals resample seven-day calendar blocks and are exploratory. They are not adjusted for the many stop/setup comparisons. A positive interval in both periods is stronger descriptive evidence, not proof of a tradable edge.

## Validation and preservation

The run evaluates 300,626 inherited episode-entry rows. Entry prices and 24-hour hold returns are matched back to Step 3, and deterministic samples replay every stop trigger, fill, time, protected return, and +2.5%-target ordering directly from raw candles. Raw grids, completeness, unique keys, Parquet/CSV round trips, and summary cardinality are checked.

Before/after SHA-256 confirms 383 prior files are unchanged. All new artifacts are isolated under Step 4 paths.

## Step 4 decision

For the reference setup, the highest full-history mean among the tested choices is `stop_4` at +0.423%, compared with the no-stop hold result. A 0.5% stop is hit 85.2% of the time; 46.9% of those stopped trades would have recovered to a positive 24-hour close. A 2% stop is hit 50.4% of the time, and 23.9% of those trades would have recovered.

The 4% stop is the leading fixed-stop candidate for the unfiltered reference setup. It improves mean return in both periods: +0.354% to +0.462% earlier and +0.319% to +0.385% later. It also changes the observed worst 24-hour outcomes from -16.11% and -20.31% to -4.00%. The 5% stop also improves the reference mean in both periods, but protects less and has a lower full-history mean than 4%.

Do not adopt a fixed stop as a final rule yet. The reference 4% block intervals include zero in both periods, only 30 of 81 configurations improve with 4% in the later period, and none of the 102 descriptive screen passes has a positive block interval in both periods. Stops at 0.5% through 2% are rejected for the reference setup because they reduce full-history mean return and trigger on 50% to 85% of entries. Every tested stop also reduces the full-history mean in the reference bullish-regime segment, so the 4% candidate applies only to the unfiltered reference sample and must be retested with exits and costs.

This run stops after downside-protection analysis. No Step 5 exit or trailing optimization is performed.

## Artifacts

`protection_summary.csv` contains every setup, period, segment, and stop. `stability_screen.csv` and `cross_grid_effects.csv` contain robustness checks. Per-dataset Parquet files preserve episode-level stop outcomes. `validation.csv` and `SUCCESS.json` record audit completion. Run `python -B -m src.research.stage15_risk.run` to reproduce into a new output directory.
