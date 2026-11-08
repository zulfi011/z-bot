"""SOL consolidation breakout: the improvements combined (all-in sizing × every stop level).

Base rule: 1-hour chart, 24-hour zone, width 2%, no confirmation wait, trail armed at +1.283% giving back 22%.
Sizing "all-in" = one position at a time, each trade using the whole balance, so profits compound.
Also reports the monthly picture and the worst single trade, which matter more when every trade uses all the money.
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


def all_in(entries, exit_index, exit_price, times, start, end, fee, initial=300.0):
    cash, peak, worst_dd, worst_trade, ledger = initial, initial, 0.0, 0.0, []
    busy_until = -1
    for position, entry in enumerate(entries):
        if not (start <= times[entry] < end) or entry <= busy_until:
            continue
        out, price = exit_index[position], exit_price[position]
        if out < 0:
            continue
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        quantity = cash / (fill * (1 + fee))
        proceeds = quantity * price * (1 - grid.SLIP) * (1 - fee)
        change = proceeds / cash - 1
        ledger.append({"entry": times[entry], "exit": times[out], "return_pct": change * 100,
                       "balance": proceeds, "hours": (out - entry) / 60})
        worst_trade = min(worst_trade, change * 100)
        cash = proceeds
        peak = max(peak, cash)
        worst_dd = min(worst_dd, cash / peak - 1)
        busy_until = out
    frame = pd.DataFrame(ledger)
    wins = int((frame.return_pct > 0).sum()) if len(frame) else 0
    return {"profit": cash - initial, "final": cash, "trades": len(frame), "wins": wins,
            "dd": worst_dd * 100, "worst_trade_pct": worst_trade, "ledger": frame}


def main() -> None:
    raw = replay.load_raw("SOLUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    high, low, open_, close, last_minute = v4.bars_for(raw, CHART)
    entries = v4.entries_for(high, low, close, last_minute, BARS, ZONE, CONFIRM, grid.CLOSE, len(raw))

    v4.STOPS = [3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
    v4.EXITS = [(a, g, s) for s in v4.STOPS for a, g in v4.PAIRS]
    v4.COLS = len(v4.EXITS)
    table = v4.exits_for(entries)
    rows, ledgers = [], {}
    for fee_bps, fee_name in ((10.0, "USDT"), (7.5, "BNB")):
        grid.FEE = fee_bps / 10_000
        for stop in v4.STOPS:
            column = [i for i, (a, g, s) in enumerate(v4.EXITS)
                      if np.isclose(a, ACTIVATION) and g == GIVEBACK and np.isclose(s, stop)][0]
            exit_index, exit_price = table[0][:, column], table[1][:, column]
            periods = {name: all_in(entries, exit_index, exit_price, times, *research.WINDOWS[name], grid.FEE)
                       for name in ("full", "earlier", "later", "unseen", *WF)}
            walk = sum(periods[name]["profit"] for name in WF)
            rows.append({"fees": fee_name, "stop": f"−{stop:g}%", "trades": periods["full"]["trades"],
                         "win_rate": round(100 * periods["full"]["wins"] / max(periods["full"]["trades"], 1)),
                         "full": periods["full"]["profit"], "final_balance": periods["full"]["final"],
                         "earlier": periods["earlier"]["profit"], "later": periods["later"]["profit"],
                         "unseen": periods["unseen"]["profit"], "walk_forward": walk,
                         "wf_windows": f"{sum(periods[n]['profit'] > 0 for n in WF)}/6",
                         "drawdown": periods["full"]["dd"], "worst_trade": periods["full"]["worst_trade_pct"]})
            if fee_name == "BNB":
                ledgers[stop] = periods["full"]["ledger"]
    table_out = pd.DataFrame(rows)
    table_out.to_csv(grid.ROOT / "results" / "sol_consolidation_combined.csv", index=False)
    pd.set_option("display.width", 250)
    for fee in ("USDT", "BNB"):
        print(f"\n=== all-in sizing, {fee} fees")
        print(table_out[table_out.fees == fee].drop(columns=["fees"]).set_index("stop").round(2).to_string())

    best = ledgers[8.0]
    print(f"\nEvery trade of the best version (stop −8%, BNB fees), {len(best)} trades:")
    view = best.assign(entry=best.entry.dt.strftime("%Y-%m-%d %H:%M"), exit=best.exit.dt.strftime("%Y-%m-%d %H:%M"))
    print(view.round(2).to_string(index=False))
    monthly = best.assign(month=best.exit.dt.strftime("%Y-%m")).groupby("month").agg(
        trades=("return_pct", "size"), profit=("return_pct", lambda r: round(float(np.prod(1 + r / 100) - 1) * 100, 2)))
    print("\nBy month (% change of the balance):")
    print(monthly.to_string())


if __name__ == "__main__":
    main()
