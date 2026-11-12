# SOL Comparison v2 — Current vs Filtered Fixed-$100 Candidates ($300, exact Stage 3 replay)

Windows: full 2024-10-01 → 2026-07-31; earlier → 2025-08-31; later 2025-09-01 → 2026-07-31; unseen
2026-08-01 → 2026-09-10 22:10 UTC. Each window restarts at $300.

- **Current live**: 3m, 15-day avg, ±0.5%, 2×25%, −4% stop, trail +4% / 10%, 24h hold
- **Reference 1×50%**: current rules, one lot of 50%
- **New best**: 3m, 12-day avg, ±0.5%, 3×$100, −2% stop, trail +1.251% / 12%, no time exit, skip entries 06–12 UTC
- **New lower-risk**: new best + confirmation close above 30-day average

| 10/2 bps | Current | 1×50% | New best | New lower-risk |
|---|---:|---:|---:|---:|
| Full profit | +$25.00 | +$46.31 | **+$51.94** | +$44.77 |
| Earlier | +$11.28 | +$22.35 | **+$22.61** | +$17.17 |
| Later | +$13.22 | +$22.29 | **+$29.34** | +$27.60 |
| Unseen | −$5.65 (3) | −$4.99 (2) | **+$8.02 (21)** | +$6.92 (20) |
| Max drawdown | −12.16% | −9.77% | −9.79% | **−8.51%** |
| Profit factor | 1.18 | 1.32 | 1.38 | **1.47** |
| Return ÷ drawdown | 0.69 | 1.58 | **1.77** | 1.75 |
| Win rate | 54.0% | 54.9% | 74.1% | **75.0%** |
| Avg win / loss | +2.64% / −2.59% | +2.70% / −2.46% | +1.07% / −2.22% | +1.09% / −2.22% |
| Trades / month | 6.9 | 3.7 | 10.9 | 7.8 |
| Fees + slippage | $27.77 | $31.46 | $57.19 | $41.18 |

| Full profit by costs | Current | 1×50% | New best | New lower-risk |
|---|---:|---:|---:|---:|
| 10/2 bps | +$25.00 | +$46.31 | **+$51.94** | +$44.77 |
| 7.5/2 bps (BNB) | +$31.24 | +$53.49 | **+$64.03** | +$53.40 |
| 15/5 bps stress | +$6.74 | **+$25.36** | +$7.15 | +$10.57 |
| 15/5 bps stress, earlier | +$1.87 | **+$12.41** | −$3.01 | −$4.46 |

The new strategies were selected from tens of thousands of combinations plus filters found in the same data,
so their historical edge is more likely overstated than the current or 1×50% rules. The 12-day average is a
knife-edge (11- and 13-day versions lose over the full history). The new strategies need Stage 3 engine
changes (12-day average, fixed-$100 lots, no time limit, time-of-day filter, 30-day filter).
