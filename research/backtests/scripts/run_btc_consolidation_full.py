"""BTC on its own terms: the whole consolidation-breakout space, same grid ETH and TRX were given."""

from __future__ import annotations

import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid

v4.SYMBOL = "BTCUSDT"
v4.TIMEFRAMES = [1, 3, 5, 10, 15, 30, 60, 120, 240]
v4.BARS = [10, 12, 20, 24, 40, 48]
v4.ZONES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]
v4.CONFIRM = [0, 1, 3, 5, 10, 15, 30, 60]
v4.RESULT_DIR = grid.ROOT / "results" / "btc_consolidation_full"

if __name__ == "__main__":
    v4.main()
