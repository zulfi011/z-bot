# Stage 1.5 Step 3 — Market Conditions

## Scope and causal definitions

This step reassesses conditions at the end of the first-touch candle across all 81 configurations. It carries forward the primary first-touch entry and the secondary 30-minute bullish-candle entry. It does not modify entry execution, stops, exits, position state, or costs.

Conditions are: completed-day average regime; approach from above/below the zone; 24h average slope; sign of the prior 24h return; prior 24h high-low range band; and whether the touch candle closes above the average. Regime-plus-approach is the only interaction searched. Context uses data known by the first-touch decision boundary. No future episode or outcome data enters a condition.

Low/medium/high prior-range thresholds are asset-specific terciles fitted on unique earlier-period origin timestamps and frozen before the later-period evaluation. This prevents later outcomes from defining bands.

## Volatility thresholds

| asset | lower_tercile_pct | upper_tercile_pct | unique_training_origins |
|---|---|---|---|
| BTCUSDT | 2.4808 | 3.9987 | 20501 |
| ETHUSDT | 3.7234 | 5.3501 | 20049 |
| SOLUSDT | 4.6300 | 6.7447 | 20026 |

## Reference setup: SOL / 15D / 5m / ±0.5%, first-touch entry

| condition | value | entries | return_24h_mean_pct | return_24h_median_pct | mae_24h_median_pct | mfe_mae_ratio | target_first_2_5_decisive_pct | mean_advantage_vs_complement_pp |
|---|---|---|---|---|---|---|---|---|
| approach | from_above | 609 | 0.1188 | 0.2285 | -1.8952 | 1.2593 | 59.3952 | -0.4648 |
| approach | from_below | 536 | 0.5836 | 0.4835 | -2.1486 | 1.3145 | 55.9551 | 0.4648 |
| average_slope_24h | falling | 523 | -0.0428 | 0.0820 | -1.9713 | 1.2243 | 56.4792 | -0.6979 |
| average_slope_24h | rising | 612 | 0.6522 | 0.5117 | -2.0624 | 1.2606 | 58.2150 | 0.6784 |
| origin_regime | bearish | 269 | -0.6372 | -0.5752 | -2.6720 | 1.0694 | 56.4103 | -1.2726 |
| origin_regime | bullish | 391 | 0.9561 | 0.7603 | -2.0191 | 1.4579 | 58.2043 | 0.9411 |
| origin_regime | neutral | 457 | 0.2714 | 0.2727 | -1.7371 | 1.2733 | 57.4924 | -0.1081 |
| prior_range_band | high | 304 | 0.4550 | 0.1464 | -2.5057 | 1.2411 | 54.9242 | 0.1616 |
| prior_range_band | low | 483 | 0.3820 | 0.2793 | -1.6699 | 1.1556 | 58.3569 | 0.0789 |
| prior_range_band | medium | 358 | 0.1740 | 0.4835 | -1.9966 | 1.3089 | 59.4502 | -0.2362 |
| prior_return_sign | nonpositive | 584 | 0.2830 | 0.3742 | -1.9347 | 1.2427 | 56.4835 | -0.1090 |
| prior_return_sign | positive | 561 | 0.3919 | 0.4092 | -2.1172 | 1.2968 | 58.9404 | 0.1090 |
| touch_close_side | above_average | 616 | 0.2075 | 0.2817 | -1.8960 | 1.2853 | 60.2128 | -0.2789 |
| touch_close_side | at_or_below_average | 529 | 0.4864 | 0.4536 | -2.1530 | 1.2817 | 55.0228 | 0.2789 |

The advantage column compares a condition with all other values of the same condition. It describes selection, not the benefit of delaying entry. A positive value means the selected condition had a larger mean 24h return than its complement.

## Cross-grid later-period evidence: first-touch entry

