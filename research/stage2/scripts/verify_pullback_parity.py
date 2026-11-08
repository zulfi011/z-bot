"""Parity gate for the pullback entry: the live rule must reproduce the research entries minute for minute.

Runs every ETH minute through `live_bot/backend/app/domain/pullback.step` (Decimal, as live does), applies the
same uptrend test and blocked hours the live service applies, and compares the buy minutes with
`eth_pullback.pullback_entries` - the function every pullback backtest in this project used.

Two runs:
  from the start   the live line seeded at the first minute, exactly like the research
  warmed up        the live line seeded 20 spans before each month, the way the service warms up after a restart;
                   entries after the warm-up must still match
"""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

import eth_pullback as pb
import run_sol_stage3_space_grid as grid

# The research imports a frozen copy of the bot under the same package name (`app`), so the live rule is loaded
# straight from its file, with the live `trend` module it depends on slotted in beside it.
LIVE_DOMAIN = Path(__file__).resolve().parents[2] / "live_bot" / "backend" / "app" / "domain"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


import app.domain  # noqa: E402  (the research's copy, already imported above)
app.domain.trend = _load("app.domain.trend", LIVE_DOMAIN / "trend.py")
live = _load("live_pullback", LIVE_DOMAIN / "pullback.py")

CONFIG = live.PullbackConfig(ema_minutes=24 * 60, dwell_minutes=180, blocked_entry_hours=(6, 12))


def live_entries(times, closes, bullish, start=0, seed_from=None):
    state = live.PullbackState()
    entries = []
    first = seed_from if seed_from is not None else start
    for index in range(first, len(closes)):
        state, reclaim = live.step(state, times[index], Decimal(str(float(closes[index]))), CONFIG)
        if reclaim is None or index < start:
            continue
        entry = index + 1
        if not bullish[index] or entry >= len(closes) - 1 or CONFIG.blocked(times[entry]):
            continue
        entries.append(entry)
    return np.asarray(entries, dtype=np.int64)


def main() -> None:
    raw, bullish, ema, mode_c = pb.setup()
    times = list(pd.DatetimeIndex(raw.open_time).to_pydatetime())
    research = pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES)
    mine = live_entries(times, grid.CLOSE, bullish)
    print(f"research entries {len(research)}, live-rule entries {len(mine)}")
    same = np.array_equal(research, mine)
    if not same:
        extra, missing = np.setdiff1d(mine, research), np.setdiff1d(research, mine)
        print(f"  only live: {[str(times[i]) for i in extra[:10]]}")
        print(f"  only research: {[str(times[i]) for i in missing[:10]]}")
    print("FROM THE START:", "EXACT MATCH" if same else "MISMATCH")

    warm = live.warmup_minutes(CONFIG)
    checked = mismatched = 0
    for month in pd.date_range("2024-11-01", "2026-09-01", freq="MS", tz="UTC"):
        start = int(np.searchsorted(grid.TIMES, month))
        stop = int(np.searchsorted(grid.TIMES, month + pd.offsets.MonthBegin(1)))
        seeded = live_entries(times[:stop + 1], grid.CLOSE[:stop + 1], bullish[:stop + 1],
                              start=start, seed_from=max(0, start - warm))
        expected = research[(research >= start) & (research < stop)]
        seeded = seeded[seeded < stop]
        checked += len(expected)
        if not np.array_equal(seeded, expected):
            mismatched += 1
            print(f"  {month:%Y-%m}: research {len(expected)} vs warmed live {len(seeded)}")
    print(f"WARMED UP ({warm} minutes of warm-up): {checked} entries checked,",
          "EXACT MATCH in every month" if mismatched == 0 else f"{mismatched} months differ")


if __name__ == "__main__":
    main()
