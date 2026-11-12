"""Download the official public USD-M metrics and funding history (ETHUSDT by default; --symbol for others)."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import io
import json
from pathlib import Path
import ssl
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

import pandas as pd
import certifi


SYMBOL = "ETHUSDT"
METRICS_ROOT = "https://data.binance.vision/data/futures/um/daily/metrics"
FUNDING_API = "https://fapi.binance.com/fapi/v1/fundingRate"
ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"User-Agent": "eth-strategy-local-research/1.0"}
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def dates(start: date, end: date):
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)


def fetch_metrics(day: date) -> tuple[str, pd.DataFrame | None, str | None]:
    stamp = day.isoformat()
    name = f"{SYMBOL}-metrics-{stamp}.zip"
    url = f"{METRICS_ROOT}/{SYMBOL}/{name}"
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=30, context=SSL_CONTEXT) as response:
            payload = response.read()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            member = archive.namelist()[0]
            with archive.open(member) as source:
                frame = pd.read_csv(source)
        frame["archive_date"] = stamp
        return stamp, frame, None
    except HTTPError as error:
        if error.code == 404:
            return stamp, None, "not_found"
        return stamp, None, f"http_{error.code}"
    except Exception as error:  # network/archive failure is recorded in the manifest
        return stamp, None, f"{type(error).__name__}: {error}"


def fetch_funding(start: date, end: date) -> pd.DataFrame:
    start_ms = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000) - 1
    rows = []
    cursor = start_ms
    while cursor <= end_ms:
        query = urlencode({"symbol": SYMBOL, "startTime": cursor, "endTime": end_ms, "limit": 1000})
        with urlopen(Request(f"{FUNDING_API}?{query}", headers=HEADERS), timeout=30,
                     context=SSL_CONTEXT) as response:
            batch = json.loads(response.read())
        if not batch:
            break
        rows.extend(batch)
        next_cursor = int(batch[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("Funding pagination did not advance")
        cursor = next_cursor
        time.sleep(0.05)
    frame = pd.DataFrame(rows)
    if len(frame):
        frame = frame.drop_duplicates("fundingTime").sort_values("fundingTime")
        frame["funding_time"] = pd.to_datetime(frame.fundingTime, unit="ms", utc=True)
        frame["fundingRate"] = pd.to_numeric(frame.fundingRate, errors="coerce")
    return frame


def run(start: date, end: date, output: Path, workers: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    frames, failures = [], {}
    requested = list(dates(start, end))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_metrics, day): day for day in requested}
        for completed, future in enumerate(as_completed(futures), start=1):
            stamp, frame, error = future.result()
            if frame is not None:
                frames.append(frame)
            else:
                failures[stamp] = error
            if completed % 100 == 0:
                print(f"metrics: {completed}/{len(requested)}", flush=True)
    if not frames:
        counts = pd.Series(list(failures.values())).value_counts().to_dict()
        raise RuntimeError(f"No Binance futures metrics were downloaded; failures={counts}")
    metrics = pd.concat(frames, ignore_index=True)
    metrics["create_time"] = pd.to_datetime(metrics.create_time, utc=True)
    metrics = metrics.sort_values(["create_time", "archive_date"]).drop_duplicates("create_time", keep="last")
    metrics.to_csv(output / "metrics_5m.csv", index=False)

    funding = fetch_funding(start, end)
    funding.to_csv(output / "funding_rates.csv", index=False)
    manifest = {
        "symbol": SYMBOL,
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "requested_metric_days": len(requested),
        "downloaded_metric_days": len(frames),
        "missing_or_failed_metric_days": failures,
        "metric_rows": len(metrics),
        "metric_first": metrics.create_time.min().isoformat(),
        "metric_last": metrics.create_time.max().isoformat(),
        "funding_rows": len(funding),
        "funding_first": funding.funding_time.min().isoformat() if len(funding) else None,
        "funding_last": funding.funding_time.max().isoformat() if len(funding) else None,
        "metrics_source": f"{METRICS_ROOT}/{SYMBOL}",
        "funding_source": FUNDING_API,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 7, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 9, 11))
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--output", type=Path, default=None,
                        help="default: data/eth_futures_crowding for ETHUSDT, data/<coin>_futures for others")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    global SYMBOL
    SYMBOL = args.symbol.upper()
    if args.output is None:
        coin = SYMBOL.removesuffix("USDT").lower()
        args.output = ROOT / "data" / ("eth_futures_crowding" if coin == "eth" else f"{coin}_futures")
    run(args.start, args.end, args.output, args.workers)


if __name__ == "__main__":
    main()
