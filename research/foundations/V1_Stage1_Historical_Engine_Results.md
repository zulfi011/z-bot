# V1 Stage 1 — Historical Research Engine Results

## Status

**Stage:** V1 — Stage 1  
**Engine:** Historical Research Engine  
**Decision:** **GO — Proceed to Stage 2 Backtesting**  
**Live Trading Approval:** **NO**

Stage 1 is complete. The average-touch hypothesis has enough historical evidence to justify strategy-level backtesting, but it is **not yet proven to be a profitable or production-ready trading strategy**.

---

# 1. Stage 1 Objective

The purpose of Stage 1 was to answer one question:

> Does price behavior around completed-day moving-average touch zones show enough repeatable structure to justify building and testing an actual trading strategy?

Stage 1 was intentionally designed as a **historical research engine**, not a trading engine.

It measured market behavior after average touches without yet introducing:

- actual trade state
- position management
- capital allocation
- execution costs
- overlapping-position rules
- final entry rules
- final stop-loss rules
- final exit rules
- live trading

---

# 2. Research Scope

## Assets

- BTCUSDT
- ETHUSDT
- SOLUSDT

## Exchange

- Binance Spot

## Historical Data

Requested research period:

- 2024-09-01 → 2026-08-31

Available Binance monthly archive used:

- 2024-09-01 → 2026-07-31

August 2026 monthly archive was not available at the time of collection.

## Base Data

- 1-minute candles

## Derived Timeframes

- 1m
- 3m
- 5m

3m and 5m candles were derived from validated 1m data.

## Averages

- 7D
- 15D
- 30D

All averages use only **completed previous daily closes**.

This prevents look-ahead from using the current incomplete daily candle.

## Touch Zones

- ±0.5%
- ±1.0%
- ±1.5%

## Total Main Configurations

Per asset:

- 3 timeframes
- 3 averages
- 3 touch zones

Therefore:

- 27 configurations per asset
- 81 configurations total

---

# 3. Stage 1 Pipeline Completed

The historical engine successfully completed the following research pipeline:

1. Defined research scope
2. Created project structure
3. Downloaded historical Binance 1m data
4. Validated raw data
5. Generated 3m and 5m candles
6. Generated daily candles
7. Created completed daily closes
8. Calculated and attached 7D / 15D / 30D averages
9. Calculated distance from averages
10. Identified average touches
11. Generated touch events
12. Measured forward returns
13. Measured profit-target reach
14. Measured maximum adverse excursion — MAE
15. Measured maximum favorable excursion — MFE
16. Researched +2.5% activation and trailing behavior
17. Compared 7D / 15D / 30D
18. Compared 1m / 3m / 5m
19. Compared BTC / ETH / SOL
20. Separated market regimes
21. Built configuration-driven experiment system
22. Generated and strictly validated the Stage 1 research report
23. Generated research visualizations
24. Made the final Stage 1 GO / NO-GO decision

---

# 4. Data Quality and Validation

Raw historical data was validated for:

- required columns
- UTC timestamps
- sorting
- duplicate rows
- duplicate timestamps
- missing 1-minute candles
- OHLC consistency
- positive prices
- non-negative volume

All raw datasets passed validation.

Raw row counts:

| Asset | 1m Rows |
|---|---:|
| BTCUSDT | 1,006,560 |
| ETHUSDT | 1,006,560 |
| SOLUSDT | 1,006,560 |

Derived data:

| Timeframe | Rows per Asset |
|---|---:|
| 1m | 1,006,560 |
| 3m | 335,520 |
| 5m | 201,312 |
| 1D | 699 |

No look-ahead was intentionally introduced in the average calculations.

---

# 5. Touch Definition

A candle touches an average zone when its high/low range intersects the configured zone around that average.

For an average value `A` and zone `z`:

```text
zone_low  = A × (1 - z)
zone_high = A × (1 + z)
```

A touch occurs when:

```text
candle_high >= zone_low
AND
candle_low <= zone_high
```

Touch zones are nested.

A candle touching ±0.5% also belongs to the wider ±1.0% and ±1.5% classifications where applicable.

Therefore event counts should **not** be interpreted as independent trades.

---

# 6. Forward Returns

Forward returns were measured at:

- 5m
- 15m
- 30m
- 1h
- 4h
- 24h

Future prices were matched using exact raw 1-minute timestamps.

No nearest-timestamp matching or interpolation was used.

The final Stage 1 configuration summary contains:

- valid count
- median return
- mean return

for every forward horizon and all 81 configurations.

For the primary research candidate:

**SOLUSDT / 5m / 15D / ±0.5%**

24h median forward return:

- **+0.3067%**

This does not mean a trade would realize +0.3067%.

It measures historical forward behavior after a qualifying touch.

---

