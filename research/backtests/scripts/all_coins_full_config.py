"""What each coin earns at 3 x $100, and at the FULL configuration its strategy actually supports.

Three of the coins have nothing to switch on - TRX, BTC and AAVE are one shared pool of lots, and their only
lever is how much money those lots hold. Two have lot-based add-ons that ship switched off:

  ETH   core lots shared by the dip, Mode C and the pullback, plus a pyramid add-on that can hold lots of its
        own: +1% steps, up to 3 adds, each add carrying its own -4.5% stop and held against the 16-hour line
  SOL   core lots shared by the dip and Mode C, plus a pyramid add-on with 2 lots of its own: +0.5% steps, up
        to 2 adds, each add parking its parent's stop and sold the minute the parent is

So each coin is shown three ways: at 3 x $100, at the same money concentrated in bigger lots, and - where there
is one - at the full configuration with the add-on switched on and funded. Same engine, same windows, hourly
mark-to-market drawdown, BNB fees, the live buying rule.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import eth_regime as rg
import all_coins_compare as cmp
import sol_wide_stop as w
import trx_volume_filter as vf

CORE = {"dip", "breakout", "pullback"}
PYRA = {"pyramid"}


def adds_for(parents, step, levels, line, arm, giveback, stop, blocked, with_parent):
    """The pyramid adds a coin's rule would take, given the lots it already holds."""
    out = []
    for parent in parents:
        if parent["source"] == "pyramid":
            continue
        fill = grid.OPEN[parent["entry"]] * (1 + grid.SLIP)
        start, stop_at = parent["entry"] + 1, parent["exit"]
        for level in range(1, levels + 1):
            if start >= stop_at:
                break
            close, above = grid.CLOSE[start:stop_at], line[start:stop_at]
            hit = np.flatnonzero((close >= fill * (1 + level * step / 100)) & (close > above))
            if not len(hit):
                break
            entry = start + int(hit[0]) + 1
            if entry >= stop_at:
                break
            hour = grid.TIMES[entry].hour
            if not (blocked and blocked[0] <= hour < blocked[1]):
                if with_parent:
                    exit_at, price, why = parent["exit"], parent["price"], 8
                else:
                    exit_at, price, why = w.resolve(entry, arm, giveback, stop, line)
                out.append({"entry": entry, "exit": exit_at, "price": price, "source": "pyramid", "why": why})
            start = entry
    return out


def main() -> None:
    pd.set_option("display.width", 255)
    books, markets = {}, {}
    for name, builder in (("TRX", cmp.trx), ("AAVE", cmp.aave), ("ETH", cmp.eth), ("SOL", cmp.sol),
                          ("BTC", cmp.btc)):
        books[name] = builder()
        markets[name] = cmp.market()

    # the two add-ons, each built against its own coin's prices
    cmp.point_at(markets["ETH"])
    eth_rule = live.load_rule("eth")
    eth_line = pd.Series(grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    eth_adds = adds_for(books["ETH"], 1.0, 3, eth_line, eth_rule["activation_pct"], eth_rule["giveback_pct"],
                        4.5, eth_rule["blocked"], with_parent=False)
    eth_full = sorted(books["ETH"] + eth_adds, key=lambda t: t["entry"])

    cmp.point_at(markets["SOL"])
    sol_rule = live.load_rule("sol")
    sol_line = pd.Series(grid.CLOSE).ewm(span=8 * 60, adjust=False).mean().to_numpy()
    sol_adds = adds_for(books["SOL"], 0.5, 2, sol_line, sol_rule["activation_pct"], sol_rule["giveback_pct"],
                        sol_rule["stop_pct"], sol_rule["blocked"], with_parent=True)
    sol_full = sorted(books["SOL"] + sol_adds, key=lambda t: t["entry"])
    print(f"ETH offers {len(eth_adds)} pyramid adds; SOL offers {len(sol_adds)}")

    rows = []
    plans = [
        ("TRX", "3 x $100", books["TRX"], [(3, CORE)], 100.0),
        ("TRX", "3 x $167 ($500)", books["TRX"], [(3, CORE)], 500 / 3),
        ("TRX", "3 x $267 ($800)", books["TRX"], [(3, CORE)], 800 / 3),
        ("AAVE", "3 x $100", books["AAVE"], [(3, CORE)], 100.0),
        ("AAVE", "3 x $167 ($500)", books["AAVE"], [(3, CORE)], 500 / 3),
        ("AAVE", "3 x $267 ($800)", books["AAVE"], [(3, CORE)], 800 / 3),
        ("ETH", "3 x $100", books["ETH"], [(3, CORE)], 100.0),
        ("ETH", "5 x $100 core ($500)", books["ETH"], [(5, CORE)], 100.0),
        ("ETH", "5 core + 3 pyramid ($800)", eth_full, [(5, CORE), (3, PYRA)], 100.0),
        ("ETH", "3 core + 3 pyramid ($600)", eth_full, [(3, CORE), (3, PYRA)], 100.0),
        ("ETH", "3 x $267 ($800), no add-on", books["ETH"], [(3, CORE)], 800 / 3),
        ("SOL", "3 x $100", books["SOL"], [(3, CORE)], 100.0),
        ("SOL", "3 core + 2 pyramid ($500)", sol_full, [(3, CORE), (2, PYRA)], 100.0),
        ("SOL", "3 x $167 ($500), no add-on", books["SOL"], [(3, CORE)], 500 / 3),
        ("BTC", "3 x $100", books["BTC"], [(3, CORE)], 100.0),
        ("BTC", "3 x $167 ($500)", books["BTC"], [(3, CORE)], 500 / 3),
    ]
    for coin, label, book, pots, lot in plans:
        cmp.point_at(markets[coin])
        w.LOT = lot
        row = vf.score(f"{coin} — {label}", book, pots)
        led = w.simulate(book, pots, *research.WINDOWS["full"])["ledger"]
        adds = led[led.source == "pyramid"] if len(led) else led
        rows.append({**row, "adds": len(adds), "add_pnl": round(adds.pnl.sum(), 2) if len(adds) else 0.0,
                     "per $100 wf": round(row["walk_forward"] / (row["money"] / 100), 2)})
        w.LOT = 100.0
    print("\n=== what each coin earns, at 3 x $100 and at everything its strategy supports")
    print(pd.DataFrame(rows).set_index("setup")[
        ["money", "trades", "adds", "add_pnl", "win%", "profit", "walk_forward", "windows", "unseen",
         "mtm_dd%", "per $100 wf"]].to_string())


if __name__ == "__main__":
    main()
