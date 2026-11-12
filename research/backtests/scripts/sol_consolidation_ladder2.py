"""SOL consolidation breakout: sizing, filters and stops tested one at a time on the working base rule.

Base = v5 winner: 1-hour chart, 24-hour zone, width 2%, no confirmation wait, stop −4%, trail +1.283%/22%.

Sizing note: "$300 in one lot" freezes after the first loss, because the bot only ever buys whole lots and $288
is less than $300. So sizing is tested as: 3 × $100, 2 × $150, and "all-in", where each trade uses the whole
balance and therefore compounds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

CHART, BARS, ZONE, CONFIRM, ACTIVATION, GIVEBACK = 60, 24, 2.0, 0, 1.283, 22.0
WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
PERIODS = ["full", "earlier", "later", "unseen", *WF]


def all_in(entries, exit_index, exit_price, times, keep, start, end, fee):
    """One position at a time, every trade using the whole balance (so profits compound)."""
    cash, peak, trough, trades, wins = 300.0, 300.0, 0.0, 0, 0
    busy_until = -1
    for position, entry in enumerate(entries):
        if not keep[position] or not (start <= times[entry] < end) or entry <= busy_until:
            continue
        out, price = exit_index[position], exit_price[position]
        if out < 0:
            continue
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        quantity = cash / (fill * (1 + fee))
        proceeds = quantity * price * (1 - grid.SLIP) * (1 - fee)
        trades += 1
        wins += proceeds > cash
        cash = proceeds
        peak = max(peak, cash)
        trough = min(trough, cash / peak - 1)
        busy_until = out
    return {"profit": cash - 300.0, "trades": trades, "wins": wins, "dd": trough * 100}


def fixed(entries, table, column, times, keep, lot, lots, start, end):
    research.LOT, research.LOTS, research.INITIAL, research.TABLE, research.COLS = lot, lots, 300.0, table, v4.COLS
    kept, rows = entries[keep], np.flatnonzero(keep)
    mask = (times[kept] >= start) & (times[kept] < end)
    stats = research.simulate(kept[mask], rows[mask])
    return {key: float(value[column]) for key, value in stats.items()}


def row_for(label, run):
    periods = {name: run(*research.WINDOWS[name]) for name in PERIODS}
    walk = sum(periods[name]["profit"] for name in WF)
    return {"variant": label, "trades": int(periods["full"]["trades"]),
            "win_rate": round(100 * periods["full"]["wins"] / max(periods["full"]["trades"], 1)),
            "full": periods["full"]["profit"], "earlier": periods["earlier"]["profit"],
            "later": periods["later"]["profit"], "unseen": periods["unseen"]["profit"],
            "walk_forward": walk, "wf_windows": f"{sum(periods[n]['profit'] > 0 for n in WF)}/6",
            "drawdown": periods["full"]["dd"]}


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

    v4.STOPS = [4.0, 5.0, 6.0, 8.0, 99.0]
    v4.EXITS = [(a, g, s) for s in v4.STOPS for a, g in v4.PAIRS]
    v4.COLS = len(v4.EXITS)
    table = v4.exits_for(entries)
    col = lambda stop: [i for i, (a, g, s) in enumerate(v4.EXITS)                                   # noqa: E731
                        if np.isclose(a, ACTIVATION) and g == GIVEBACK and np.isclose(s, stop)][0]
    every = np.ones(len(entries), bool)
    filters = {"base": every, "above 30-day avg": feats["above_30d"], "skip 06–12": ~feats["morning"],
               "both filters": feats["above_30d"] & ~feats["morning"]}

    for fee_bps, fee_name in ((10.0, "USDT fees"), (7.5, "BNB fees")):
        grid.FEE = fee_bps / 10_000
        rows = []
        for lot, lots, label in ((100.0, 3, "3 × $100 (base)"), (150.0, 2, "2 × $150"), (100.0, 1, "1 × $100")):
            rows.append(row_for(f"Sizing: {label}",
                                lambda s, e, lot=lot, lots=lots: fixed(entries, table, col(4.0), times, every, lot, lots, s, e)))
        rows.append(row_for("Sizing: all-in, compounding",
                            lambda s, e: all_in(entries, table[0][:, col(4.0)], table[1][:, col(4.0)], times, every, s, e, grid.FEE)))
        for name, keep in filters.items():
            if name == "base":
                continue
            rows.append(row_for(f"Filter: {name}",
                                lambda s, e, keep=keep: fixed(entries, table, col(4.0), times, keep, 100.0, 3, s, e)))
        for stop in v4.STOPS:
            label = f"Stop: −{stop:g}%" if stop < 99 else "Stop: none"
            rows.append(row_for(label, lambda s, e, stop=stop: fixed(entries, table, col(stop), times, every, 100.0, 3, s, e)))
        out = pd.DataFrame(rows)
        out.insert(0, "fees", fee_name)
        out.to_csv(grid.ROOT / "results" / f"sol_consolidation_ladder2_{fee_name.split()[0].lower()}.csv", index=False)
        pd.set_option("display.width", 250)
        print(f"\n=== {fee_name}")
        print(out.drop(columns=["fees"]).set_index("variant").round(2).to_string())


if __name__ == "__main__":
    main()
