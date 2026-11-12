# BTC Stage 1/1.5/Version 2 End-to-End Audit

## Historical decision

**REJECT** — no BTC rule passed the complete historical robustness standard.

## Freeze decision

The best rule may be frozen only as an immutable prospective paper experiment. It must not be represented as historically validated.

## Best paper candidate

BTCUSDT spot, long only; 5-minute bullish confirmation after a ±1.5% touch of the completed-day 30-day SMA, only when 7D > 15D > 30D. Enter at the next raw one-minute open, take profit at +1.0% from actual fill, stop at −2.0% from actual fill, and force exit after 1,440 minutes. Model 10 bps fee and 2 bps slippage per side. Use one position and 10% of account equity.

This stop was selected after a 720-configuration exploratory exit grid. There is no untouched historical holdout left, so its positive result is a hypothesis for forward paper trading.

## Best candidate realistic results

| scenario | period | trades | mean_pct | median_pct | win_pct | profit_factor | expected_shortfall_10_pct | worst_trade_pct | max_drawdown_pct | longest_nonpositive_streak | ci95_low | ci95_high | probability_mean_positive_pct | blocks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| realistic | earlier | 31 | 0.24851 | 0.778042 | 77.4194 | 1.73477 | -2.21537 | -2.21537 | -2.45128 | 2 | -0.0242295 | 0.512769 | 96.18 | 12 |
| realistic | later | 30 | 0.109412 | 0.778042 | 70 | 1.26242 | -2.21537 | -2.21537 | -6.49995 | 3 | -0.441988 | 0.517615 | 67.54 | 14 |
| realistic | combined | 61 | 0.180101 | 0.778042 | 73.7705 | 1.47781 | -2.21537 | -2.21537 | -8.57131 | 4 | -0.11816 | 0.42708 | 89.6 | 26 |

## Best candidate quarterly stability

| quarter | trades | mean_pct | median_pct |
| --- | --- | --- | --- |
| 2024Q4 | 17 | 0.365917 | 0.778042 |
| 2025Q1 | 4 | 0.0296904 | 0.778042 |
| 2025Q2 | 2 | -0.297788 | -0.297788 |
| 2025Q3 | 9 | -0.0283698 | 0.778042 |
| 2025Q4 | 5 | -0.419321 | 0.778042 |
| 2026Q1 | 17 | 0.469284 | 0.778042 |
| 2026Q2 | 4 | -0.220636 | -0.0543999 |
| 2026Q3 | 3 | 0.166346 | 0.229671 |

## Original Stage 1.5 leader (no stop)

| period | scenario | trades | mean_pct | median_pct | win_pct | profit_factor | expected_shortfall_10_pct | worst_trade_pct | max_drawdown_pct | longest_nonpositive_streak | ci95_low | ci95_high | probability_mean_positive_pct | blocks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| earlier | realistic | 29 | 0.301721 | 0.778042 | 79.3103 | 2.01031 | -2.34577 | -3.15927 | -3.15927 | 2 |  |  |  | 0 |
| later | realistic | 29 | 0.0551484 | 0.778042 | 72.4138 | 1.1127 | -3.51483 | -5.18901 | -7.15836 | 2 |  |  |  | 0 |
| combined | realistic | 58 | 0.178435 | 0.778042 | 75.8621 | 1.45288 | -2.9303 | -5.18901 | -8.87665 | 3 | -0.177768 | 0.461014 | 85.43 | 26 |

## Original leader cost sensitivity

