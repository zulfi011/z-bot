"""Download one more symbol in exactly the layout the SOL/ETH/BTC research uses.

- History: Binance monthly 1m archives Sep 2024 – Jul 2026 → data/raw/<SYM>/<SYM>_1m.parquet
  (same columns and dtypes as downloader.py).
- Unseen weeks: the Aug 2026 monthly archive and Sep 1–10 2026 daily archives, kept as zips in
  research/stage2/data/holdout_downloads/ (where stage3_replay.load_holdout_zips reads them).

Every archive is checked against Binance's published SHA-256 before it is used.

Usage (from research/stage1/):  python -m src.data.download_new_symbol LINKUSDT
"""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

from src.data.downloader import COLUMNS, INTERVAL, RAW_DIR

BASE = "https://data.binance.vision/data/spot"
HISTORY_MONTHS = pd.period_range("2024-09", "2026-07", freq="M")
HOLDOUT_MONTHS = ["2026-08"]
HOLDOUT_DAYS = [f"2026-09-{day:02d}" for day in range(1, 11)]
HOLDOUT_DIR = Path(__file__).resolve().parents[3] / "stage2" / "data" / "holdout_downloads"
NUMERIC = ["open", "high", "low", "close", "volume", "quote_volume", "number_of_trades",
           "taker_buy_base_volume", "taker_buy_quote_volume"]


def fetch_verified(url: str) -> bytes:
    """Archive bytes whose SHA-256 matches Binance's .CHECKSUM file."""
    response = requests.get(url, timeout=120)
    if response.status_code == 404:
        raise FileNotFoundError(url)
    response.raise_for_status()
    expected = requests.get(url + ".CHECKSUM", timeout=60)
    expected.raise_for_status()
    digest = expected.text.split()[0].strip().lower()
    actual = hashlib.sha256(response.content).hexdigest()
    if actual != digest:
        raise ValueError(f"Checksum mismatch for {url}: {actual} != {digest}")
    return response.content


def parse(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as archive, archive.open(archive.namelist()[0]) as handle:
        frame = pd.read_csv(handle, header=None, names=COLUMNS)
    frame = frame[frame["open_time"].astype(str).str.isdigit()]  # newer archives may carry a header row
    for column in ("open_time", "close_time"):
        stamps = frame[column].astype("int64")
        unit = "us" if stamps.iloc[0] > 10**14 else "ms"
        frame[column] = pd.to_datetime(stamps, unit=unit, utc=True)
    for column in NUMERIC:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["ignore"] = pd.to_numeric(frame["ignore"], errors="coerce").fillna(0).astype("int64")
    return frame


def download_history(symbol: str) -> Path:
    parts, total = [], 0
    for month in HISTORY_MONTHS:
        name = f"{symbol}-{INTERVAL}-{month}.zip"
        content = fetch_verified(f"{BASE}/monthly/klines/{symbol}/{INTERVAL}/{name}")
        total += len(content)
        parts.append(parse(content))
        print(f"  ok {name} ({len(content) / 1e6:.1f} MB, {len(parts[-1]):,} candles)", flush=True)
    frame = pd.concat(parts, ignore_index=True).drop_duplicates("open_time").sort_values("open_time")
    start, end = pd.Timestamp("2024-09-01", tz="UTC"), pd.Timestamp("2026-08-01", tz="UTC")
    frame = frame[(frame.open_time >= start) & (frame.open_time < end)].reset_index(drop=True)
    for column in ("open_time", "close_time"):
        frame[column] = frame[column].astype("datetime64[us, UTC]")
    output = RAW_DIR / symbol / f"{symbol}_1m.parquet"
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    print(f"Saved {output}: {len(frame):,} candles, {frame.open_time.min()} → {frame.open_time.max()}, "
          f"downloaded {total / 1e6:.1f} MB", flush=True)
    return output


def download_holdout(symbol: str) -> None:
    HOLDOUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [("monthly", f"{symbol}-{INTERVAL}-{month}.zip") for month in HOLDOUT_MONTHS] + \
              [("daily", f"{symbol}-{INTERVAL}-{day}.zip") for day in HOLDOUT_DAYS]
    for period, name in targets:
        content = fetch_verified(f"{BASE}/{period}/klines/{symbol}/{INTERVAL}/{name}")
        (HOLDOUT_DIR / name).write_bytes(content)
        print(f"  ok {name} ({len(content) / 1e3:.0f} kB)", flush=True)


def main() -> None:
    symbol = sys.argv[1].upper()
    print(f"History for {symbol}", flush=True)
    download_history(symbol)
    print(f"Unseen weeks for {symbol}", flush=True)
    download_holdout(symbol)


if __name__ == "__main__":
    main()
