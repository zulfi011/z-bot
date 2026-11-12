"""SOL consolidation breakout, second range: tighter bands held for longer.

v1 showed the whole grid losing, with results improving towards the tight-band / long-window corner: a 3% band
over 1 minute is not consolidation, it is every minute. This run moves the range to where real consolidation lives.

  band:      0.1, 0.2, 0.3, 0.5, 0.75, 1 %
  quiet for: 30 min, 1 h, 2 h, 4 h, 8 h, 12 h

Everything else is unchanged from v1 (and from every coin in this project): buy at the next minute's open after a
green candle closes above the range, exits stop −0.5…−4% with the trailing stop, no time exit, $300 as 3 × $100
lots, 10 bps fee + 2 bps slippage, trend and 06–12 UTC filters.
"""

from __future__ import annotations

import run_sol_consolidation_v1 as v1
import run_sol_stage3_space_grid as grid

v1.BANDS = [0.1, 0.2, 0.3, 0.5, 0.75, 1.0]
v1.MINUTES = [30, 60, 120, 240, 480, 720]
v1.RESULT_DIR = grid.ROOT / "results" / "sol_consolidation_v2"

if __name__ == "__main__":
    v1.main()
