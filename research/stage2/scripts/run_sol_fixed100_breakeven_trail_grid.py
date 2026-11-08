"""Fixed-$100 SOL strategy where each giveback uses its own break-even trail start.

Giveback 10, 12, … 30%; trail start = 0.2202% / (1 − giveback) rounded up
(+0.245% at 10% … +0.315% at 30%), so a trail exit right after activation
returns the stake after fees and slippage. Other rules as
run_sol_fixed100_giveback_grid. 5,940 combinations.
"""

from __future__ import annotations

import run_sol_fixed100_giveback_grid as base
import run_sol_stage3_space_grid as grid

GIVEBACKS = [float(g) for g in range(10, 31, 2)]

base.EXPERIMENT_ID = "sol_fixed100_breakeven_trail_grid_v1"
base.RESULT_DIR = grid.ROOT / "results" / base.EXPERIMENT_ID
base.DATA_DIR = grid.ROOT / "data" / base.EXPERIMENT_ID
base.GIVEBACKS = GIVEBACKS
base.EXIT_SETS = [("break_even", base.break_even_activation(g), g) for g in GIVEBACKS]
base.ACTIVATIONS = sorted({a for _, a, _ in base.EXIT_SETS})

if __name__ == "__main__":
    print([(g, a) for _, a, g in base.EXIT_SETS], flush=True)
    base.main()
