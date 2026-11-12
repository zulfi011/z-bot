"""SOL consolidation breakout v5: the direction v4 pointed at — slower charts, longer and tighter zones.

v4 found every "best" at the edge of its range: the 30-minute chart had the least-bad median, and zone spans of
600 and 1200 minutes were the only ones whose median was near or above zero. This run walks further that way and
stops when the trend stops helping.

  charts:  30, 60, 120, 240 minutes
  zone:    12, 24, 48 bars of that chart (6 hours up to 8 days)
  width:   0.3, 0.5, 0.75, 1, 1.5, 2 %
  confirm: 0, 5, 15, 30, 60 minutes after the break
  stop:    −1 … −4%, trailing 12% / +1.251% up to 30% / +1.315%, both fee levels, $300 as 3 × $100 lots.
"""

from __future__ import annotations

import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid

v4.TIMEFRAMES = [30, 60, 120, 240]
v4.BARS = [12, 24, 48]
v4.ZONES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0]
v4.CONFIRM = [0, 5, 15, 30, 60]
v4.RESULT_DIR = grid.ROOT / "results" / "sol_consolidation_v5"

if __name__ == "__main__":
    v4.main()
