# ETH Stage 1.5 Full Historical Audit and Freeze Decision

## Decision

**FROZEN_FOR_PAPER_VALIDATION_ONLY**

The candidate is frozen as an immutable paper-trading hypothesis only. It is not approved for live trading because the historical sample was used to select it, realistic medians are not positive in both periods, and both 95% block-bootstrap intervals include zero.

## Frozen strategy

- ETHUSDT spot, long only, one open position maximum.
- Use 3-minute signal candles and raw 1-minute execution candles.
- Calculate 7D, 15D, and 30D simple averages from completed UTC daily closes only.
- Eligible regime: 7D average > 15D average > 30D average.
- Start one touch episode when a 3-minute candle range intersects the ±1.0% zone around the 15D average; consecutive touching candles remain one episode.
- During that episode, accept the first bullish 3-minute candle (close > open) no later than 30 minutes after the first touch. The first non-touch candle is the final confirmation opportunity.
- Enter at the next raw 1-minute open after the confirming candle closes.
- Place a 5.0% protective stop from the actual entry fill; a gap fills at the worse of the stop or candle open.
- No profit target and no trailing stop. Exit after 480 minutes using the final raw 1-minute close, with adverse exit slippage.
- Risk at most 1.0% of current net liquidation per trade. With a modeled 5.25% all-in stop loss, cap position notional at 19.0% of net liquidation; use spot balance only and no leverage.
- Model 10 bps fee and 2 bps slippage per side. Reject paper signals if the implementation cannot preserve these rules.

## Main candidate by historical period

| period | trades | mean % | median % | win % | profit factor | ES 10% | max DD % | 95% CI | P(mean > 0) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| earlier | 69 | 0.0465 | 0.0348 | 50.7246 | 1.0535 | -4.1308 | -16.6605 | [-0.6320, 0.6268] | 54.4600% |
| later | 48 | 0.0294 | -0.1654 | 45.8333 | 1.0671 | -1.9870 | -7.4828 | [-0.3539, 0.3140] | 57.2400% |
| combined | 117 | 0.0395 | -0.1020 | 48.7179 | 1.0570 | -3.5576 | -16.6605 | [-0.3643, 0.3977] | 58.0200% |

The earlier/later boundary is 2025-09-01 UTC. Returns include 10 bps fees and 2 bps slippage on each side.
The main statistics use an exact raw-minute replay with the protective stop calculated from the adverse entry fill. The broader exit sweep preserves each previously audited historical exit event and overlays execution costs for comparison.

## Execution-cost sensitivity

| scenario | fee/side bps | slippage/side bps | combined mean % | combined median % | profit factor | max DD % |
|---|---:|---:|---:|---:|---:|---:|
| gross | 0.0 | 0.0 | 0.2794 | 0.1380 | 1.4842 | -12.2572 |
| fee_only | 10.0 | 0.0 | 0.0790 | -0.0621 | 1.1174 | -15.9070 |
| realistic | 10.0 | 2.0 | 0.0395 | -0.1020 | 1.0570 | -16.6605 |
| stressed | 10.0 | 5.0 | -0.0198 | -0.1619 | 0.9726 | -17.7780 |
| severe | 10.0 | 10.0 | -0.1185 | -0.2617 | 0.8467 | -20.5955 |

## Adjacent timeframe and zone sensitivity

| timeframe | zone % | trades earlier/later | mean earlier % | mean later % | median earlier % | median later % |
|---|---:|---:|---:|---:|---:|---:|
| 1m | 0.5 | 50/50 | -0.2787 | 0.0578 | -0.4567 | 0.1458 |
| 1m | 1.0 | 70/50 | 0.1771 | 0.0356 | 0.0151 | -0.1465 |
| 1m | 1.5 | 84/46 | -0.0259 | -0.4742 | -0.1646 | -0.3791 |
| 3m | 0.5 | 48/46 | -0.2166 | 0.0703 | -0.3266 | 0.1185 |
| 3m | 1.0 | 69/48 | 0.0465 | 0.0294 | 0.0348 | -0.1654 |
| 3m | 1.5 | 79/43 | 0.0220 | -0.4316 | -0.1764 | -0.3372 |
| 5m | 0.5 | 47/45 | -0.1677 | 0.0247 | -0.3957 | 0.0413 |
| 5m | 1.0 | 67/46 | 0.0480 | -0.0143 | 0.0332 | -0.2432 |
| 5m | 1.5 | 77/38 | -0.0203 | -0.2753 | -0.2132 | -0.1237 |

