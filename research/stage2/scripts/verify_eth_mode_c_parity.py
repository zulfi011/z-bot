"""Does the live Mode C detector find exactly the breakouts the research found?

The research generates entries with a vectorised sweep (`run_sol_consolidation_v4.entries_for`); the bot walks
bars one at a time in `app.domain.consolidation`. They must agree minute for minute, or the strategy that was
measured is not the strategy that will trade.

Run in its own process: it imports live_bot's domain, which must not share a process with stage3_replay.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pandas as pd

import verify_stage3_v2_parity as base
from app.domain.consolidation import ConsolidationConfig, build_bars, confirm, find_breakouts


class Candle:
    __slots__ = ("open_time", "high", "low", "close")

    def __init__(self, open_time, high, low, close):
        self.open_time, self.high, self.low, self.close = open_time, high, low, close


def main() -> None:
    strategy = json.loads((base.STAGE3 / "eth_strategy.json").read_text())
    config = ConsolidationConfig.from_strategy(strategy)
    print(f"Mode C: {config.chart_minutes}m chart, {config.zone_bars} bars, <= {config.maximum_zone_pct}% wide, "
          f"{config.confirmation_wait_minutes} min wait, stop -{config.stop_pct}%", flush=True)

    raw = base.load_raw("ETHUSDT")
    raw = raw[raw.open_time < pd.Timestamp("2026-09-11", tz="UTC")].reset_index(drop=True)
    times = pd.DatetimeIndex(raw.open_time)
    candles = [Candle(time.to_pydatetime(), Decimal(str(h)), Decimal(str(l)), Decimal(str(c)))
               for time, h, l, c in zip(times, raw.high, raw.low, raw.close)]
    closes = {candle.open_time: candle.close for candle in candles}

    bars = build_bars(candles, config.chart_minutes)
    breakouts = find_breakouts(bars, config)
    live_entries = []
    for breakout in breakouts:
        state, entry_at = confirm(breakout, closes)
        if state == "confirmed" and not config.blocked(entry_at):
            live_entries.append(entry_at)
    live_index = sorted(int(times.searchsorted(pd.Timestamp(at))) for at in live_entries)
    print(f"live engine: {len(bars):,} bars, {len(breakouts)} breakouts, {len(live_index)} confirmed entries",
          flush=True)

    research = pd.read_csv(base.ROOT / "results" / "eth_mode_c_research_entries.csv")
    research_index = sorted(research.entry_index.tolist())
    print(f"research:    {len(research_index)} entries")

    only_live = sorted(set(live_index) - set(research_index))
    only_research = sorted(set(research_index) - set(live_index))
    if not only_live and not only_research:
        print(f"\nall {len(live_index)} entries match exactly\nPARITY OK")
        return
    print(f"\nonly the live engine found ({len(only_live)}): {[str(times[i]) for i in only_live[:8]]}")
    print(f"only the research found ({len(only_research)}): {[str(times[i]) for i in only_research[:8]]}")
    print("PARITY FAILED - do not deploy")


if __name__ == "__main__":
    main()
