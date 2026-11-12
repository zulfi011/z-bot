"""SOL consolidation breakout: add one improvement at a time and see what each is worth.

Base = the v5 winner: 1-hour chart, zone of 24 bars (24 hours), zone width 2%, no confirmation wait, stop −4%,
trailing armed at +1.283% giving back 22%. Each step keeps everything before it.

Costs 2 bps slippage per side; profit shown with USDT fees (10 bps) and with BNB fees (7.5 bps).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

CHART, BARS, ZONE, CONFIRM = 60, 24, 2.0, 0
ACTIVATION, GIVEBACK = 1.283, 22.0
WF = [f"wf{i}" for i in range(len(research.TESTS))]


def measure(entries, table, column, times, keep, lot, lots):
    research.LOT, research.LOTS, research.INITIAL = lot, lots, 300.0
    research.TABLE = table
    research.COLS = v4.COLS
    kept = entries[keep]
    rows = np.flatnonzero(keep)
    entry_times = times[kept]
    out = {}
    for name in ("full", "earlier", "later", "unseen", *[f"{w}_test" for w in WF]):
        start, end = research.WINDOWS[name]
        mask = (entry_times >= start) & (entry_times < end)
        stats = research.simulate(kept[mask], rows[mask])
        out[name] = {key: float(value[column]) for key, value in stats.items()}
    out["wf_total"] = sum(out[f"{w}_test"]["profit"] for w in WF)
    out["wf_positive"] = sum(out[f"{w}_test"]["profit"] > 0 for w in WF)
    return out


def main() -> None:
    raw = replay.load_raw("SOLUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals)
             for d, vals in replay.daily_averages(raw).items()}
    high, low, open_, close, last_minute = v4.bars_for(raw, CHART)
    entries = v4.entries_for(high, low, close, last_minute, BARS, ZONE, CONFIRM, grid.CLOSE, len(raw))
    feats = research.features(pd.DataFrame({"entry_index": entries}), 1, daily, times)

    v4.STOPS = [4.0, 5.0, 6.0, 8.0, 99.0]          # 99 = effectively no stop
    v4.EXITS = [(a, g, s) for s in v4.STOPS for a, g in v4.PAIRS]
    v4.COLS = len(v4.EXITS)
    table = v4.exits_for(entries)
    column_for = lambda stop: [i for i, (a, g, s) in enumerate(v4.EXITS)                      # noqa: E731
                               if np.isclose(a, ACTIVATION) and g == GIVEBACK and np.isclose(s, stop)][0]

    all_in = np.ones(len(entries), bool)
    steps = [
        ("0. Base: 3 × $100 lots, stop −4%", all_in, 100.0, 3, 4.0),
        ("1. One lot of $300", all_in, 300.0, 1, 4.0),
        ("2. + only above the 30-day average", feats["above_30d"], 300.0, 1, 4.0),
        ("3. + skip 06–12 UTC entries", feats["above_30d"] & ~feats["morning"], 300.0, 1, 4.0),
    ]
    rows = []
    for label, keep, lot, lots, stop in steps:
        for fee, name in ((10.0, "USDT"), (7.5, "BNB")):
            grid.FEE = fee / 10_000
            result = measure(entries, table, column_for(stop), times, keep, lot, lots)
            rows.append({"step": label, "fees": name, "trades": int(result["full"]["trades"]),
                         "full": result["full"]["profit"], "earlier": result["earlier"]["profit"],
                         "later": result["later"]["profit"], "unseen": result["unseen"]["profit"],
                         "walk_forward": result["wf_total"], "wf_windows": f"{int(result['wf_positive'])}/6",
                         "drawdown": result["full"]["dd"],
                         "win_rate": 100 * result["full"]["wins"] / max(result["full"]["trades"], 1)})
    best_keep = steps[-1][1] if True else all_in
    for stop in v4.STOPS[1:]:
        for fee, name in ((10.0, "USDT"), (7.5, "BNB")):
            grid.FEE = fee / 10_000
            result = measure(entries, table, column_for(stop), times, best_keep, 300.0, 1)
            label = f"4. + stop −{stop:g}%" if stop < 99 else "4. + no stop at all"
            rows.append({"step": label, "fees": name, "trades": int(result["full"]["trades"]),
                         "full": result["full"]["profit"], "earlier": result["earlier"]["profit"],
                         "later": result["later"]["profit"], "unseen": result["unseen"]["profit"],
                         "walk_forward": result["wf_total"], "wf_windows": f"{int(result['wf_positive'])}/6",
                         "drawdown": result["full"]["dd"],
                         "win_rate": 100 * result["full"]["wins"] / max(result["full"]["trades"], 1)})
    table_out = pd.DataFrame(rows)
    table_out.to_csv(grid.ROOT / "results" / "sol_consolidation_ladder.csv", index=False)
    pd.set_option("display.width", 250)
    for fee in ("USDT", "BNB"):
        print(f"\n=== {fee} fees")
        view = table_out[table_out.fees == fee].drop(columns=["fees"]).set_index("step")
        print(view.round(2).to_string())


if __name__ == "__main__":
    main()