| scenario | period | trades | mean_pct | median_pct | win_pct | profit_factor | expected_shortfall_10_pct | worst_trade_pct | max_drawdown_pct | longest_nonpositive_streak | ci95_low | ci95_high | probability_mean_positive_pct | blocks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gross | earlier | 30 | 0.543163 | 1 | 83.3333 | 3.18093 | -2.11112 | -2.92658 | -2.92658 | 1 | 0.234145 | 0.845987 | 100 | 12 |
| gross | later | 30 | 0.305584 | 1 | 73.3333 | 1.74514 | -3.28299 | -4.96119 | -6.71165 | 2 | -0.351475 | 0.74304 | 84.96 | 14 |
| gross | combined | 60 | 0.424374 | 1 | 78.3333 | 2.28764 | -2.69706 | -4.96119 | -8.21819 | 3 | 0.0843657 | 0.694869 | 98.96 | 26 |
| fee_only | earlier | 30 | 0.342278 | 0.798202 | 83.3333 | 2.21438 | -2.3067 | -3.12053 | -3.12053 | 1 | 0.033877 | 0.644496 | 98.6 | 12 |
| fee_only | later | 30 | 0.105173 | 0.798202 | 73.3333 | 1.22737 | -3.47623 | -5.15107 | -7.08406 | 2 | -0.550572 | 0.541756 | 65.25 | 14 |
| fee_only | combined | 60 | 0.223725 | 0.798202 | 78.3333 | 1.60108 | -2.89147 | -5.15107 | -8.76723 | 3 | -0.115603 | 0.493681 | 91.37 | 26 |
| realistic | earlier | 29 | 0.301721 | 0.778042 | 79.3103 | 2.01031 | -2.34577 | -3.15927 | -3.15927 | 2 |  |  |  | 0 |
| realistic | later | 29 | 0.0551484 | 0.778042 | 72.4138 | 1.1127 | -3.51483 | -5.18901 | -7.15836 | 2 |  |  |  | 0 |
| realistic | combined | 58 | 0.178435 | 0.778042 | 75.8621 | 1.45288 | -2.9303 | -5.18901 | -8.87665 | 3 | -0.177768 | 0.461014 | 85.43 | 26 |
| stressed | earlier | 28 | 0.247214 | 0.747803 | 78.5714 | 1.76781 | -2.40435 | -3.21736 | -3.21736 | 2 |  |  |  | 0 |
| stressed | later | 29 | 0.0159673 | 0.747803 | 72.4138 | 1.03158 | -3.57271 | -5.24587 | -7.2697 | 2 |  |  |  | 0 |
| stressed | combined | 57 | 0.129562 | 0.747803 | 75.4386 | 1.3119 | -2.98853 | -5.24587 | -9.04052 | 3 | -0.224276 | 0.416837 | 77.99 | 26 |
| severe | earlier | 28 | 0.184741 | 0.697404 | 78.5714 | 1.53849 | -2.50189 | -3.3141 | -3.3141 | 2 |  |  |  | 0 |
| severe | later | 28 | -0.215594 | 0.697404 | 64.2857 | 0.66392 | -3.66909 | -5.34058 | -8.01674 | 2 |  |  |  | 0 |
| severe | combined | 56 | -0.0154268 | 0.697404 | 71.4286 | 0.968663 | -3.08549 | -5.34058 | -9.86347 | 3 | -0.368368 | 0.268873 | 47.34 | 26 |

## Parameter and stop sensitivity

| kind | timeframe | touch_zone_pct | trades_earlier | mean_pct_earlier | trades_later | mean_pct_later | positive_both | stop_pct | median_pct_earlier | max_drawdown_pct_earlier | median_pct_later | max_drawdown_pct_later |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| neighbor | 1m | 1.5 | 30 | 0.369664 | 30 | -0.10164 | False |  |  |  |  |  |
| neighbor | 3m | 1.5 | 28 | 0.293714 | 32 | -0.0126702 | False |  |  |  |  |  |
| neighbor | 5m | 1 | 20 | 0.252744 | 21 | -0.0801653 | False |  |  |  |  |  |
| neighbor | 5m | 2 | 0 |  | 0 |  | False |  |  |  |  |  |
| stop |  |  | 42 | -0.154991 | 38 | -0.157582 |  | 1 | 0.535812 | -9.90772 | 0.503857 | -6.15503 |
| stop |  |  | 31 | 0.24851 | 30 | 0.109412 |  | 2 | 0.778042 | -2.45128 | 0.778042 | -6.49995 |
| stop |  |  | 31 | 0.330713 | 30 | 0.0142389 |  | 3 | 0.778042 | -3.21317 | 0.778042 | -8.26889 |
| stop |  |  | 31 | 0.298526 | 30 | -0.0855413 |  | 4 | 0.778042 | -4.21097 | 0.778042 | -10.1505 |
| stop |  |  | 29 | 0.231049 | 30 | -0.0647896 |  | 5 | 0.778042 | -5.20877 | 0.778042 | -10.4481 |
| stop |  |  | 29 | 0.196642 | 30 | -0.0980497 |  | 6 | 0.778042 | -6.20657 | 0.778042 | -11.3907 |
| stop |  |  | 29 | 0.301721 | 30 | -0.16457 |  | 8 | 0.778042 | -3.15927 | 0.778042 | -13.276 |
| stop |  |  | 29 | 0.301721 | 29 | 0.0551484 |  | none | 0.778042 | -3.15927 | 0.778042 | -7.15836 |

## Original leader gate audit

- sample_pass: **FAIL**
- positive_mean_both: **PASS**
- positive_median_both: **PASS**
- profit_factor_both: **PASS**
- drawdown_pass_both: **PASS**
- quarter_consistency: **PASS**
- neighbor_stability: **FAIL**
- positive_ci95_both: **FAIL**
- strict_historical_validation_pass: **FAIL**

## End-to-end interpretation

Stage 1 established the completed-day moving-average touch framework on BTC. Stage 1.5 evaluated entry timing, market filters, downside protection, exits, non-overlap, costs, quarterly stability, and block bootstrap uncertainty; BTC produced zero provisional and zero robust selections. Its top-ranked candidate was the no-stop rule replayed above. Version 2 tested BTC bounce confirmations, but every BTC configuration failed the sample gate and the later market-filter, ATR-exit, execution, and strict-robustness stages proceeded with SOL only. The exact replay used actual one-minute opens, adverse fills, non-overlapping trades, conservative same-candle stop ordering, cost stress, weekly block bootstrap, quarterly slices, nearby timeframes, zones, exits, and source hashes.
