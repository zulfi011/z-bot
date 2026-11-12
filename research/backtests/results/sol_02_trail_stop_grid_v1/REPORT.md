# SOL ±0.2% Touch — Trailing × Stop Grid (Stage 3 rules)

## Rules tested

3m candles, 15-day average of completed daily closes (as Stage 3), ±0.2% touch from below, bullish
confirmation within 30 minutes, avoid strong bearish. Buy at the confirmation boundary. One position,
100% of equity. No time exit. Trailing activation immediate or +1% … +4% (0.5 steps) × giveback
10/15/20% × protective stop −1% … −4% (0.5 steps) or none = **192 combinations**. 10 bps fee + 2 bps
slippage per side.

Windows: full 2024-10-01 → 2026-07-31; earlier → 2025-08-31; later 2025-09-01 → 2026-07-31; unseen
2026-08-01 → 2026-09-10 19:57 UTC (Binance archives + live paper database, identical where they overlap).

## Result

Only **12 of 192** were profitable over the full history; **3** were positive in both periods.

| Strategy (exact Stage 3 replay) | Full | Earlier | Later | Unseen | Max DD | Trades | Win rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| Best ±0.2%: trail +3%, 15% giveback, −4% stop, 1×100% | +11.91% | +3.97% | +7.64% | −1.48% | −21.95% | 66 | 62.1% |
| Current live: ±0.5%, 2×25%, −4%/+4%/10%, 24h | +8.33% | +3.76% | +4.41% | −1.88% | −12.16% | 152 | 54.0% |
| **Candidate: ±0.5%, 1×50%, −4%/+4%/10%, 24h** | **+15.44%** | **+7.45%** | **+7.43%** | −1.66% | **−9.77%** | 82 | 54.9% |
| (Reference) Candidate rules at 1×100% | +30.84% | +14.27% | +14.51% | — | −18.73% | 82 | — |

- The best ±0.2% row is a single spike: at +2.5% activation it loses (−4.6%), at +3.5% it loses
  7.9% in the later period, at +4% it loses (−10.9%).
- Immediate trailing loses heavily (best −51.5%; 379 trades each paying fees on tiny gains).
- No stop: best earlier +45% then −55% later, −74.6% drawdown (one position held through a crash).
- Earlier-only pick (trail +3%, 20% giveback, no stop): −37.8% full.

## Conclusion

The ±0.2% / 100% / no-time-exit family does not beat the 1×50% candidate on return, drawdown, or
consistency. At the same 100% exposure, the current ±0.5% rules make +30.84% vs +11.91%.

Files: `all_192_combinations.csv`, `exact_comparison.csv`; script `scripts/run_sol_02_trail_stop_grid.py`.
