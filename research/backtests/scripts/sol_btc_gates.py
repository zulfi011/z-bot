"""Does knowing what BTC is doing improve SOL?

Every SOL rule we have reads only SOL's own chart. BTC leads this market and SOL is a high-beta follower, so
BTC's state is information SOL's price has not already used. Two families of gate, both daily, both built from
completed UTC days only and effective the next day - the convention the averages already use, so no lookahead:

  BTC regime      is BTC itself healthy?      close above its own 7/15/30-day average, its averages stacked up
                  or not stacked down, BTC up over the last 1/3/7 days
  SOL/BTC ratio   is SOL leading or lagging?  the ratio above its own 7/15/30-day average, or rising today

Every gate is also tried INVERTED (buy only when BTC is weak, or only when SOL is lagging), because SOL is a
mean-reverter and the obvious direction is not obviously right. Every single gate and every PAIR of gates (both
must agree) is tried, on the dip alone, on Mode C alone, and on both ways in.

Two ways to use a gate:
  SHARED     the deployed 3 lots only buy when the gate agrees - fewer trades, same money
  SEPARATE   the 3 core lots carry on untouched and a sleeve of 1-2 lots of their own buys a SECOND lot on the
             same signal when the gate agrees - the gate never removes a trade, it doubles down on one

Judged with the corrected window engine (sol_wide_stop.simulate): every lot is marked, and anything still open
when a window ends is closed at that window's last price. Selection is walk-forward: the gate is chosen on the
six months before each test window and never with hindsight.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

import run_eth_full_research as research
import stage3_replay as replay
import eth_regime as rg
import sol_pullback as sp
import sol_wide_stop as w
from sol_wide_stop import CORE, SLEEVE, TRAINS, simulate

SCOPES = ["dip", "mode c", "both"]


def daily_closes(raw: pd.DataFrame) -> pd.Series:
    day = raw.open_time.dt.floor("D")
    grouped = raw.groupby(day).agg(close=("close", "last"), n=("close", "size"))
    return grouped[grouped.n == 1440].close


def gates(sol_raw: pd.DataFrame, btc_raw: pd.DataFrame) -> dict[str, np.ndarray]:
    """One boolean per SOL minute per gate, decided from the previous completed day."""
    sol, btc = daily_closes(sol_raw), daily_closes(btc_raw)
    common = sol.index.intersection(btc.index)
    sol, btc = sol.loc[common], btc.loc[common]
    ratio = sol / btc
    frame = pd.DataFrame({
        "btc>30d": btc > btc.rolling(30).mean(),
        "btc>15d": btc > btc.rolling(15).mean(),
        "btc>7d": btc > btc.rolling(7).mean(),
        "btc stacked up": (btc.rolling(7).mean() > btc.rolling(15).mean())
                          & (btc.rolling(15).mean() > btc.rolling(30).mean()),
        "btc not bearish": ~((btc.rolling(7).mean() < btc.rolling(15).mean())
                             & (btc.rolling(15).mean() < btc.rolling(30).mean())),
        "btc up 1d": btc > btc.shift(1),
        "btc up 3d": btc > btc.shift(3),
        "btc up 7d": btc > btc.shift(7),
        "ratio>30d": ratio > ratio.rolling(30).mean(),
        "ratio>15d": ratio > ratio.rolling(15).mean(),
        "ratio>7d": ratio > ratio.rolling(7).mean(),
        "ratio rising": ratio > ratio.shift(1),
    })
    frame = frame[frame.index.isin(common[29:])]                  # only once every average exists
    frame.index = frame.index + pd.Timedelta(days=1)              # effective the next UTC day
    day = sol_raw.open_time.dt.floor("D")
    out = {}
    for name in frame.columns:
        flags = day.map(frame[name]).fillna(False).to_numpy(bool)
        known = day.map(frame[name]).notna().to_numpy(bool)       # before the first full average, nothing is known
        out[name] = flags
        out[f"NOT {name}"] = known & ~flags
    return out


def passes(gate, names, entry):
    return all(gate[name][entry] for name in names)


def subset(trades, gate, names, scope, tag=""):
    """The trades this gate allows. `tag` turns the survivors into sleeve lots instead of replacing the core."""
    out = []
    for trade in trades:
        gated = scope == "both" or (scope == "dip") == (trade["source"] == "dip")
        if gated and not passes(gate, names, trade["entry"]):
            continue
        out.append({**trade, "source": f"{tag}{trade['source']}"} if tag else trade)
    return out


def main() -> None:
    raw, bullish, ema = sp.setup()
    btc = replay.load_raw("BTCUSDT", include_holdout=True)
    btc = btc[btc.open_time < research.T("2026-09-11")].reset_index(drop=True)
    rule, dips, breaks = w.signals(raw)
    core = w.core_trades(rule, dips, breaks, bullish, ema)
    gate = gates(raw, btc)
    pd.set_option("display.width", 260)

    singles = [(name,) for name in gate]
    pairs = [pair for pair in combinations([n for n in gate], 2)
             if pair[1] != f"NOT {pair[0]}" and pair[0] != f"NOT {pair[1]}"]
    keys = [(names, scope) for names in singles + pairs for scope in SCOPES]
    print(f"SOL: {len(dips)} dip signals, {len(breaks)} Mode C signals")
    print(f"{len(gate)} gates ({len(singles)} single, {len(pairs)} pairs) x {len(SCOPES)} scopes = {len(keys)} rules")

    print("\n=== 0. how often each single gate is open, and what SOL's lots did under it (deployed 3 lots)")
    ledger = simulate(core, [(3, CORE)], *research.WINDOWS["full"])["ledger"]
    rows = []
    for name in list(gate)[:24]:
        if name.startswith("NOT "):
            continue
        flags = np.array([gate[name][e] for e in ledger.entry])
        for label, part in ((name, ledger[flags]), (f"NOT {name}", ledger[~flags])):
            rows.append({"gate": label, "trades": len(part),
                         "win%": round(100 * (part.pnl > 0).mean(), 1) if len(part) else 0.0,
                         "total $": round(part.pnl.sum(), 2) if len(part) else 0.0,
                         "avg $": round(part.pnl.mean(), 3) if len(part) else 0.0})
    print(pd.DataFrame(rows).set_index("gate").to_string())

    base = w.score("SOL as deployed, 3 x $100", core, [(3, CORE)])
    print("\n=== 1. SHARED: the deployed lots only buy when the gate agrees")
    print(pd.DataFrame([base]).set_index("setup").to_string())
    shared = {key: subset(core, gate, *key) for key in keys}
    rows = [w.score(f"{' + '.join(names)} [{scope}]", trades, [(3, CORE)])
            for (names, scope), trades in shared.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  gates beating no gate: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame)} on the full window, "
          f"{int((frame['mtm_dd%'] > base['mtm_dd%']).sum())}/{len(frame)} on drawdown")

    print("\n=== 2. SEPARATE: the core carries on, a gated sleeve buys a second lot on the same signal")
    sleeves = {key: sorted(core + subset(core, gate, *key, tag="wide "), key=lambda t: t["entry"]) for key in keys}
    controls = {n: w.score(f"flat core {n} (control)", core, [(n, CORE)]) for n in (4, 5)}
    rows = [w.score(f"{' + '.join(names)} [{scope}] - sleeve 2", trades, [(3, CORE), (2, SLEEVE)])
            for (names, scope), trades in sleeves.items()]
    frame2 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())
    print(frame2.set_index("setup").head(10).to_string())
    print(f"  gated sleeves beating flat core 5: "
          f"{int((frame2.walk_forward > controls[5]['walk_forward']).sum())}/{len(frame2)} on walk-forward, "
          f"{int((frame2['mtm_dd%'] > controls[5]['mtm_dd%']).sum())}/{len(frame2)} on drawdown")

    print("\n=== 3. the honest test: the gate is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, sets, pots, control_pots in (
            ("shared, 3 lots", shared, [(3, CORE)], [(3, CORE)]),
            ("sleeve of 1", sleeves, [(3, CORE), (1, SLEEVE)], [(4, CORE)]),
            ("sleeve of 2", sleeves, [(3, CORE), (2, SLEEVE)], [(5, CORE)])):
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        scores = {key: {x: simulate(trades, pots, *research.WINDOWS[x])["profit"] for x in windows}
                  for key, trades in sets.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(sets, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        name = lambda k: f"{' + '.join(k[0])} [{k[1]}]"
        print(f"\n  --- {label} (control: {'no gate' if label.startswith('shared') else f'flat core {control_pots[0][0]}'})")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed gate in hindsight {name(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")
        print(f"    it picked: {'; '.join(name(p) for p in picks)}")


if __name__ == "__main__":
    main()