# 7. Profit-Target Reach

Profit targets researched within the next 24 hours:

- +0.5%
- +1.0%
- +1.5%
- +2.0%
- +2.5%
- +3.0%
- +5.0%

For the primary candidate:

**SOLUSDT / 5m / 15D / ±0.5%**

| Target | Reach Probability |
|---|---:|
| +0.5% | ~87.28% |
| +1.0% | ~73.40% |
| +1.5% | ~62.22% |
| +2.0% | ~54.58% |
| +2.5% | ~45.93% |
| +3.0% | ~36.72% |
| +5.0% | ~18.05% |

For +2.5%:

- valid complete events: **11,865**
- reach probability: **45.93%**
- median time to target: **548 minutes**

The fixed +2.5% target naturally favors more volatile assets, so it must not be treated as a volatility-neutral metric.

---

# 8. Downside — MAE

Maximum Adverse Excursion was measured using future raw 1-minute lows.

For the primary candidate:

**SOLUSDT / 5m / 15D / ±0.5%**

24h downside statistics:

- median MAE: **-1.8488%**
- severe 10% downside: **-5.7181%**
- severe 5% downside: **-7.1724%**
- worst observed: **-23.4721%**

This is one of the main reasons Stage 1 does **not** approve the strategy for live trading.

The opportunity is meaningful, but the downside distribution also contains substantial tails.

---

# 9. Upside — MFE

Maximum Favorable Excursion was measured using future raw 1-minute highs.

For the primary candidate:

**SOLUSDT / 5m / 15D / ±0.5%**

24h median MFE:

- **+2.2556%**

Median MFE / absolute median MAE:

- **~1.2200**

This indicates that the typical favorable excursion was larger than the typical adverse excursion for this configuration.

However, MFE and MAE alone do not determine which happened first.

---

# 10. Target vs Stop First-Hit Research

Stage 1 also measured which barrier was hit first:

Target:

- +2.5%

Stops tested:

- -1.0%
- -1.5%
- -2.0%
- -2.5%
- -3.0%

Same-candle target/stop hits were kept as ambiguous.

No intraminute ordering was guessed.

For the primary SOL / 15D / 5m / ±0.5% setup:

At -2.5% stop:

- target-first, all-confirmed basis: **~42.55%**
- target-first among decisive events: **~56.63%**

This showed that very tight stops such as -1.0% and -1.5% were generally too restrictive for the observed price behavior.

It did **not** prove that -2.5% is the final stop.

---

# 11. +2.5% Activation and Trailing Research

Stage 1 studied whether +2.5% could act as a profit-activation point.

After +2.5% activation, trailing giveback behavior was measured.

A **30% profit giveback** emerged as the strongest practical Stage 1 trailing candidate.

For the primary configuration:

- activation: +2.5%
- 30% profit giveback
- resolved rate: ~97.45%
- ambiguous rate: ~2.40%
- no-trigger rate: ~0.15%
- median realized return among resolved outcomes: ~2.07%

This is a research candidate only.

It is **not yet proven to be the optimal exit rule**.

---

# 12. Average Comparison

Averages tested:

- 7D
- 15D
- 30D

The strongest Stage 1 result was:

> **15D is the primary average candidate.**

Across directly matched configurations and multiple metrics, 15D showed the strongest overall consistency.

15D was particularly strong in:

- MFE / MAE balance
- MAE
- first-hit behavior
- post-activation continuation
- trailing-related behavior

Therefore:

```text
Primary average candidate: 15D
```

7D and 30D should remain available during robustness testing.

---

# 13. Timeframe Comparison

Timeframes tested:

- 1m
- 3m
- 5m

Main conclusion:

> **1m ≈ 3m ≈ 5m behaviorally.**

The measured differences were very small.

Therefore Stage 1 does **not** claim:

> 5m is statistically the best timeframe.

Instead:

> **5m is the operational candidate.**

Why?

Because it substantially reduces repeated touch observations while preserving nearly the same measured market behavior.

This can make Stage 2 trade-state logic and signal deduplication much cleaner.

---

# 14. Asset Comparison

Assets tested:

- BTCUSDT
- ETHUSDT
- SOLUSDT

## SOLUSDT

Strongest Stage 1 opportunity candidate.

Strongest in:

- fixed target reach
- MFE
- first-hit opportunity
- post-activation movement
- overall upside behavior

But also:

- larger downside excursions
- higher volatility

## BTCUSDT

Strongest downside-control/reference asset.

BTC generally showed:

- lower MAE
- smaller absolute movement
- weaker fixed +2.5% target reach

## ETHUSDT

Useful secondary validation asset.

ETH showed intermediate opportunity behavior and comparatively strong profit-retention/trailing characteristics.

Therefore the correct Stage 1 conclusion is:

