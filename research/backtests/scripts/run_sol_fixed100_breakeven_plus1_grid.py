"""Fixed-$100 SOL strategy: each giveback's break-even trail start plus 1%.

Giveback 10, 12, … 30%; trail start = break-even start + 1 percentage point
(+1.245% at 10% … +1.315% at 30%). Other rules as
run_sol_fixed100_giveback_grid. 5,940 combinations.
"""

from __future__ import annotations

import run_sol_fixed100_giveback_grid as base
import run_sol_stage3_space_grid as grid

GIVEBACKS = [float(g) for g in range(10, 31, 2)]

base.EXPERIMENT_ID = "sol_fixed100_breakeven_plus1_grid_v1"
base.RESULT_DIR = grid.ROOT / "results" / base.EXPERIMENT_ID
base.DATA_DIR = grid.ROOT / "data" / base.EXPERIMENT_ID
base.GIVEBACKS = GIVEBACKS
base.EXIT_SETS = [("break_even_plus_1", round(base.break_even_activation(g) + 1.0, 3), g) for g in GIVEBACKS]
base.ACTIVATIONS = sorted({a for _, a, _ in base.EXIT_SETS})

if __name__ == "__main__":
    print([(g, a) for _, a, g in base.EXIT_SETS], flush=True)
    base.main()