| condition | value | configurations | median_entry_share_pct | configs_positive_mean | configs_mean_beats_complement | median_mean_advantage_vs_complement_pp | median_mfe_mae_ratio |
|---|---|---|---|---|---|---|---|
| approach | from_above | 81 | 48.6111 | 46 | 46 | 0.0487 | 1.0863 |
| approach | from_below | 81 | 51.3889 | 31 | 35 | -0.0487 | 0.8926 |
| average_slope_24h | falling | 81 | 53.4783 | 30 | 40 | -0.0016 | 0.9657 |
| average_slope_24h | rising | 81 | 46.5217 | 33 | 41 | 0.0016 | 0.9109 |
| origin_regime | bearish | 81 | 30.8530 | 26 | 17 | -0.4206 | 0.7778 |
| origin_regime | bullish | 81 | 25.0427 | 51 | 58 | 0.3167 | 1.0279 |
| origin_regime | neutral | 81 | 42.2336 | 46 | 57 | 0.2247 | 0.9933 |
| prior_range_band | high | 81 | 24.9615 | 38 | 33 | -0.1447 | 0.8376 |
| prior_range_band | low | 81 | 43.2718 | 38 | 45 | 0.0677 | 1.1399 |
| prior_range_band | medium | 81 | 30.7967 | 37 | 36 | -0.0186 | 0.8534 |
| prior_return_sign | nonpositive | 81 | 48.6741 | 51 | 47 | 0.0976 | 0.9157 |
| prior_return_sign | positive | 81 | 51.3259 | 25 | 34 | -0.0976 | 1.0263 |
| touch_close_side | above_average | 81 | 48.7316 | 46 | 45 | 0.0517 | 1.0844 |
| touch_close_side | at_or_below_average | 81 | 51.2684 | 30 | 36 | -0.0517 | 0.8872 |

Cross-grid counts are descriptive and share market observations across configurations.

## Stability screen across every configuration

151 setup-entry-condition combinations pass the prespecified descriptive screen: at least 100 entries in both periods, positive mean and median return in both, MFE/MAE above one in both, and mean return above the condition's complement in both. The first 15 by later-period complement advantage are shown.

| asset | timeframe | average_type | touch_zone | rule | condition | value | entries_earlier | entries_later | return_24h_mean_pct_earlier | return_24h_mean_pct_later | return_24h_median_pct_later | mae_24h_median_pct_later | mean_advantage_vs_complement_pp_later | positive_block_ci_both |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETHUSDT | 1m | 30d | 1.0000 | first_touch | regime_approach | neutral__from_above | 116 | 260 | 0.2750 | 1.3662 | 0.9850 | -1.3187 | 1.6696 | False |
| ETHUSDT | 1m | 30d | 1.0000 | bullish_candle | regime_approach | neutral__from_above | 115 | 258 | 0.3329 | 1.3125 | 0.9162 | -1.3473 | 1.6174 | False |
| BTCUSDT | 1m | 30d | 0.5000 | bullish_candle | regime_approach | bearish__from_below | 171 | 101 | 0.7514 | 1.5162 | 1.0584 | -1.4282 | 1.4168 | False |
| BTCUSDT | 1m | 30d | 0.5000 | first_touch | regime_approach | bearish__from_below | 184 | 106 | 0.6891 | 1.4273 | 0.9355 | -1.4399 | 1.3607 | False |
| SOLUSDT | 5m | 15d | 1.0000 | first_touch | prior_range_band | high | 254 | 148 | 0.3693 | 0.9227 | 0.5077 | -1.8809 | 1.3198 | False |
| SOLUSDT | 5m | 15d | 1.0000 | bullish_candle | prior_range_band | high | 238 | 140 | 0.2935 | 0.9262 | 0.4411 | -1.9517 | 1.3055 | False |
| SOLUSDT | 3m | 30d | 1.0000 | first_touch | origin_regime | neutral | 253 | 281 | 1.4806 | 0.3400 | 0.4655 | -1.5930 | 1.2578 | False |
| SOLUSDT | 3m | 30d | 1.0000 | bullish_candle | origin_regime | neutral | 250 | 269 | 1.4751 | 0.3227 | 0.3764 | -1.6144 | 1.2291 | False |
| SOLUSDT | 3m | 7d | 0.5000 | bullish_candle | regime_approach | bullish__from_above | 206 | 117 | 0.5370 | 0.8210 | 0.9516 | -1.7542 | 1.0294 | False |
| SOLUSDT | 3m | 15d | 1.0000 | first_touch | prior_range_band | high | 310 | 179 | 0.3633 | 0.7615 | 0.4323 | -1.8973 | 1.0122 | False |
| SOLUSDT | 5m | 7d | 1.0000 | bullish_candle | regime_approach | neutral__from_above | 166 | 156 | 0.7517 | 0.5576 | 0.0830 | -1.9422 | 0.9843 | False |
| ETHUSDT | 5m | 7d | 1.0000 | bullish_candle | regime_approach | bullish__from_below | 151 | 108 | 1.0168 | 1.0574 | 0.2724 | -1.3455 | 0.9788 | False |
| SOLUSDT | 1m | 30d | 1.0000 | bullish_candle | origin_regime | neutral | 385 | 446 | 1.3145 | 0.2631 | 0.3719 | -1.6641 | 0.9236 | False |
| SOLUSDT | 1m | 30d | 1.0000 | first_touch | origin_regime | neutral | 403 | 476 | 1.3013 | 0.2533 | 0.3261 | -1.6641 | 0.9208 | False |
| SOLUSDT | 5m | 15d | 1.0000 | first_touch | origin_regime | bullish | 238 | 183 | 0.7412 | 0.5639 | 0.5353 | -1.5535 | 0.9190 | False |

