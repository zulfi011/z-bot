"""Which three coins get the $100, given how the app actually holds money.

$100 per coin is a CAP, not a separate wallet: the app keeps one shared pot and a coin may hold at most one
$100 lot at a time. Modelling each coin as its own isolated $100 account is wrong - a single loss would leave
$96, below a full lot, and freeze that coin for ever. So this simulates the real thing: $300 in one pot, at
most one open lot per coin, first come first served, every coin on the strategy now built for it.
"""

from __future__ import annotations

from itertools import combinations

import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as three

FEE, SLIP = 7.5 / 10_000, 2 / 10_000
LOT, POT = 100.0, 300.0
WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
BUILT = {
    "eth": (16, dict(chart=120, bars=12, zone=2.5, confirm=30, stop=3.5, arm=1.283, giveback=22.0), 4.5),
    "sol": (8, dict(chart=60, bars=24, zone=2.0, confirm=0, stop=4.0, arm=1.283, giveback=22.0), None),
    "trx": (None, dict(chart=60, bars=40, zone=2.0, confirm=3, stop=3.0, arm=1.283, giveback=22.0), None),
    "aave": (None, dict(chart=30, bars=24, zone=2.0, confirm=60, stop=3.5, arm=1.283, giveback=22.0), None),
    "btc": (None, None, None),
}


def trades_for(coin: str, new: bool) -> pd.DataFrame:
    """Every candidate trade as (entry time, exit time, return multiple), independent of how much is staked."""
    three.COIN = coin
    hours, mode_c, dip_stop = BUILT[coin]
    rule = live.load_rule(coin)
    raw = replay.load_raw(f"{coin.upper()}USDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = SLIP
    times = pd.DatetimeIndex(raw.open_time)
    grid.TIMES = times
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=hours * 60, adjust=False).mean().to_numpy() if (hours and new) else None
    use = ({"dip", "breakout"} if (hours and new) else set())
    built = three.build(raw, bullish, ema, use, mode_c=mode_c if new else None,
                        dip_stop=(dip_stop or rule["stop_pct"]) if new else rule["stop_pct"])
    rows = []
    for entry, exit_index, exit_price, source in built:
        if exit_index < 0:
            continue
        fill = grid.OPEN[entry] * (1 + SLIP)
        multiple = (exit_price * (1 - SLIP) * (1 - FEE)) / (fill * (1 + FEE))
        rows.append({"coin": coin.upper(), "entry": times[entry], "exit": times[exit_index],
                     "multiple": multiple, "source": source})
    return pd.DataFrame(rows)


def portfolio(trades: pd.DataFrame, start, end) -> dict:
    """One shared pot, one open lot per coin, at most three open."""
    window = trades[(trades.entry >= start) & (trades.entry < end)].sort_values("entry")
    cash, open_lots, pnl = POT, {}, []
    peak, worst = POT, 0.0
    for row in window.itertuples(index=False):
        for coin in [c for c, lot in open_lots.items() if lot[0] <= row.entry]:
            cash += open_lots.pop(coin)[1]
        equity = cash + LOT * len(open_lots)
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1)
        if row.coin in open_lots or len(open_lots) >= 3 or cash < LOT:
            continue
        cash -= LOT
        open_lots[row.coin] = (row.exit, LOT * row.multiple)
        pnl.append({"coin": row.coin, "pnl": LOT * row.multiple - LOT})
    for _, proceeds in open_lots.values():
        cash += proceeds
    frame = pd.DataFrame(pnl)
    return {"profit": cash - POT, "trades": len(frame), "dd": worst * 100,
            "wins": int((frame.pnl > 0).sum()) if len(frame) else 0,
            "by_coin": frame.groupby("coin").pnl.sum().round(2).to_dict() if len(frame) else {}}


def score(trades: pd.DataFrame) -> dict:
    full = portfolio(trades, *research.WINDOWS["full"])
    walk = [portfolio(trades, *research.WINDOWS[w])["profit"] for w in WF]
    return {"profit": round(full["profit"], 2), "trades": full["trades"],
            "win_rate": round(100 * full["wins"] / max(full["trades"], 1), 1),
            "unseen": round(portfolio(trades, *research.WINDOWS["unseen"])["profit"], 2),
            "walk_forward": round(sum(walk), 2), "wf_windows": f"{sum(v > 0 for v in walk)}/6",
            "drawdown": round(full["dd"], 2), "by_coin": full["by_coin"]}


def main() -> None:
    pd.set_option("display.width", 250)
    new = {coin: trades_for(coin, new=True) for coin in BUILT}
    old = {coin: trades_for(coin, new=False) for coin in BUILT}

    print("=== every three-coin choice, $300 shared, one $100 lot per coin (new strategies)")
    rows = []
    for trio in combinations(BUILT, 3):
        result = score(pd.concat([new[c] for c in trio], ignore_index=True))
        rows.append({"coins": " + ".join(c.upper() for c in trio), **{k: v for k, v in result.items() if k != "by_coin"},
                     "split": result["by_coin"]})
    print(pd.DataFrame(rows).sort_values("profit", ascending=False).set_index("coins").to_string())

    print("\n=== the same three coins, on the OLD strategies, for comparison")
    rows = []
    for trio in (("eth", "trx", "aave"), ("eth", "trx", "sol"), ("eth", "trx", "btc")):
        result = score(pd.concat([old[c] for c in trio], ignore_index=True))
        rows.append({"coins": " + ".join(c.upper() for c in trio),
                     **{k: v for k, v in result.items() if k != "by_coin"}})
    print(pd.DataFrame(rows).set_index("coins").to_string())

    print("\n=== all five at once, one lot each (three open at a time)")
    result = score(pd.concat(new.values(), ignore_index=True))
    print({k: v for k, v in result.items()})


if __name__ == "__main__":
    main()
