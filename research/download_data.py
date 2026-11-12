"""Download the price data the research uses, and build the files its scripts read.

    python research/download_data.py                  # all six symbols (about 1 GB, a few minutes per symbol)
    python research/download_data.py SOLUSDT ETHUSDT  # only some

For each symbol it downloads Binance's public 1-minute spot archives (Sep 2024 - Jul 2026), checks every archive
against Binance's published SHA-256, and writes:

    research/foundations/data/raw/<SYMBOL>/<SYMBOL>_1m.parquet          the 1-minute history
    research/backtests/data/holdout_downloads/                         Aug 2026 + 1-10 Sep 2026, kept for unseen tests
    research/foundations/data/processed/<SYMBOL>/...                     3m/5m and daily candles, averages, distances

BNBUSDT is only needed for fee prices, so it gets the raw history and nothing else. A symbol whose history file is
already there is not downloaded again (delete it to refresh). Nothing here needs a Binance account or key.
Needs: pip install -r research/backtests/requirements.txt
"""

import os
import sys
from pathlib import Path

FOUNDATIONS = Path(__file__).resolve().parent / "foundations"
COINS = ["SOLUSDT", "ETHUSDT", "BTCUSDT", "AAVEUSDT", "TRXUSDT"]
FEE_SYMBOL = "BNBUSDT"

# The foundations code works with paths relative to research/foundations.
os.chdir(FOUNDATIONS)
sys.path.insert(0, str(FOUNDATIONS))

from src.data import download_new_symbol as download  # noqa: E402
from src.indicators.attach_averages import TIMEFRAMES, attach_to_timeframe, calculate_daily_averages  # noqa: E402
from src.indicators.available_closes import create_available_closes  # noqa: E402
from src.indicators.distance_from_average import process as attach_distances  # noqa: E402
from src.processing.daily import create_daily_data  # noqa: E402
from src.processing.resampling import resample_symbol  # noqa: E402


def main(symbols: list[str]) -> None:
    for symbol in symbols:
        raw = FOUNDATIONS / "data" / "raw" / symbol / f"{symbol}_1m.parquet"
        print(f"\n== {symbol}", flush=True)
        if raw.exists():
            print(f"history already there: {raw.relative_to(FOUNDATIONS.parent)}")
        else:
            download.download_history(symbol)
        download.download_holdout(symbol)
        if symbol == FEE_SYMBOL:
            continue
        resample_symbol(symbol)
        create_daily_data(symbol)
        create_available_closes(symbol)          # only completed daily closes, as the bot sees them
        averages = calculate_daily_averages(symbol)
        for timeframe in TIMEFRAMES:
            attach_to_timeframe(symbol, timeframe, averages)
            attach_distances(symbol, timeframe)
    print("\nDone. The research scripts in research/backtests/scripts can now run.")


if __name__ == "__main__":
    main(sys.argv[1:] or COINS + [FEE_SYMBOL])
