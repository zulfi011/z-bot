# Stage 1.5 Step 1 — Touch Deduplication

## Rule and scope

One episode is a maximal consecutive run of touching candles per asset/timeframe/average/zone. Keep the first candle at its close; reset after one complete non-touch candle. Daily average updates alone do not reset a run. Missing candle intervals are rejected. Boundary/warm-up runs are retained and marked censored. Episode ends and lengths are retrospective audit metadata, never selection inputs.

Stage 1 IDs, prices, forward-return timing, future windows, nullable outcomes, and ambiguity treatment are preserved. All retained enriched columns are copied exactly by event ID. No trading state, costs, or parameter optimization is introduced.

## Population

Across 81 configurations: 6,199,294 classified observations → 150,313 episodes (97.58% reduction). These totals include overlapping average, zone, and timeframe classifications.

Primary SOLUSDT / 5m / 15D / ±0.5%: 11,867 → 1,147 (90.33% reduction); left-censored 1, right-censored 0.

## Primary comparison

| Metric | Stage 1 | Deduplicated | Difference |
|---|---:|---:|---:|
| forward_return_total_event_count | 11867 | 1147 | -10720 |
| complete_24h_event_count | 11865 | 1146 | -10719 |
| reach_probability_pct | 45.9334 | 50.349 | +4.41562 |
| median_time_to_target_minutes | 548 | 521 | -27 |
| return_24h_median_pct | 0.306674 | 0.345169 | +0.0384949 |
| mae_24h_median_pct | -1.84878 | -2.03009 | -0.181313 |
| mfe_24h_median_pct | 2.25558 | 2.51077 | +0.255185 |
| median_mfe_mae_ratio | 1.22004 | 1.23677 | +0.016736 |
| target_2_5_first_vs_stop_2_5_pct | 42.555 | 45.6844 | +3.12941 |
| first_2_5_target_first_decisive_pct | 56.627 | 57.5192 | +0.892163 |
| activated_event_count | 5450 | 577 | -4873 |
| trail30_resolved_pct | 97.4495 | 96.8804 | -0.569125 |
| trail30_ambiguous_pct | 2.40367 | 2.77296 | +0.369294 |
| trail30_median_realized_return_pct | 2.07407 | 2.0971 | +0.0230248 |

## Findings across the full grid

| Metric | Configurations higher | Configurations lower | Median change |
|---|---:|---:|---:|
| return_24h_median_pct | 16 | 65 | -0.0983622 |
| reach_probability_pct | 62 | 19 | +1.7929 |
| mae_24h_median_pct | 0 | 81 | -0.249904 |
| mfe_24h_median_pct | 68 | 13 | +0.123797 |
| median_mfe_mae_ratio | 15 | 66 | -0.0801944 |
| first_2_5_target_first_decisive_pct | 13 | 68 | -2.58079 |

A lower MAE means a more negative adverse excursion. The primary candidate retains positive median 24h forward behavior and improves target reach, but experiences deeper downside. Across the full grid, first-touch selection generally weakens the median return and excursion balance. These are descriptive changes on the same historical period, not independent significance tests.

## Primary regime sensitivity

| Regime | Episodes | Median 24h return (%) | Median MAE (%) | Median MFE (%) | MFE/MAE | Target-first decisive (%) |
|---|---:|---:|---:|---:|---:|---:|
| bearish | 270 | -0.5455 | -2.6650 | 2.8575 | 1.0722 | 56.1702 |
| bullish | 391 | 0.7928 | -2.0191 | 2.9435 | 1.4579 | 58.0247 |
| missing | 29 | 0.8435 | -2.1036 | 2.8897 | 1.3737 | 66.6667 |
| neutral | 457 | 0.2195 | -1.7371 | 2.2106 | 1.2726 | 57.3171 |

The Stage 1 Neutral-regime preference is sensitive to observation weighting. For this first-touch population, Bullish has a larger median forward return and MFE/MAE ratio than Neutral; Bearish has a negative median 24h return. This warrants reassessment, not a new regime filter within Step 1. The missing group lacks all three completed-day averages.

Percentage metric differences are percentage points; ratios and counts retain their own units.

## Validation

All 11 recorded validation groups passed. Full candle formula and event coverage checks; independent timestamp-gap partition reconstruction; one first representative per episode; exact retained outcome and Parquet round-trip equality; recomputed baseline compared numerically against the validated 81-row Stage 1 summary; CSV round trips; before/after SHA-256 equality of protected Stage 1 files.

## Interpretation and limits

Deduplication changes the weighting from every touching candle to the beginning of each contiguous interaction. It does not prove statistical independence: nested zones, shared averages/timeframes, nearby re-entries, and overlapping 24h windows remain. The one-non-touch reset is an explicit minimal rule, not an optimized cooldown.

Primary configuration has 1057 subsequent episode starts less than 24h after the preceding start. This is not a non-overlapping trade backtest.

Target reach uses confirmed hit/non-hit outcomes (unknown excluded); MAE/MFE use complete windows; first-hit reports all-confirmed and decisive denominators separately; trailing statistics condition on activation and resolved/confirmed outcomes. The MFE/MAE ratio is a ratio of population medians, not a median event ratio. Forward returns remain anchored to candle open plus horizon; excursion windows start after candle completion.

A first-touch sample is a changed hypothesis population, not evidence of profitability. No significance or live-performance claim is made. Missing-regime observations are preserved as a separate group.

## Artifacts and reproduction

Run `python -B -m src.research.stage15.run_step1` from the project environment. Existing run directories are refused. A run is complete only when SUCCESS.json exists. Run `python -B -m pytest tests/test_stage15_deduplication.py` for synthetic boundary and causal tests.

Per asset/timeframe, event_membership maps every Stage 1 row to an episode; episodes contains audit metadata; episode_outcomes preserves the selected original enriched rows. Comparison CSVs cover every horizon, target, excursion window, first-hit stop, trailing giveback, and regime. Differences use identical formulas on both populations.

Stopped after Step 1. No further refinement or Stage 2 work performed.
