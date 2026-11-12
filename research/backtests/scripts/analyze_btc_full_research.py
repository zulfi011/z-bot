"""Pick and stress-test the BTC candidate (same analysis as ETH)."""

import analyze_eth_full_research as analysis
import run_btc_full_research  # noqa: F401  (sets SYMBOL and RESULT_DIR)

if __name__ == "__main__":
    analysis.main()
