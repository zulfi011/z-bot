"""Replay SOL or ETH history through the redesigned Stage 3 domain code (v2) and
compare with the Stage 2 backtest of the same strategy.

Usage: verify_stage3_v2_parity.py [SOLUSDT|ETHUSDT|BTCUSDT|AAVEUSDT|LINKUSDT|TRXUSDT]

Imports engine/backend/app directly (not the frozen v1 copy), so
run it in its own process, never alongside stage3_replay.
"""

from __future__ import annotations

import json
import sys
import zipfile
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
STAGE3 = PROJECT.parent / "engine"
sys.path.insert(0, str(STAGE3 / "backend"))

from app.domain.execution import (  # noqa: E402
    Candle, ExecutionConfig, FeeContext, Position, create_entry, evaluate_exit, fill_exit,
)


# The lot sizing these parity checks were run with (ETH 5 lots, the others 3, $100 each). Strategy files no longer
# carry money, so it lives here.
LOT_SIZE_USD = Decimal("100")
LOTS_BY_SYMBOL = {"ETHUSDT": 5}


def full_lot(cash: Decimal, open_lots: int, strategy: dict) -> Decimal | None:
    """One full lot when a slot is free and the cash covers it; never a partial lot."""
    lots = LOTS_BY_SYMBOL.get(strategy["market"]["symbol"], 3)
    return LOT_SIZE_USD if open_lots < lots and cash >= LOT_SIZE_USD else None
from app.domain.signal_engine import SignalCandle, build_signal_engine as build_engine  # noqa: E402

MONEY, PRICE, QTY = Decimal("0.00000001"), Decimal("0.0000000001"), Decimal("0.000000000001")
UTC = "UTC"
WINDOWS = {
    "full": (pd.Timestamp("2024-10-01", tz=UTC), pd.Timestamp("2026-08-01", tz=UTC)),
    "earlier": (pd.Timestamp("2024-10-01", tz=UTC), pd.Timestamp("2025-09-01", tz=UTC)),
    "later": (pd.Timestamp("2025-09-01", tz=UTC), pd.Timestamp("2026-08-01", tz=UTC)),
}
# Stage 2 results at 10/2 bps. SOL used the older rule (lot 3 could use leftover cash under $100);
# ETH (eth_full_research_v2) and BTC (btc_full_research_v1) already used full $100 lots.
STAGE2 = {"SOLUSDT": {"full": 51.94, "earlier": 22.61, "later": 29.34},
          "ETHUSDT": {"full": 134.05, "earlier": 83.42, "later": 47.83},
          "BTCUSDT": {"full": 71.92, "earlier": 59.23, "later": 11.73},
          "AAVEUSDT": {"full": 77.23, "earlier": 39.51, "later": 33.91},
          "LINKUSDT": {"full": 88.29, "earlier": 55.35, "later": 30.20},
          "TRXUSDT": {"full": 147.41, "earlier": 109.16, "later": 38.25}}
STRATEGY_FILES = {"SOLUSDT": "sol_strategy.json", "ETHUSDT": "eth_strategy.json", "BTCUSDT": "btc_strategy.json",
                  "AAVEUSDT": "aave_strategy.json", "LINKUSDT": "link_strategy.json", "TRXUSDT": "trx_strategy.json"}


def load_raw(symbol: str) -> pd.DataFrame:
    raw = pd.read_parquet(PROJECT / f"stage1/data/raw/{symbol}/{symbol}_1m.parquet",
                          columns=["open_time", "open", "high", "low", "close"])
    parts = []
    for path in sorted((ROOT / "data/holdout_downloads").glob(f"{symbol}-1m-*.zip")):
        with zipfile.ZipFile(path) as archive, archive.open(archive.namelist()[0]) as handle:
            part = pd.read_csv(handle, header=None, usecols=range(5))
        parts.append(part[part[0].astype(str).str.isdigit()])
    extra = pd.concat(parts)
    extra.columns = ["open_time", "open", "high", "low", "close"]
    stamps = extra.open_time.astype("int64")
    extra["open_time"] = pd.to_datetime(np.where(stamps > 10**14, stamps, stamps * 1000), unit="us", utc=True)
    extra[["open", "high", "low", "close"]] = extra[["open", "high", "low", "close"]].astype(float)
    return pd.concat([raw, extra]).drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)


def dec(value) -> Decimal:
    return Decimal(str(value))


def daily(raw: pd.DataFrame, signal_days: int) -> dict:
    grouped = raw.groupby(raw.open_time.dt.floor("D")).agg(close=("close", "last"), n=("close", "size"))
    complete = grouped[grouped.n == 1440]
    closes = [dec(v) for v in complete.close]
    out = {}
    for i, day in enumerate(complete.index):
        mean = lambda p: sum(closes[i + 1 - p:i + 1], Decimal(0)) / p if i + 1 >= p else None  # noqa: E731
        out[day + pd.Timedelta(days=1)] = (mean(signal_days), mean(7), mean(15), mean(30))
    return out