> **SOL is the strongest opportunity candidate, not universally the best or safest asset.**

---

# 15. Touch-Zone Comparison

Zones tested:

- ±0.5%
- ±1.0%
- ±1.5%

For the primary SOL / 15D / 5m setup:

| Zone | +2.5% Reach | Median MAE | Median MFE | MFE/MAE |
|---|---:|---:|---:|---:|
| ±0.5% | ~45.93% | -1.8488% | +2.2556% | ~1.2200 |
| ±1.0% | ~44.53% | -1.8283% | +2.1485% | ~1.1752 |
| ±1.5% | ~43.66% | -1.8733% | +2.1255% | ~1.1346 |

Stage 1 conclusion:

> **±0.5% is the leading touch-zone candidate.**

It is not yet a finalized production threshold.

---

# 16. Market Regime Results

Regimes were defined using completed-day averages:

## Bullish

```text
7D > 15D > 30D
```

## Bearish

```text
7D < 15D < 30D
```

## Neutral

Any other full ordering.

For the primary SOL / 15D / 5m / ±0.5% configuration:

### Neutral

- strongest balanced MFE / MAE behavior
- strongest decisive target-first behavior
- strongest post-activation continuation
- smaller median adverse excursion

### Bearish

- highest +2.5% target reach
- stronger rebound behavior
- larger downside exposure

### Bullish

- weakest overall risk/reward balance for this specific average-touch hypothesis

Stage 1 interpretation:

```text
Neutral → strongest balanced candidate
Bearish → higher-opportunity / higher-risk rebound candidate
Bullish → weaker balance, retain for control testing
```

No hard regime filter should be implemented before Stage 2 backtesting.

---

# 17. Visualization Results

Stage 1 visualization work includes:

- price + moving-average touch examples
- forward-return distributions
- MAE distributions
- MFE distributions
- MFE vs MAE scatter
- event-level MFE / MAE ratio distribution
- average comparison charts
- timeframe comparison charts
- asset comparison charts
- touch-zone comparison charts
- market-regime charts
- target-reach charts
- target-vs-stop charts
- trailing behavior charts

Generated outputs are stored under:

```text
results/figures/
```

The visualization layer supports the research conclusions but does not replace the numerical validation.

---

# 18. Important Statistical Limitations

Stage 1 results must be interpreted with the following limitations.

## Touch Events Are Not Independent Trades

Consecutive candles can represent the same underlying market interaction.

Therefore:

```text
event_count != independent trade_count
```

## Touch Zones Are Nested

±0.5%, ±1.0%, and ±1.5% observations overlap.

## Timeframes Overlap

1m, 3m, and 5m signals describe highly overlapping market movement.

## Several Metrics Are Correlated

For example:

- target reach
- MFE
- target-first probability
- post-activation upside

These metrics partly measure the same underlying opportunity/volatility behavior.

They must not be treated as independent votes.

## Fixed Percentage Targets Favor Volatility

A +2.5% barrier is easier for a higher-volatility asset to reach.

Therefore SOL's strong result must be considered together with:

- MAE
- MFE / MAE
- decisive first-hit behavior
- regime results

## Same-Candle Ambiguity Exists

OHLC candles cannot always reveal whether a target or stop occurred first inside the same minute.

Ambiguous outcomes were kept ambiguous rather than guessed.

---

# 19. Current Leading Research Candidate

The main configuration carried forward from Stage 1 is:

```text
Asset: SOLUSDT
Average: 15D
Operational timeframe: 5m
Touch zone: ±0.5%
```

Key measurements:

| Metric | Result |
|---|---:|
| Complete 24h events | 11,865 |
| +2.5% reach | ~45.93% |
| Median time to +2.5% | 548 min |
| 24h median forward return | +0.3067% |
| Median 24h MAE | -1.8488% |
| Median 24h MFE | +2.2556% |
| Median MFE / MAE | ~1.2200 |
| Target-first vs -2.5%, all-confirmed | ~42.55% |
| Target-first vs -2.5%, decisive | ~56.63% |
| Median post-activation extra upside | ~2.84% |
| 30% giveback median resolved return | ~2.07% |

This is the **leading hypothesis configuration**.

It is not a finished strategy.

---

# 20. Stage 2 Candidate Family

Stage 2 should not test only one hand-picked configuration.

The following candidate family should be retained.

## Primary

```text
SOLUSDT / 15D / 5m / ±0.5%
```

## Timeframe Robustness

```text
SOLUSDT / 15D / 1m / ±0.5%
SOLUSDT / 15D / 3m / ±0.5%
SOLUSDT / 15D / 5m / ±0.5%
```

## Touch-Zone Robustness

```text
SOLUSDT / 15D / 5m / ±0.5%
SOLUSDT / 15D / 5m / ±1.0%
SOLUSDT / 15D / 5m / ±1.5%
```

