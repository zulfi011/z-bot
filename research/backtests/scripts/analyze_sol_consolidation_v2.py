"""Pick and stress-test the SOL consolidation candidate from the second (tighter band, longer window) grid."""

import run_sol_consolidation_v2  # noqa: F401  (retargets bands, windows and the result folder)
import analyze_sol_consolidation_v1 as analysis

if __name__ == "__main__":
    analysis.main()
