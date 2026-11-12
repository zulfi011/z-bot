"""The SOL consolidation rules, unchanged, on every coin with two years of data.

The settings were chosen on SOL, so running them untouched on other coins is a real out-of-sample test: nothing is
re-fitted. Two rules from the v2 grid:

  A: quiet ±1% for 8 hours, stop −3.5%, trail from +1.306% giving back 28%, only above the 30-day average, all hours
  B: quiet ±0.5% for 4 hours, stop −1.5%, trail from +1.29% giving back 24%, no trend filter, all hours

Account and costs as everywhere else: $300 as 3 × $100 lots, at most 3 open, 10 bps fee + 2 bps slippage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v1 as v1
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

COINS = ["SOLUSDT", "ETHUSDT", "BTCUSDT", "TRXUSDT", "AAVEUSDT", "LINKUSDT", "ADAUSDT", "BCHUSDT", "UNIUSDT",
         "INJUSDT", "ATOMUSDT", "PAXGUSDT", "CAKEUSDT", "FETUSDT"]
RULES = {
    "A: ±1% for 8h, stop −3.5%, trail 28%, above 30-day": dict(band=1.0, window=480, stop=3.5, activation=1.306,
                                                               giveback=28.0, trend="above_30d"),
    "B: ±0.5% for 4h, stop −1.5%, trail 24%, no trend filter": dict(band=0.5, window=240, stop=1.5, activation=1.29,
                                                                    giveback=24.0, trend="none"),
}


def column_for(rule: dict) -> int:
    for index, (mode, activation, giveback, be, stop) in enumerate(research.EXITS):
        if (mode == "plus_1pct" and be is None and np.isclose(activation, rule["activation"])
                and np.isclose(giveback, rule["giveback"]) and np.isclose(stop, rule["stop"])):
            return index
    raise LookupError(rule)


def main() -> None:
    rows = []
    for symbol in COINS:
        raw = replay.load_raw(symbol, include_holdout=True)
        raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
        grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
        research.COLS = len(research.EXITS)
        times = pd.DatetimeIndex(raw.open_time)
        daily = {d: tuple(float(v) if v is not None else np.nan for v in vals)
                 for d, vals in replay.daily_averages(raw).items()}
        for name, rule in RULES.items():
            entries = v1.breakouts(grid.HIGH, grid.LOW, grid.OPEN, grid.CLOSE, rule["band"], rule["window"])
            if not len(entries):
                continue
            feats = research.features(pd.DataFrame({"entry_index": entries}), 1, daily, times)
            keep = feats[rule["trend"]]
            entries = entries[keep]
            research.TABLE = research.exits_for(entries)
            column = column_for(rule)
            entry_times = times[entries]
            record = {"coin": symbol.removesuffix("USDT"), "rule": name}
            for window in ("full", "earlier", "later", "unseen"):
                start, end = research.WINDOWS[window]
                mask = (entry_times >= start) & (entry_times < end)
                stats = research.simulate(entries[mask], np.arange(len(entries))[mask])
                record[window] = round(float(stats["profit"][column]), 2)
                if window == "full":
                    trades = float(stats["trades"][column])
                    record["trades"] = int(trades)
                    record["win_rate"] = round(100 * float(stats["wins"][column]) / trades, 1) if trades else np.nan
                    record["drawdown"] = round(float(stats["dd"][column]), 1)
            rows.append(record)
        print("done", symbol, flush=True)
    table = pd.DataFrame(rows)
    table.to_csv(grid.ROOT / "results" / "consolidation_across_coins.csv", index=False)
    pd.set_option("display.width", 220)
    for name in RULES:
        view = table[table.rule == name].set_index("coin")[["full", "earlier", "later", "unseen", "trades",
                                                            "win_rate", "drawdown"]]
        print(f"\n== {name}")
        print(view.to_string())
        print(f"   coins profitable over the full period: {(view.full > 0).sum()} of {len(view)} | "
              f"total across coins ${view.full.sum():.2f} | median trades {int(view.trades.median())}")


if __name__ == "__main__":
    main()
