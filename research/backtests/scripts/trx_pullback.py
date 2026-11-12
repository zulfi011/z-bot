"""Does the pullback entry help TRX, and on what settings?

The third way in that was built for ETH, tuned from scratch for TRX (never transplant another coin's numbers):
in an uptrend, 1-minute closes below an N-hour EMA for at least `dwell` minutes, then the first close back above
it buys at the next minute.

TRX is the odd coin out: it has NO trend exit. Mode A was tested for its core and rejected - every EMA length
made TRX worse - so a pullback lot has to be told how to leave. Every combination:

  line      the pullback EMA: 4 / 8 / 12 / 24 / 36 / 48 hours
  dwell     minutes below it before a reclaim counts: 15 / 60 / 180 / 360
  uptrend   require 7d > 15d > 30d at the signal (as ETH does), or take any reclaim
  exit      "dip"      TRX's deployed dip exit: stop -4%, trail arms +1.245%, gives back 10%
            "mode c"   TRX's Mode C exit: stop -3%, arms +1.283%, gives back 22%
            "wide"     the dip trail with a -6% stop, in case a pullback lot needs more room
            "line 8h"  held against an 8-hour EMA once the trail arms (Mode A), stop -4%
            "line 16h" the same on a 16-hour EMA
            "line 24h" the same on a 24-hour EMA
  lots      SHARED with TRX's 3 deployed lots, or 1-3 lots of its own on top

TRX has no blocked hours, so none are applied. Corrected window engine (every lot marked, anything still open at
a window's end closed at that window's last price), hourly mark-to-market drawdown, walk-forward selection
against the only fair control: the same money in more plain core lots.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_pullback as pb
import eth_regime as rg
import sol_wide_stop as w
from sol_wide_stop import TRAINS, simulate

COIN, SYMBOL = "trx", "TRXUSDT"
MODE_C = dict(chart=60, bars=40, zone=2.0, confirm=3, stop=3.0, arm=1.283, giveback=22.0)
CORE, PULL = {"dip", "breakout"}, {"pullback"}
HOURS = [4, 8, 12, 24, 36, 48]
DWELL = [15, 60, 180, 360]
UPTREND = [True, False]
EXITS = ["dip", "mode c", "wide", "line 8h", "line 16h", "line 24h"]
SIZES = [1, 2, 3]


def setup():
    raw = replay.load_raw(SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    return raw, live.regime_flags(raw)


def core_trades(raw, rule):
    """TRX as deployed: the dip and Mode C, both on the giveback trail (Mode B) - TRX has no trend exit."""
    trades = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"], None)
        trades.append({"entry": entry, "exit": exit_at, "price": price, "source": "dip", "why": why})
    high, low, open_, close, last_minute = v4.bars_for(raw, MODE_C["chart"])
    entries = v4.entries_for(high, low, close, last_minute, MODE_C["bars"], MODE_C["zone"], MODE_C["confirm"],
                             grid.CLOSE, len(raw))
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, MODE_C["arm"], MODE_C["giveback"], MODE_C["stop"], None)
        trades.append({"entry": entry, "exit": exit_at, "price": price, "source": "breakout", "why": why})
    return sorted(trades, key=lambda t: t["entry"])


def pullback_trades(entries, rule, exit_style, lines):
    arm, giveback, stop = {
        "dip": (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]),
        "mode c": (MODE_C["arm"], MODE_C["giveback"], MODE_C["stop"]),
        "wide": (rule["activation_pct"], rule["giveback_pct"], 6.0),
    }.get(exit_style, (rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"]))
    line = lines.get(exit_style)
    out = []
    for entry in entries:
        entry = int(entry)
        exit_at, price, why = w.resolve(entry, arm, giveback, stop, line)
        out.append({"entry": entry, "exit": exit_at, "price": price, "source": "pullback", "why": why})
    return out


def score(label, trades, pots):
    runs = {x: simulate(trades, pots, *research.WINDOWS[x]) for x in ("full", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[x]["profit"] for x in rg.TESTS]
    pulls = led[led.source.isin(PULL)] if len(led) else led
    return {"setup": label, "money": int(runs["full"]["capital"]), "trades": len(led), "pull": len(pulls),
            "pull_pnl": round(pulls.pnl.sum(), 2) if len(pulls) else 0.0,
            "win%": round(100 * (led.pnl > 0).mean(), 1) if len(led) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "unseen": round(runs["unseen"]["profit"], 2),
            "mtm_dd%": round(runs["full"]["mtm_dd%"], 2)}


def name_of(key):
    hours, dwell, uptrend, exit_style = key
    return f"{hours}h line, {dwell}m below{'' if uptrend else ', any market'}, exit {exit_style}"


def main() -> None:
    raw, bullish = setup()
    rule = live.load_rule(COIN)
    core = core_trades(raw, rule)
    lines = {f"line {h}h": pd.Series(grid.CLOSE).ewm(span=h * 60, adjust=False).mean().to_numpy()
             for h in (8, 16, 24)}
    pd.set_option("display.width", 270)

    base = score("TRX as deployed, 3 x $100", core, [(3, CORE)])
    controls = {n: score(f"flat core {n} (control)", core, [(n, CORE)]) for n in (4, 5, 6)}
    print("=== the controls")
    print(pd.DataFrame([base, *controls.values()]).set_index("setup").to_string())

    everywhere = np.ones(len(grid.CLOSE), bool)
    entries = {}
    for hours in HOURS:
        for dwell in DWELL:
            for uptrend in UPTREND:
                flags = bullish if uptrend else everywhere
                entries[(hours, dwell, uptrend)] = pb.pullback_entries(grid.CLOSE, flags, hours, dwell,
                                                                       grid.TIMES, blocked=None)
    counts = pd.Series({k: len(v) for k, v in entries.items()})
    print(f"\n{len(entries)} entry settings x {len(EXITS)} exits = {len(entries) * len(EXITS)} rules; "
          f"candidate reclaims: median {counts.median():.0f}, range {counts.min()}-{counts.max()}")

    sets = {(*k, e): pullback_trades(v, rule, e, lines) for k, v in entries.items() for e in EXITS}
    sets = {k: v for k, v in sets.items() if v}

    print("\n=== 1. SHARED: the pullback competes for TRX's 3 deployed lots (best 10 by walk-forward)")
    rows = [base] + [score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE | PULL)])
                     for k, v in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  beating no pullback: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame) - 1} on "
          f"walk-forward, {int((frame.profit > base['profit']).sum())}/{len(frame) - 1} on the full window")

    print("\n=== 2. the pullback ALONE, on its own money (2 x $100) - best 5")
    alone = pd.DataFrame([score(name_of(k), v, [(2, PULL)]) for k, v in sets.items()])
    print(alone.sort_values("walk_forward", ascending=False).set_index("setup").head(5).to_string())
    print(f"  pullback rules that made money alone: {int((alone.profit > 0).sum())}/{len(alone)}")

    print("\n=== 3. SEPARATE: the core carries on, the pullback holds lots of its own")
    for size in SIZES:
        control = controls[3 + size]
        rows = [score(name_of(k), sorted(core + v, key=lambda t: t["entry"]), [(3, CORE), (size, PULL)])
                for k, v in sets.items()]
        part = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against flat core {3 + size} "
              f"(+${control['walk_forward']:.2f}, {control['windows']}, {control['mtm_dd%']}%)")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating that control: {int((part.walk_forward > control['walk_forward']).sum())}/{len(part)} "
              f"on walk-forward, {int((part['mtm_dd%'] > control['mtm_dd%']).sum())}/{len(part)} on drawdown")

    print("\n=== 4. the honest test: the pullback rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for label, pots, control_pots in (("shared, 3 lots", [(3, CORE | PULL)], [(3, CORE)]),
                                      ("own 1", [(3, CORE), (1, PULL)], [(4, CORE)]),
                                      ("own 2", [(3, CORE), (2, PULL)], [(5, CORE)]),
                                      ("own 3", [(3, CORE), (3, PULL)], [(6, CORE)])):
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        scores = {k: {x: simulate(sorted(core + v, key=lambda t: t["entry"]), pots,
                                  *research.WINDOWS[x])["profit"] for x in windows} for k, v in sets.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(sets, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed rule in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")
        print(f"    it picked: {'; '.join(name_of(p) for p in picks)}")


if __name__ == "__main__":
    main()
