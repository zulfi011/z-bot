"""SUI: exactly the ETH v2 / BTC v1 procedure (run_eth_full_research) on SUIUSDT.

Grid: 1/3/5m × 1–15 day average × ±0.1…0.5% zone × stop −0.5…−4% × giveback 10…30% with
trail start at break-even (+0.245…+0.315%) or break-even + 1% (+1.245…+1.315%), break-even
stop none/+0.5/+0.75 (+1% starts) × trend none/above 30-day/above 30-day ≤ +10% × all hours /
skip 06–12 UTC. $300, full $100 lots, ≤ 3 open, no time exit, 10/2 bps. Windows: full, earlier,
later, unseen Aug 1 – Sep 10 2026, and six walk-forward train/test pairs.
"""

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid

research.SYMBOL = "SUIUSDT"
research.RESULT_DIR = grid.ROOT / "results" / "sui_full_research_v1"

if __name__ == "__main__":
    research.main()
