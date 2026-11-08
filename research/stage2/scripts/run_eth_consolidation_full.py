"""ETH on its own terms: the whole consolidation-breakout space, nothing borrowed from SOL.

Every combination of

  chart:   1, 3, 5, 10, 15, 30, 60, 120, 240 minutes
  zone:    10, 12, 20, 24, 40, 48 bars of that chart
  width:   0.3, 0.5, 0.75, 1, 1.5, 2, 2.5, 3 %
  confirm: 0, 1, 3, 5, 10, 15, 30, 60 minutes after the break
  stop:    -1 ... -4%
  trail:   giveback 12% -> start +1.251%, up to 30% -> +1.315%

at both fee levels, $300 as 3 x $100 lots. Winners get re-sized afterwards.
"""

from __future__ import annotations

import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid

v4.SYMBOL = "ETHUSDT"
v4.TIMEFRAMES = [1, 3, 5, 10, 15, 30, 60, 120, 240]
v4.BARS = [10, 12, 20, 24, 40, 48]
v4.ZONES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]
v4.CONFIRM = [0, 1, 3, 5, 10, 15, 30, 60]
v4.RESULT_DIR = grid.ROOT / "results" / "eth_consolidation_full"

if __name__ == "__main__":
    v4.main()