At the frozen ±1.0% zone, the 1m variant retains positive means in both periods. The 5m variant is positive earlier and −0.0143% later. One of two adjacent timeframes therefore passes the predeclared 50% continuity threshold; neither neighbor has a positive confidence lower bound.

## Exact protective-stop sensitivity

| stop % | trades earlier/later | mean earlier % | mean later % | worst earlier % | worst later % | max DD earlier % | max DD later % |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.0 | 76/49 | -0.1170 | -0.0053 | -2.2154 | -2.2154 | -20.8252 | -7.5024 |
| 3.0 | 73/48 | -0.0615 | 0.0300 | -3.2132 | -3.2132 | -18.8153 | -7.4541 |
| 4.0 | 70/48 | -0.0064 | 0.0294 | -4.2110 | -3.2432 | -19.8894 | -7.4828 |
| 5.0 | 69/48 | 0.0465 | 0.0294 | -5.2088 | -3.2432 | -16.6605 | -7.4828 |
| 6.0 | 69/48 | 0.0341 | 0.0294 | -6.2066 | -3.2432 | -17.5377 | -7.4828 |
| 8.0 | 69/48 | 0.0686 | 0.0294 | -5.2064 | -3.2432 | -16.6584 | -7.4828 |

The exact fill replay rejects stops from 2% through 4% because their realistic mean is non-positive in at least one period. The 5% stop is the smallest tested protective boundary that preserves a positive mean in both periods. This choice was made on historical data and is therefore part of the strategy's selection bias; it must remain unchanged during prospective paper validation.

## Exit sweep

Top ten of all 38 previously audited exit rules for the same 3m/15D/±1.0% entry family, ranked by the weaker realistic period mean:

| exit | trades earlier/later | mean earlier % | mean later % | median earlier % | median later % | weaker mean % |
|---|---:|---:|---:|---:|---:|---:|
| time_480_stop_4 | 69/48 | 0.0532 | 0.0294 | 0.0348 | -0.1654 | 0.0294 |
| time_480_no_stop | 69/48 | 0.0686 | 0.0294 | 0.0348 | -0.1654 | 0.0294 |
| time_240_stop_4 | 88/73 | -0.1073 | -0.1252 | -0.3517 | -0.1110 | -0.1252 |
| time_240_no_stop | 88/73 | -0.0941 | -0.1499 | -0.3517 | -0.1110 | -0.1499 |
| time_120_stop_4 | 121/98 | -0.1081 | -0.1764 | -0.1436 | -0.1811 | -0.1764 |
| time_120_no_stop | 121/98 | -0.0975 | -0.1806 | -0.1436 | -0.1811 | -0.1806 |
| time_720_stop_4 | 52/41 | -0.1044 | -0.1815 | -0.0579 | -0.2717 | -0.1815 |
| time_60_no_stop | 151/129 | -0.2185 | -0.2161 | -0.2315 | -0.2148 | -0.2185 |
| time_60_stop_4 | 151/129 | -0.2211 | -0.2161 | -0.2315 | -0.2148 | -0.2211 |
| time_30_no_stop | 185/159 | -0.2021 | -0.2265 | -0.2651 | -0.2190 | -0.2265 |

## Gate audit

- Sample size: **PASS**.
- Positive realistic mean in both periods: **PASS**.
- At least half of adjacent timeframes positive in both periods: **PASS** (1/2).
- Positive-quarter consistency: **PASS** (5/7 quarters; 71.43%).
- Tail and drawdown floors: **PASS**.
- Positive realistic median in both periods: **FAIL**.
- Positive 95% weekly-block confidence lower bound in both periods: **FAIL**.

Passing the paper-freeze gate means the rule is sufficiently coherent to test prospectively without further historical tuning. Failing the strict gate means the historical evidence does not establish a dependable positive edge.

## Interpretation

This is a small, positively skewed historical effect. Its gross return is only slightly larger than realistic round-trip execution drag, and it becomes fragile under stressed slippage. Paper trading must measure actual fill drag, missed signals, stop gaps, and data latency. The frozen parameters must not be tuned during that test; any rule change creates a new version and restarts validation.

## Reproduction

Run from `stage1_research`: `.env/bin/python -B -m src.research.eth_stage15_freeze.run`.
