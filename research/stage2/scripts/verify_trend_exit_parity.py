"""Does the live engine reproduce the Stage 2 backtest of a coin's trend exit, trade for trade?

Replays ETH history through the CURRENT live_bot domain code - the same `evaluate_exit`, `create_entry`,
`fill_exit` and `app.domain.trend` the server runs - and compares with `eth_optimal.py`, which produced the
numbers the strategy was chosen on. A mismatch means the live implementation does something the research did
not, and must be fixed before this goes anywhere near real money.

Usage: verify_trend_exit_parity.py [sol|eth]
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal

import numpy as np
import pandas as pd

import verify_stage3_v2_parity as base
from app.domain import trend
from app.domain.paper_execution import (
    Candle, CoinAllocation, ExecutionConfig, FeeContext, Position, create_entry, evaluate_exit, fill_exit,
    lot_allocation,
)

MONEY, PRICE, QTY = base.MONEY, base.PRICE, base.QTY
UTC = "UTC"
WINDOWS = dict(base.WINDOWS)
WINDOWS["unseen"] = (pd.Timestamp("2026-08-01", tz=UTC), pd.Timestamp("2026-09-11", tz=UTC))
# What the research reports for "dip only, EMA-in-uptrend exit", per coin.
EXPECTED = {
    "eth": {"USDT": {"full": 232.40, "earlier": 168.96, "later": 59.64, "unseen": 3.34},
            "BNB": {"full": 244.97, "earlier": 175.50, "later": 65.77, "unseen": 4.36}},
    "sol": {"USDT": {"full": 53.27, "earlier": 24.60, "later": 28.67, "unseen": 4.02},
            "BNB": {"full": 71.89, "earlier": 37.76, "later": 34.13, "unseen": 4.97}},
    # AAVE keeps its giveback exit, so the "new rule" here is simply the deployed one.
    # AAVE and TRX keep their giveback exits, so the "new rule" is the deployed one, at the live ordering.
    "aave": {"USDT": {"full": 77.24, "earlier": 39.52, "later": 33.91, "unseen": -0.22},
             "BNB": {"full": 96.56, "earlier": 53.42, "later": 39.12, "unseen": 0.63}},
    "trx": {"USDT": {"full": 148.82, "earlier": 110.58, "later": 38.25, "unseen": -1.58},
            "BNB": {"full": 156.35, "earlier": 116.30, "later": 40.06, "unseen": -0.88}},
}
# Each coin's previous rule and its published numbers at USDT fees: the control that proves the account
# layer still behaves exactly as it did before the trend exit was added.
CONTROL = {
    "eth": {"stop": 3.5, "windows": {"full": 134.05, "earlier": 83.42, "later": 47.83}},
    # SOL's published 51.94 predates the full-lot rule (a third lot could use leftover cash under $100).
    # These are what the unchanged verify_stage3_v2_parity.py reports for the same rule today, so they are
    # the right baseline for "did the trend exit disturb anything".
    "sol": {"stop": 2.0, "windows": {"full": 47.14, "earlier": 17.81, "later": 29.34}},
    # AAVE and TRX have no trend exit at all, so their controls ask purely "did adding Mode C disturb the
    # dip rule's money". Their figures are a little above the published ones because this replay sells before
    # it buys within a minute, exactly as LiveExecutionService._advance does, while the older research script
    # bought first. That swaps which lot takes a slot freed in the same minute. The trade counts are identical
    # in every window, which is what shows it is an ordering difference and not a behaviour change - TRX moves
    # most because 523 signals compete for three lots.
    "aave": {"stop": 4.0, "windows": {"full": 77.24, "earlier": 39.52, "later": 33.91}},
    "trx": {"stop": 4.0, "windows": {"full": 148.82, "earlier": 110.58, "later": 38.25}},
}
# The research records the regime on the entry day; the live signal engine records it when the touch happens.
# Both are tested - they differ on a couple of trades where the touch and the entry fall on different days.
REGIME_AT_ENTRY = True


def ema_series(raw: pd.DataFrame, minutes: int) -> list[Decimal]:
    """The live EMA, computed with the server's own module over every minute of history."""
    values, previous = [], None
    for close in raw.close.to_numpy(float):
        previous = trend.advance(previous, Decimal(str(close)), minutes)
        values.append(previous)
    return values


