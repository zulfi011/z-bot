"""Research side of the Mode C parity check: the entries run_sol_consolidation_v4 would take."""

from __future__ import annotations

import json
import sys

import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

OUT = None  # results/<coin>_mode_c_research_entries.csv


def main() -> None:
    coin = (sys.argv[1] if len(sys.argv) > 1 else "eth").lower()
    strategy = json.loads((grid.ROOT.parent / "live_bot" / f"{coin}_strategy.json").read_text())
    setting = strategy["entry"]["consolidation_breakout"]
    raw = replay.load_raw(f"{coin.upper()}USDT", include_holdout=True)
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
    out = grid.ROOT / "results" / f"{coin}_mode_c_research_entries.csv"
    frame.to_csv(out, index=False)
    print(f"{len(frame)} research entries -> {out}")


if __name__ == "__main__":
    main()
