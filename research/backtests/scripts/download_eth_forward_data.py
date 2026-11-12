"""Download completed ETHUSDT one-minute UTC days for the forward competition."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import certifi
import ssl


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "holdout_downloads"
BASE = "https://data.binance.vision/data/spot/daily/klines/ETHUSDT/1m"
START = date(2026, 9, 11)
HEADERS = {"User-Agent": "eth-forward-research/1.0"}
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _days(start: date, end_exclusive: date):
    day = start
    while day < end_exclusive:
        yield day
        day += timedelta(days=1)


def _download(day: date) -> tuple[date, str]:
    name = f"ETHUSDT-1m-{day.isoformat()}.zip"
    destination = OUTPUT / name
    if destination.exists() and destination.stat().st_size > 0:
        return day, "existing"
    url = f"{BASE}/{name}"
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=30, context=SSL_CONTEXT) as response:
            payload = response.read()
    except HTTPError as error:
        if error.code == 404:
            return day, "not_published"
        raise
    if not payload.startswith(b"PK"):
        raise ValueError(f"Unexpected archive payload for {day}")
    destination.write_bytes(payload)
    return day, "downloaded"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=START)
    parser.add_argument(
        "--end-exclusive", type=date.fromisoformat,
        default=datetime.now(timezone.utc).date(),
        help="Defaults to today UTC, so only completed UTC days are requested.",
    )
    args = parser.parse_args()
    if args.end_exclusive <= args.start:
        raise ValueError("end-exclusive must be after start")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    outcomes = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        pending = {executor.submit(_download, day): day for day in _days(args.start, args.end_exclusive)}
        for future in as_completed(pending):
            outcomes.append(future.result())
    counts = {state: sum(result == state for _, result in outcomes)
              for state in ("downloaded", "existing", "not_published")}
    print(f"ETH completed days: {len(outcomes)} requested · {counts}")


if __name__ == "__main__":
    main()