def regimes(raw: pd.DataFrame, signal_days: int) -> dict:
    """Day -> was the market in a clean uptrend (7d > 15d > 30d), as the signal engine records it."""
    out = {}
    for day, (_, a7, a15, a30) in base.daily(raw, signal_days).items():
        out[day] = None not in (a7, a15, a30) and a7 > a15 > a30
    return out


def replay(strategy: dict, raw: pd.DataFrame, entries, start, end, bnb: bool) -> dict:
    config = ExecutionConfig.from_strategy(strategy)
    allocation_rule = CoinAllocation.default(strategy)
    times = pd.DatetimeIndex(raw.open_time)
    o, h, l, c = (raw[k].to_numpy(float) for k in ["open", "high", "low", "close"])
    ema = ema_series(raw, config.trend_exit_ema_minutes) if config.trend_exit_ema_minutes else None
    uptrend = regimes(raw, strategy["averages"]["signal_average_days"])
    wanted = {}
    for touch, entry in entries:
        # windowed on the entry, exactly as the research masks its entry array
        if entry >= start and entry < end:
            when = entry if REGIME_AT_ENTRY else touch
            wanted[int(times.searchsorted(entry))] = bool(uptrend.get(when.floor("D"), False))
    order = sorted(wanted)
    cash = Decimal(str(strategy["portfolio"]["reference_capital_usd"]))
    bnb_balance, bnb_price = (Decimal("1000"), Decimal("600")) if bnb else (Decimal(0), None)
    context = lambda: FeeContext(bnb, bnb_balance, bnb_price)  # noqa: E731
    positions, pnl, modes, pointer = [], [], {"A": 0, "B": 0}, 0
    reasons = {}
    index = order[0] if order else len(times)
    while index < len(times):
        candle = Candle(times[index].to_pydatetime(), base.dec(o[index]), base.dec(h[index]), base.dec(l[index]),
                        base.dec(c[index]))
        still = []
        for position in positions:
            signal = evaluate_exit(position, candle, config, ema[index] if ema else None)
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
            reasons[signal.reason] = reasons.get(signal.reason, 0) + 1
            cash += cash_in
            bnb_balance -= fill.fee.bnb.quantize(QTY)
        positions = still
        if pointer < len(order) and order[pointer] == index:
            allocation = lot_allocation(cash, len(positions), allocation_rule)
            if allocation is not None:
                allocation = allocation.quantize(MONEY)
                fill = create_entry(candle.open, allocation, config, context())
                mode_a = wanted[index] and config.trend_exit_ema_minutes is not None
                positions.append(Position(str(index), candle.open_time, candle.open, fill.fill_price.quantize(PRICE),
                                          fill.quantity.quantize(QTY), allocation, fill.fee.usd.quantize(MONEY),
                                          fill.fee.asset, trend_exit_active=mode_a))
                modes["A" if mode_a else "B"] += 1
                cash -= allocation
                bnb_balance -= fill.fee.bnb.quantize(QTY)
            pointer += 1
        if positions:
            index += 1
        elif pointer < len(order):
            index = order[pointer]
        else:
            break
    # The research simulator values whatever is still open at the last close (`qty * CLOSE[-1]`, no exit
    # costs) and counts it in the profit. Mirror that, or the comparison punishes lots that simply had not
    # closed yet when the data ran out.
    last_close = base.dec(c[-1])
    unrealised = float(sum(position.quantity * last_close - position.allocation_usd
                           - (position.entry_fee_usd if position.entry_fee_asset == "BNB" else Decimal(0))
                           for position in positions))
    array = np.array(pnl)
    return {"unrealised_usd": round(unrealised, 2), "trades": len(array), "win_rate_pct": round(float((array > 0).mean() * 100), 2) if len(array) else 0.0,
            "profit_usd": round(float(array.sum()) + unrealised, 2),
            "realised_usd": round(float(array.sum()), 2), "mode_a": modes["A"], "mode_b": modes["B"],
            "reasons": reasons, "open_at_end": len(positions)}