def signals(strategy: dict, raw: pd.DataFrame) -> list[pd.Timestamp]:
    minutes = int(strategy["market"]["signal_timeframe"].removesuffix("m"))
    averages = daily(raw, strategy["averages"]["signal_average_days"])
    indexed = raw.set_index("open_time")
    frame = indexed.resample(f"{minutes}min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"})
    frame = frame[indexed.close.resample(f"{minutes}min", label="left", closed="left").count() == minutes]
    engine = build_engine(strategy)
    touches, entries = {}, []
    for stamp, row in zip(frame.index, frame.itertuples(index=False)):
        sig, a7, a15, a30 = averages.get(stamp.floor("D"), (None,) * 4)
        transition = engine.process(SignalCandle(stamp.to_pydatetime(), dec(row.open), dec(row.high), dec(row.low),
                                                 dec(row.close), sig, a7, a15, a30))
        if transition.episode and transition.episode.status == "pending_confirmation":
            touches[transition.episode.episode_id] = pd.Timestamp(transition.episode.touch_time)
        if transition.resolution and transition.resolution.status == "confirmed":
            entries.append((touches[transition.resolution.episode_id], pd.Timestamp(transition.resolution.entry_time)))
    return entries


def replay(strategy: dict, raw: pd.DataFrame, entries, start, end, bnb: bool) -> dict:
    config = ExecutionConfig.from_strategy(strategy)
    times = pd.DatetimeIndex(raw.open_time)
    o, h, l, c = (raw[k].to_numpy(float) for k in ["open", "high", "low", "close"])
    wanted = sorted({int(times.searchsorted(e)) for t, e in entries if t >= start and e < end})
    cash = Decimal(str(strategy["portfolio"].get("reference_capital_usd", strategy["portfolio"].get("initial_deposit_usd"))))
    bnb_balance, bnb_price = (Decimal("1000"), Decimal("600")) if bnb else (Decimal(0), None)
    context = lambda: FeeContext(bnb, bnb_balance, bnb_price)  # noqa: E731
    positions, pnl, max_lots, pointer = [], [], 0, 0
    index = wanted[0] if wanted else len(times)
    while index < len(times):
        candle = Candle(times[index].to_pydatetime(), dec(o[index]), dec(h[index]), dec(l[index]), dec(c[index]))
        if pointer < len(wanted) and wanted[pointer] == index:
            allocation = full_lot(cash, len(positions), strategy)
            if allocation is not None:
                allocation = allocation.quantize(MONEY)
                fill = create_entry(candle.open, allocation, config, context())
                positions.append(Position(str(index), candle.open_time, candle.open, fill.fill_price.quantize(PRICE),
                                          fill.quantity.quantize(QTY), allocation, fill.fee.usd.quantize(MONEY),
                                          fill.fee.asset))
                cash -= allocation
                bnb_balance -= fill.fee.bnb.quantize(QTY)
                max_lots = max(max_lots, len(positions))
            pointer += 1
        still = []
        for position in positions:
            signal = evaluate_exit(position, candle, config)
            if signal is None:
                if position.peak_price is not None:
                    position.peak_price = position.peak_price.quantize(PRICE)
                still.append(position)
                continue
            fill = fill_exit(position, signal, config, context())
            cash_in = fill.cash_in_usd.quantize(MONEY)
            entry_bnb = position.entry_fee_usd if position.entry_fee_asset == "BNB" else Decimal(0)
            exit_bnb = fill.fee.usd.quantize(MONEY) if fill.fee.asset == "BNB" else Decimal(0)
            pnl.append(float(cash_in - position.allocation_usd - entry_bnb - exit_bnb))
            cash += cash_in
            bnb_balance -= fill.fee.bnb.quantize(QTY)
        positions = still
        if positions:
            index += 1
        elif pointer < len(wanted):
            index = wanted[pointer]
        else:
            break
    pnl = np.array(pnl)
    return {"trades": len(pnl), "win_rate_pct": round(float((pnl > 0).mean() * 100), 2),
            "profit_usd": round(float(pnl.sum()), 2), "max_open_lots": max_lots,
            "open_at_end": len(positions)}


def main() -> None:
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "SOLUSDT"
    strategy = json.loads((STAGE3 / STRATEGY_FILES[symbol]).read_text())
    raw = load_raw(symbol)
    entries = signals(strategy, raw)
    print(f"{symbol}: {len(entries)} confirmed signals (after the 06–12 UTC block)")
    rows = []
    for name, (start, end) in WINDOWS.items():
        usdt = replay(strategy, raw, entries, start, end, bnb=False)
        wallet = replay(strategy, raw, entries, start, end, bnb=True)
        rows.append({"window": name, "stage2": STAGE2[symbol][name], "full_lots_usdt_fees": usdt["profit_usd"],
                     "full_lots_bnb_wallet": wallet["profit_usd"], "trades": usdt["trades"],
                     "win_rate_pct": usdt["win_rate_pct"], "max_open_lots": usdt["max_open_lots"]})
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
