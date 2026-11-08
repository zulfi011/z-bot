"""Research side of the Mode C parity check: the entries run_sol_consolidation_v4 would take."""

from __future__ import annotations

import json

import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

OUT = grid.ROOT / "results" / "eth_mode_c_research_entries.csv"


def main() -> None:
    strategy = json.loads((grid.ROOT.parent / "live_bot" / "eth_strategy.json").read_text())
    setting = strategy["entry"]["consolidation_breakout"]
    raw = replay.load_raw("ETHUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    high, low, open_, close, last_minute = v4.bars_for(raw, setting["chart_minutes"])
    entries = v4.entries_for(high, low, close, last_minute, setting["zone_bars"], setting["maximum_zone_pct"],
                             setting["confirmation_wait_minutes"], grid.CLOSE, len(raw))
    blocked = strategy["entry"].get("blocked_entry_hours_utc")
    if blocked:
        hours = times[entries].hour
        entries = entries[~((hours >= blocked["start"]) & (hours < blocked["end"]))]
    frame = pd.DataFrame({"entry_index": entries, "entry_time": times[entries]})
    frame.to_csv(OUT, index=False)
    print(f"{len(frame)} research entries -> {OUT}")


if __name__ == "__main__":
    main()
