"""Live-engine side of the parity diff: replay each ETH entry through evaluate_exit and compare with the CSV."""

from __future__ import annotations

import json
from decimal import Decimal

import pandas as pd

import verify_stage3_v2_parity as base
import verify_eth_trend_exit_parity as parity
from app.domain.paper_execution import Candle, ExecutionConfig, Position, evaluate_exit

SLIP = Decimal("2") / Decimal("10000")


def live_exit(index, mode_a, config, ema, o, h, l, c, times):
    fill = (Decimal(str(o[index])) * (Decimal("1") + SLIP))
    position = Position("x", times[index].to_pydatetime(), Decimal(str(o[index])), fill,
                        Decimal("1"), Decimal("100"), Decimal("0"), "BNB", trend_exit_active=mode_a)
    for i in range(index, len(o)):
        candle = Candle(times[i].to_pydatetime(), Decimal(str(o[i])), Decimal(str(h[i])), Decimal(str(l[i])),
                        Decimal(str(c[i])))
        signal = evaluate_exit(position, candle, config, ema[i])
        if signal is not None:
            return i, float(signal.raw_price), signal.reason
    return -1, float("nan"), "open"


def main() -> None:
    strategy = json.loads((base.STAGE3 / "eth_strategy.json").read_text())
    config = ExecutionConfig.from_strategy(strategy)
    research = pd.read_csv(base.ROOT / "results" / "eth_research_exits.csv")
    raw = base.load_raw("ETHUSDT")
    raw = raw[raw.open_time < pd.Timestamp("2026-09-11", tz="UTC")].reset_index(drop=True)
    times = pd.DatetimeIndex(raw.open_time)
    o, h, l, c = (raw[k].to_numpy(float) for k in ["open", "high", "low", "close"])
    ema = parity.ema_series(raw, config.trend_exit_ema_minutes)

    rows = []
    for record in research.itertuples(index=False):
        index, mode_a = int(record.entry_index), record.mode == "A"
        l_idx, l_price, reason = live_exit(index, mode_a, config, ema, o, h, l, c, times)
        if l_idx != record.exit_index or abs(l_price - record.exit_price) > 1e-6:
            rows.append({"entry": str(record.entry_time)[:16], "mode": record.mode,
                         "research_exit": record.exit_index, "live_exit": l_idx,
                         "minutes_apart": l_idx - record.exit_index,
                         "research_price": round(record.exit_price, 4), "live_price": round(l_price, 4),
                         "live_reason": reason,
                         "close_vs_ema_at_research_exit": round(c[record.exit_index] - float(ema[record.exit_index]), 4)})
    pd.set_option("display.width", 260)
    if not rows:
        print(f"all {len(research)} trades match exactly")
        return
    frame = pd.DataFrame(rows)
    print(f"{len(frame)} of {len(research)} trades differ\n")
    print(frame.head(20).to_string(index=False))
    print("\nby mode:", frame["mode"].value_counts().to_dict())
    print("by live reason:", frame.live_reason.value_counts().to_dict())
    print("minutes apart:", frame.minutes_apart.describe()[["min", "50%", "max"]].round(1).to_dict())


if __name__ == "__main__":
    main()