`positive_block_ci_both` means the exploratory seven-day block interval for selected-versus-complement mean return is above zero in both periods. It is not adjusted for the many hypotheses tested. This screen finds hypotheses; it does not establish optimal filters. Results share episodes across nested zones, averages, and timeframes, and the later period was already visible during Stage 1.

## Validation and preservation

Every retained Step 2 outcome is copied exactly. Context timestamps, raw 24h history, average slope, and touch close distance are independently replayed on deterministic samples. Volatility thresholds are recomputed from earlier unique origins, candidate cardinality is checked, incomplete histories stay missing, and Parquet/CSV round trips are verified.

Before/after SHA-256 confirms 347 protected Stage 1, Step 1, and Step 2 files are unchanged. All new files are isolated under Step 3 paths.

## Step 3 decision

Do not adopt a hard market filter yet. For the reference setup, bullish regime is the leading broad condition: mean/median 24h return was +1.206%/+0.775% earlier and +0.563%/+0.746% later. Approaching from below and a rising 15D average are useful secondary condition candidates, but approach from below carries somewhat deeper MAE and is not consistently superior across all configurations. Combining bullish regime with approach from below leaves only 49 later-period reference entries and does not remain stable, so do not combine them into a rule.

Bearish regime is rejected as a preferred condition for this setup because its earlier mean/median return was -2.082%/-2.849%, despite improving later. Prior-return sign and volatility band reversed between periods and should not be used as filters. None of the 151 descriptive hypotheses had an exploratory positive block interval in both periods, so the evidence supports carrying candidates forward for controlled testing rather than declaring a market-condition edge. Missing-regime observations are retained for audit only.

This run stops after market-condition analysis. No stop, exit, or Stage 2 work is performed.

## Artifacts

`condition_summary.csv` contains all periods and condition groups. `stability_screen.csv` contains every screen result. `cross_grid_effects.csv` summarizes consistency across configurations. `market_context.csv` and the per-dataset Parquet files preserve episode-level context and outcomes. `validation.csv` and `SUCCESS.json` record completion. Run `python -B -m src.research.stage15_market.run` to reproduce into a new output directory.
