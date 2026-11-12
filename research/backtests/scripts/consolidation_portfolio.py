"""How to get the most out of the consolidation strategy: one shared $300 pot across SOL, ETH and TRX.

Each coin runs its OWN rule (the one its own full grid found). Signals are rare, so the interesting question is
how often they collide and how much of the time the money is idle.

  SOL   60m chart,  24h zone, 2.0%, no wait,   stop -4.0%
  ETH  120m chart,  24h zone, 2.5%, 30m wait,  stop -3.5%
  TRX   60m chart,  40h zone, 2.0%, 3m wait,   stop -3.0%

Trailing stop armed at +1.283% giving back 22% everywhere. Costs 2 bps slippage per side, 7.5 bps BNB fees.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

RULES = {"SOL": ("SOLUSDT", 60, 24, 2.0, 0, 4.0), "ETH": ("ETHUSDT", 120, 12, 2.5, 30, 3.5),
         "TRX": ("TRXUSDT", 60, 40, 2.0, 3, 3.0), "BTC": ("BTCUSDT", 10, 20, 0.3, 1, 2.0),
         "AAVE": ("AAVEUSDT", 30, 24, 2.0, 60, 3.5)}
GIVEBACK = 22.0
WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
FEE, SLIP = 7.5 / 10_000, 2 / 10_000


def trades_for(coin) -> pd.DataFrame:
    symbol, chart, bars, zone, confirm, stop = RULES[coin]
    raw = replay.load_raw(symbol, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    high, low, open_, close, last_minute = v4.bars_for(raw, chart)
    entries = v4.entries_for(high, low, close, last_minute, bars, zone, confirm, grid.CLOSE, len(raw))
    v4.STOPS = [stop]
    v4.EXITS = [(a, g, s) for s in v4.STOPS for a, g in v4.PAIRS]
    v4.COLS = len(v4.EXITS)
    idx, price, code = v4.exits_for(entries)
    column = [i for i, (a, g, s) in enumerate(v4.EXITS) if g == GIVEBACK][0]
    rows = []
    for position, entry in enumerate(entries):
        out = idx[position, column]
        if out < 0:
            continue
        rows.append({"coin": coin, "entry_time": times[entry], "exit_time": times[out],
                     "fill": grid.OPEN[entry] * (1 + SLIP), "exit_price": price[position, column],
                     "hours": (out - entry) / 60})
    frame = pd.DataFrame(rows)
    frame["gross_pct"] = (frame.exit_price / frame.fill - 1) * 100
    return frame


def run(trades: pd.DataFrame, start, end, initial=300.0, cap=1.0, max_open=3):
    """Shared pot, first come first served. cap = the most of the balance one trade may use."""
    trades = trades[(trades.entry_time >= start) & (trades.entry_time < end)].sort_values("entry_time")
    cash, open_positions, taken, skipped = initial, [], [], 0
    peak, worst_dd = initial, 0.0
    busy_minutes, span = pd.Timedelta(0), end - start
    for _, signal in trades.iterrows():
        matured = [p for p in open_positions if p["exit_time"] <= signal.entry_time]
        for position in matured:
            cash += position["proceeds"]
            peak = max(peak, cash + sum(p["stake"] for p in open_positions if p not in matured))
        open_positions = [p for p in open_positions if p["exit_time"] > signal.entry_time]
        equity = cash + sum(p["stake"] for p in open_positions)
        stake = min(cash, equity * cap)
        if len(open_positions) >= max_open or stake < 10:
            skipped += 1
            continue
        quantity = stake / (signal.fill * (1 + FEE))
        proceeds = quantity * signal.exit_price * (1 - SLIP) * (1 - FEE)
        cash -= stake
        open_positions.append({"exit_time": signal.exit_time, "stake": stake, "proceeds": proceeds})
        busy_minutes += signal.exit_time - signal.entry_time
        taken.append({"coin": signal.coin, "return_pct": (proceeds / stake - 1) * 100, "profit": proceeds - stake})
        equity = cash + sum(p["stake"] for p in open_positions)
        peak = max(peak, equity)
        worst_dd = min(worst_dd, equity / peak - 1)
    cash += sum(p["proceeds"] for p in open_positions)
    frame = pd.DataFrame(taken)
    wins = int((frame.return_pct > 0).sum()) if len(frame) else 0
    return {"profit": cash - initial, "trades": len(frame), "wins": wins, "skipped": skipped,
            "dd": worst_dd * 100, "busy_pct": 100 * busy_minutes / span, "ledger": frame}


def main() -> None:
    per_coin = {coin: trades_for(coin) for coin in RULES}
    for coin, frame in per_coin.items():
        print(f"{coin}: {len(frame)} signals, median hold {frame.hours.median():.1f} h, "
              f"median move {frame.gross_pct.median():+.2f}%")
    everything = pd.concat(per_coin.values(), ignore_index=True)
    pd.set_option("display.width", 220)

    print("\n=== how much of the time is money actually working? (whole period, one coin alone, all-in)")
    span = research.WINDOWS["full"][1] - research.WINDOWS["full"][0]
    for coin, frame in per_coin.items():
        inside = frame[(frame.entry_time >= research.WINDOWS["full"][0]) & (frame.entry_time < research.WINDOWS["full"][1])]
        busy = inside.hours.sum() / (span.total_seconds() / 3600) * 100
        print(f"  {coin}: {len(inside)} trades, in the market {busy:.1f}% of the time")

    print("\n=== one shared $300 pot, three coins, BNB fees")
    rows = []
    for label, cap, max_open in [("all-in, one at a time", 1.0, 1), ("half the pot, 2 open", 0.5, 2),
                                 ("a third each, 3 open", 1 / 3, 3)]:
        periods = {name: run(everything, *research.WINDOWS[name], cap=cap, max_open=max_open)
                   for name in ("full", "earlier", "later", "unseen", *WF)}
        full = periods["full"]
        rows.append({"sharing": label, "trades": full["trades"], "missed": full["skipped"],
                     "win_rate": round(100 * full["wins"] / max(full["trades"], 1)),
                     "full": full["profit"], "earlier": periods["earlier"]["profit"],
                     "later": periods["later"]["profit"], "unseen": periods["unseen"]["profit"],
                     "walk_forward": sum(periods[w]["profit"] for w in WF),
                     "wf_windows": f"{sum(periods[w]['profit'] > 0 for w in WF)}/6",
                     "drawdown": full["dd"], "busy_pct": full["busy_pct"]})
    print(pd.DataFrame(rows).set_index("sharing").round(2).to_string())

    print("\n=== each coin alone with its own $300 (for comparison)")
    rows = []
    for coin, frame in per_coin.items():
        periods = {name: run(frame, *research.WINDOWS[name], cap=1.0, max_open=1) for name in ("full", *WF)}
        rows.append({"coin": coin, "trades": periods["full"]["trades"], "full": periods["full"]["profit"],
                     "walk_forward": sum(periods[w]["profit"] for w in WF),
                     "drawdown": periods["full"]["dd"], "busy_pct": periods["full"]["busy_pct"]})
    print(pd.DataFrame(rows).set_index("coin").round(2).to_string())

    print("\n=== do the three coins' signals collide?")
    inside = everything[(everything.entry_time >= research.WINDOWS["full"][0])
                        & (everything.entry_time < research.WINDOWS["full"][1])].sort_values("entry_time")
    clashes = 0
    for _, signal in inside.iterrows():
        others = inside[(inside.coin != signal.coin) & (inside.entry_time <= signal.entry_time)
                        & (inside.exit_time > signal.entry_time)]
        clashes += len(others) > 0
    print(f"  {len(inside)} signals; {clashes} arrived while another coin was already holding "
          f"({100 * clashes / max(len(inside), 1):.0f}%)")


if __name__ == "__main__":
    main()
