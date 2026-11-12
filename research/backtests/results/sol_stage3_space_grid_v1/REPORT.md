# SOL — Every Stage 3-Deployable Combination (846,720)

## Search

Every combination of rules Stage 3 can already run, on SOLUSDT, $100 start, 10 bps fee + 2 bps
slippage per side:

| Dimension | Values |
|---|---|
| Signal candle | 1m, 3m, 5m |
| Average (completed daily closes) | 7, 15, 30 days |
| Touch zone | ±0.25%, ±0.5%, ±0.75%, ±1% |
| Approach | from below, any direction |
| Trend filter | avoid strong bearish, bullish only |
| Protective stop | −1% … −4% (0.5 steps) |
| Trail activation | +1% … +4% (0.5 steps) |
| Giveback | 10%, 15%, 20% |
| Maximum hold | 12h, 24h, 48h, 72h, none |
| Sizing | 1×100%, 1×50%, 2×25%, 2×50%, 3×20%, 3×33%, 4×25%, 5×20% |

144 entry configs × 735 exit configs × 8 sizings = **846,720**, each run on earlier
(2024-10-01 → 2025-08-31), later (2025-09-01 → 2026-07-31) and unseen holdout
(2026-08-01 → 2026-09-09), restarting at $100 each.

## Verification

- Fast signal engine equals Stage 3's `FrozenSignalEngine` for **all 144 entry configs** (99,573 signals).
- The live baseline row reproduces the exact Stage 3 replay: 82 / 70 / 1 trades, $103.76 / $104.41 / $99.64.
- All candidates below are re-run on the exact Stage 3 replay with minute-marked drawdown.
- The grid's drawdown is marked at signal times only, so it is slightly optimistic (−11.4% vs exact −12.2% for the baseline).

## Finding 1 — picking on the earlier period does not work

| Earlier-only selection rule | Top N | Median earlier | Median later | Beat baseline later |
|---|---:|---:|---:|---:|
| Highest earlier return (DD ≤ 15%, ≥30 trades, PF > 1) | 10 / 100 / 1000 | +65.7% / +50.8% / +40.8% | −23.3% / −22.8% / −18.8% | 0% / 0% / 0% |
| Best earlier return per drawdown | 10 / 100 / 1000 | +28.8% / +28.7% / +32.3% | −6.1% / −8.4% / −9.5% | 0% / 0% / 0% |

The earlier-period winner (3m, 30-day average, ±1%, any direction, 72h hold, 1×100%) made +56.9% earlier
and **lost 24.0% later** (exact replay, −31.3% drawdown). Big earlier-period winners are fitted to
that year's market.

## Finding 2 — the current strategy is already near the top

The live rules rank in the top 15% earlier and **top 8% later** out of 846,720. Only 1,005
combinations beat it in both periods, and they are dominated by its own rules: 15-day average (51%),
from below (94%), ±0.25–0.5% zone (96%), 24h hold (58%), −3.5 to −4% stop (69%), +3.5 to +4%
activation (60%). What they mostly change is **sizing — fewer, larger lots.**

## Finding 3 — one lot beats two lots for these rules

Live rules unchanged, sizing varied (exact replay):

| Sizing | Full | Earlier | Later | Holdout | Max drawdown | Trades |
|---|---:|---:|---:|---:|---:|---:|
| 2 × 25% (live) | +8.33% | +3.76% | +4.41% | −0.36% | −12.16% | 152 |
| **1 × 50%** | **+15.44%** | **+7.45%** | **+7.43%** | **−0.14%** | **−9.77%** | 82 |
| 1 × 100% | +30.84% | +14.27% | +14.51% | −0.29% | −18.73% | 82 |
| 2 × 50% | +15.59% | +6.64% | +8.38% | −0.72% | −23.16% | 152 |
| 3 × 20% | +4.61% | +1.94% | +2.61% | −0.50% | −14.33% | 205 |
| 3 × 33% | +6.70% | +2.62% | +3.98% | −0.83% | −23.00% | 205 |
| 4 × 25% | +2.61% | −0.26% | +2.88% | −0.88% | −23.10% | 250 |
| 5 × 20% | +3.73% | +0.12% | +3.60% | −0.90% | −21.53% | 287 |

1 × 50% and 2 × 25% have the same maximum exposure (50% of equity). Why one lot wins: a second lot opens
only while the first is still open, i.e. when SOL keeps re-touching the average from below without
breaking out. In the live-rules history, first lots average **+0.33%** per trade and second lots
**+0.13%**, and paired lots tend to be stopped out together (as happened live on 2026-09-10 12:48).

Robustness: across 81 neighbouring exit settings (stop 3–4%, activation 3–4%, giveback 10–20%,
hold 12–48h), 1 × 50% earns more than 2 × 25% in both periods in 67% of cases. Its drawdown advantage
does **not** generalise (7% of neighbours) — that part is specific to the exact live settings. Across
the whole grid, one lot beats two in both periods for only 10% of rule sets, so this is a property of
these rules, not a universal law.

## Candidate

**`sol_15d_touch_v2_single_lot`** — current live SOL rules with `maximum_open_positions: 1` and
`equity_fraction_per_entry: 0.5`. Proposed file:
`config/experiments/sol_15d_touch_v2_single_lot_PROPOSED.json` (not deployed).

Caveats:
- It was identified after looking at both periods, so earlier/later are not an independent test of it.
- The unseen holdout has only one closed trade — inconclusive.
- A forward paper sample is the real test.

## Files

- `all_combinations.parquet` — all 846,720 rows × 3 periods
- `selection.json`, `generalisation.csv`, `top1000_*.csv` — earlier-only selection
- `sizing_exact.csv` — exact replays behind Finding 3
- Scripts: `run_sol_stage3_space_grid.py`, `verify_sol_stage3_space_grid.py`,
  `analyze_sol_stage3_space_grid.py`, `analyze_sol_sizing.py`
