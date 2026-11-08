"""Pick and stress-test the NEAR candidate (same analysis as ETH and BTC)."""

import analyze_eth_full_research as analysis
import run_near_full_research  # noqa: F401  (sets SYMBOL and RESULT_DIR)

if __name__ == "__main__":
    analysis.main()
