"""Exact replay of the live SOL rules under every grid sizing, plus neighbours."""

from __future__ import annotations

import json

import pandas as pd

import analyze_sol_stage3_space_grid as analysis
import run_sol_stage3_space_grid as grid

VARIANTS = [
    {**grid.BASELINE, "lots": lots, "fraction": fraction} for lots, fraction in grid.SIZINGS
] + [
    {**grid.BASELINE, "signal_minutes": 1, "lots": 2, "fraction": 0.5},
    {**grid.BASELINE, "signal_minutes": 1, "lots": 1, "fraction": 1.0},
    {**grid.BASELINE, "signal_minutes": 5, "lots": 1, "fraction": 1.0},
    {**grid.BASELINE, "zone_pct": 0.25, "lots": 1, "fraction": 1.0},
]


def main() -> None:
    exact = analysis.ExactReplay()
    rows = []
    for variant in VARIANTS:
        result = exact.run(variant)
        for period, summary in result.items():
            rows.append({"variant": analysis.describe(variant), "lots": variant["lots"],
                         "fraction": variant["fraction"], "signal_minutes": variant["signal_minutes"],
                         "zone_pct": variant["zone_pct"], "period": period, **summary})
        print(analysis.describe(variant), flush=True)
    frame = pd.DataFrame(rows)
    frame["return_per_drawdown"] = frame.return_pct / -frame.max_drawdown_pct
    frame.to_csv(grid.RESULT_DIR / "sizing_exact.csv", index=False)
    view = frame.pivot_table(index=["signal_minutes", "zone_pct", "lots", "fraction"], columns="period",
                             values=["return_pct", "max_drawdown_pct", "trades"], sort=False)
    print(view.round(2).to_string())


if __name__ == "__main__":
    main()