## Asset Validation

```text
ETHUSDT / 15D / 5m / ±0.5%
BTCUSDT / 15D / 5m / ±0.5%
```

## Regime Validation

```text
Neutral
Bearish
Bullish
```

This prevents Stage 2 from being built around one potentially overfit historical result.

---

# 21. Parameters That Are Candidates — Not Final Rules

Stage 1 produced the following candidates:

```text
Asset:
SOLUSDT

Average:
15D

Operational timeframe:
5m

Touch zone:
±0.5%

Balanced regime:
Neutral

Higher-risk rebound regime:
Bearish

Profit activation:
+2.5%

Trailing:
30% profit giveback
```

These should enter Stage 2 as research hypotheses.

They should **not** be hard-coded as unquestionable final strategy rules.

---

# 22. Decisions That Must Be Made in Stage 2

The following are intentionally still unresolved:

- exact trade-entry condition
- signal deduplication
- whether repeated touches create new signals
- re-entry rules
- stop-loss definition
- maximum holding period
- no-trigger exit behavior
- overlapping position behavior
- one-position vs multiple-position logic
- fees
- slippage
- execution assumptions
- position sizing
- capital allocation
- portfolio exposure
- regime filtering
- train / validation / out-of-sample methodology
- final performance acceptance criteria

These belong to Stage 2.

---

# 23. Stage 1 Decision Criteria

The hypothesis was evaluated using:

- consistency across configurations
- sample size
- forward returns
- target reach
- downside behavior
- upside behavior
- MFE / MAE balance
- first-hit ordering
- post-activation continuation
- trailing behavior
- asset comparison
- timeframe robustness
- average robustness
- touch-zone robustness
- market regimes

The final decision was **not** based on a single best metric or ranking score.

---

# 24. Final Stage 1 Decision

## Decision

# 🟢 GO — PROCEED TO STAGE 2 BACKTESTING

The average-touch hypothesis has enough historical structure and consistency to justify building a proper strategy backtesting engine.

Stage 1 found:

- meaningful forward behavior after average touches
- strong support for the 15D average
- consistent behavior across 1m / 3m / 5m
- a strong opportunity candidate in SOL
- a meaningful upside/downside relationship
- regime-dependent behavior
- useful +2.5% activation behavior
- a practical 30% profit-giveback trailing candidate
- sufficient event sample size for deeper research

This is enough evidence to continue.

---

# 25. What the GO Decision Does Not Mean

The Stage 1 GO decision does **not** mean:

```text
The strategy is profitable.
The strategy is safe.
SOL is always the best asset.
5m is statistically superior.
±0.5% is the final threshold.
+2.5% is the optimal target.
30% giveback is the optimal exit.
The system is ready for live trading.
```

Stage 1 only establishes:

> The historical average-touch hypothesis is strong enough to justify strategy-level backtesting.

---

# 26. Live Trading Decision

# 🔴 NO — NOT APPROVED FOR LIVE TRADING

Before live trading can even be considered, Stage 2 and later stages must demonstrate that the apparent historical edge survives:

- actual trade-state rules
- signal deduplication
- fees
- slippage
- overlapping positions
- stop rules
- exit rules
- capital management
- out-of-sample testing
- robustness testing
- realistic execution assumptions

---

# 27. Final Stage 1 Status

```text
V1 STAGE 1 — HISTORICAL RESEARCH ENGINE

Research pipeline:        COMPLETE
Raw-data validation:      PASS
No-look-ahead validation: PASS
81-config experiment:     COMPLETE
Forward returns:          COMPLETE
Target reach:             COMPLETE
MAE research:             COMPLETE
MFE research:             COMPLETE
First-hit research:       COMPLETE
Trailing research:        COMPLETE
Average comparison:       COMPLETE
Timeframe comparison:     COMPLETE
Asset comparison:         COMPLETE
Regime research:          COMPLETE
Configuration system:     COMPLETE
Research report:          COMPLETE
Final report validation:  100 / 100 PASS
Visualizations:            COMPLETE
Stage 1 decision:          GO

NEXT:
V1 STAGE 2 — STRATEGY BACKTESTING

LIVE TRADING:
NOT APPROVED
```

---

# Final Conclusion

Stage 1 successfully fulfilled its purpose.

The historical research engine found enough consistent evidence around completed-day average touches to justify moving forward.

The strongest direction is:

> **SOLUSDT interacting with the completed-close 15D average, with 5m as the practical operating timeframe and ±0.5% as the leading touch-zone candidate.**

The evidence is promising but still descriptive.

The next stage must determine whether this behavior can be converted into a **realistic, deduplicated, cost-aware and robust trading strategy**.

# Final Decision: GO TO STAGE 2 BACKTESTING
