# SOL Fixed-$100 Micro Trail — Giveback 12…30%

> **Corrected 2026-09-11.** The first version of this report was produced by a fast-engine bug (stop exits
> before trail activation were recorded only for the first 3 giveback values). Giveback ≥ 18% rows were
> wrong. Fixed in `run_sol_stage3_space_grid.exit_outcomes` and re-run; numbers below are corrected.

## Rules

Same as `sol_fixed100_micro_trail_grid_v1` ($300, up to 3 lots of min($100, free cash); touch from below of
a 7–15 day completed-close average, ±0.1…0.5%; bullish confirmation; avoid strong bearish; stops
−0.5/−1/−1.5/−2%; no time exit), with giveback 12, 14, … 30% and two trail starts per giveback:

- **fixed**: +0.245% from entry fill
- **break-even**: 0.2202% / (1 − giveback), rounded up — +0.251% (12%) … +0.315% (30%)

3 candles × 9 averages × 5 zones × 4 stops × 10 givebacks × 2 starts = **10,800 combinations**.

## Result

**0 of 10,800 profitable** over the full history; none profitable in either period. 6,323 were positive
before fees and slippage (best +$61.01). Median −$109.13 on $300; worst −$209.56.

Best candidate (exact Stage 3 replay = fast grid to the cent):
**5m candles, 13-day average, ±0.1% zone, −2% stop, trail from +0.298% with 26% giveback**

| Window | Trades | Win rate | Profit on $300 | Max DD | Fees + slippage |
|---|---:|---:|---:|---:|---:|
| Full | 318 | 80.8% | −$44.51 (−14.8%) | −16.4% | $73.24 |
| Earlier | 156 | 80.1% | −$30.83 | −12.3% | $36.53 |
| Later | 162 | 81.5% | −$13.71 | −6.9% | $38.48 |
| Unseen | 30 | 83.3% | −$0.30 | −1.0% | $7.20 |

283 trailing exits earned +$32.12 (+$0.11 each); 35 stops lost −$76.64 (−$2.19 each).

Median full profit by trail start: break-even −$107.8, fixed +0.245% −$110.9. Giveback medians range from
−$110.9 (14%) to −$107.3 (30%) — larger giveback helps slightly, never enough.