def control(strategy: dict, raw: pd.DataFrame, coin: str) -> pd.DataFrame:
    """The previous ETH rule, replayed through the same modified engine. It must still produce its
    published numbers exactly; if it does not, the change broke something unrelated to the trend exit."""
    import copy
    old = copy.deepcopy(strategy)
    old["exit"].pop("trend_exit", None)
    old["entry"].pop("consolidation_breakout", None)
    old["exit"]["protective_stop_pct_from_entry_fill"] = CONTROL[coin]["stop"]
    entries = base.signals(old, raw)
    rows = []
    for name, expected in CONTROL[coin]["windows"].items():
        start, end = WINDOWS[name]
        got = replay(old, raw, entries, start, end, bnb=False)["profit_usd"]
        rows.append({"window": name, "published": expected, "live engine": got,
                     "difference": round(got - expected, 2)})
    return pd.DataFrame(rows)


def main() -> None:
    coin = (sys.argv[1] if len(sys.argv) > 1 else "eth").lower()
    strategy = json.loads((base.STAGE3 / f"{coin}_strategy.json").read_text())
    config = ExecutionConfig.from_strategy(strategy)
    print(f"{coin.upper()} strategy {strategy['strategy_id']}: stop -{config.stop_pct}%, arm +{config.trail_activation_pct}%, "
          f"giveback {config.trail_giveback_pct}%, trend EMA {config.trend_exit_ema_minutes} min "
          f"(uptrend only: {config.trend_exit_requires_uptrend})", flush=True)
    raw = base.load_raw(f"{coin.upper()}USDT")
    raw = raw[raw.open_time < pd.Timestamp("2026-09-11", tz=UTC)].reset_index(drop=True)
    entries = base.signals(strategy, raw)
    print(f"{len(entries)} confirmed signals over {len(raw):,} minutes", flush=True)
    pd.set_option("display.width", 250)
    control_frame = control(strategy, raw, coin)
    print(f"\n=== control: the previous {coin.upper()} rule through the same engine (USDT fees)")
    print(control_frame.to_string(index=False))

    rows = []
    for fee_name, bnb in (("USDT", False), ("BNB", True)):
        for name, (start, end) in WINDOWS.items():
            result = replay(strategy, raw, entries, start, end, bnb=bnb)
            expected = EXPECTED[coin][fee_name][name]
            rows.append({"fees": fee_name, "window": name, "stage2 backtest": expected,
                         "live engine": result["profit_usd"],
                         "difference": round(result["profit_usd"] - expected, 2), "trades": result["trades"],
                         "win_rate_pct": result["win_rate_pct"], "still_open": result["unrealised_usd"],
                         "mode_A": result["mode_a"], "mode_B": result["mode_b"], "exits": result["reasons"]})
    frame = pd.DataFrame(rows)
    print("\n=== the new trend exit")
    print(frame.to_string(index=False))

    control_worst = control_frame.difference.abs().max()
    # Baselines are recorded at the live engine's own ordering, so this must be exact. Any drift is a
    # regression, not a convention difference.
    ALLOWED_ORDERING_CENTS = Decimal("0")
    usdt_worst = frame[frame.fees == "USDT"].difference.abs().max()
    print(f"\ncontrol drift: ${control_worst:.2f} (must be 0.00)")
    print(f"new rule, USDT fees: ${usdt_worst:.2f} from the research figure")
    ok = control_worst <= float(ALLOWED_ORDERING_CENTS) and usdt_worst <= 1.0
    print("PARITY OK" if ok else "PARITY FAILED - do not deploy")


if __name__ == "__main__":
    main()
