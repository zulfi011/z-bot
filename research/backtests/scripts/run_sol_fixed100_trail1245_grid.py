"""Fixed-$100 SOL strategy with the trail starting at +1.245%, giveback 10…30%.

Identical rules and machinery to run_sol_fixed100_giveback_grid; only the
trail start (+1.245% from entry fill) and the giveback list (10, 12, … 30%)
change. 5,940 combinations.
"""

from __future__ import annotations

import run_sol_fixed100_giveback_grid as base
import run_sol_stage3_space_grid as grid

ACTIVATION = 1.245
GIVEBACKS = [10.0] + [float(g) for g in range(12, 31, 2)]

base.EXPERIMENT_ID = "sol_fixed100_trail1245_grid_v1"
base.RESULT_DIR = grid.ROOT / "results" / base.EXPERIMENT_ID
base.DATA_DIR = grid.ROOT / "data" / base.EXPERIMENT_ID
base.GIVEBACKS = GIVEBACKS
base.EXIT_SETS = [("fixed_1.245", ACTIVATION, g) for g in GIVEBACKS]
base.ACTIVATIONS = [ACTIVATION]

if __name__ == "__main__":
    base.main()
