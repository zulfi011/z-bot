"""SOL's wide-stop sleeve, done properly.

The idea, in one line: leave the 3 core lots exactly as deployed, and give SOL extra lots of their own that take
the SAME signals but hold them with a far wider protective stop - so the core takes its quick -2% loss while the
sleeve sits through the shake-out and waits for the recovery.

It is a second lot on the same minute, not a second entry rule, so it doubles the money at risk on a signal and
only differs in how it lets go. That is the honest way to describe it and the honest way to test it.

Every combination:
  stop     -2% (the deployed level) / 3 / 4 / 6 / 8 / 10 / 12 / 15 / 20%, or no stop at all
  arm      the trail arms at +1.251% (deployed) / 1.8 / 2.5 / 3.5 / 5%
  exit     "deployed" - Mode A on the 8-hour line when the lot was opened in a clean uptrend, else the giveback
           "mode a"   - always held against the line
           "mode b"   - always the giveback trail, never the line
  scope    which signals the sleeve takes: the dip only, Mode C only, or both
  size     1, 2 or 3 sleeve lots of their own, on top of the 3 core lots

Judged against the only fair control: the SAME money as more plain core lots. Selection is walk-forward - the
rule is chosen on the six months before each test window and never with hindsight - and the drawdown reported is
hourly MARK TO MARKET on the whole plan, so unrealised pain counts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import eth_regime as rg
import sol_pullback as sp

COIN = "sol"
STOPS = [2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, None]     # None = no protective stop at all
ARMS = [1.251, 1.8, 2.5, 3.5, 5.0]
EXITS = ["deployed", "mode a", "mode b"]
SCOPES = ["dip", "mode c", "both"]
SIZES = [1, 2, 3]
FEE, MIN_ORDER, LOT = 7.5 / 10_000, 5.0, 100.0
CORE, SLEEVE = {"dip", "breakout"}, {"wide dip", "wide breakout"}
TRAINS = [f"wf{i}_train" for i in range(6)]
NO_STOP = 99.0                       # a stop that can never be reached, for the "no stop" case


def signals(raw):
    """The entry minutes of both ways in, exactly as deployed."""
    rule = live.load_rule(COIN)
    dips = [int(entry) for entry in live.live_entries(raw, rule)]
    high, low, open_, close, last_minute = v4.bars_for(raw, sp.MODE_C["chart"])
    entries = v4.entries_for(high, low, close, last_minute, sp.MODE_C["bars"], sp.MODE_C["zone"],
                             sp.MODE_C["confirm"], grid.CLOSE, len(raw))
    blocked = rule["blocked"]
    if blocked:
        hours = grid.TIMES[entries].hour
        entries = entries[~((hours >= blocked[0]) & (hours < blocked[1]))]
    return rule, dips, [int(entry) for entry in entries]


def resolve(entry, arm, giveback, stop, line):
    """opt.trade, but a lot that never resolves is still a lot: it is marked at the last price, not dropped.

    This matters enormously here. A lot with no stop that falls and never comes back simply never exits, and
    treating that as "no trade" would quietly hide every loss the idea produces.
    """
    exit_at, price, why = opt.trade(entry, arm, giveback, stop, line)
    if exit_at < 0:
        return len(grid.CLOSE) - 1, float(grid.CLOSE[-1]), 3          # still open at the end of the data
    return exit_at, price, why


def core_trades(rule, dips, breaks, bullish, ema):
    """SOL as deployed: dip and Mode C, Mode A on the 8-hour line for anything opened in a clean uptrend."""
    out = []
    for entries, source, stop, arm, giveback in (
            (dips, "dip", rule["stop_pct"], rule["activation_pct"], rule["giveback_pct"]),
            (breaks, "breakout", sp.MODE_C["stop"], sp.MODE_C["arm"], sp.MODE_C["giveback"])):
        for entry in entries:
            exit_at, price, why = resolve(entry, arm, giveback, stop, ema if bullish[entry] else None)
            out.append({"entry": entry, "exit": exit_at, "price": price, "source": source, "why": why})
    return sorted(out, key=lambda t: t["entry"])


def sleeve_trades(rule, dips, breaks, bullish, ema, stop, arm, exit_mode, scope):
    """The same signals, held the sleeve's way. Outside the sleeve's scope, nothing is bought."""
    out = []
    for entries, source, giveback in ((dips, "dip", rule["giveback_pct"]),
                                      (breaks, "breakout", sp.MODE_C["giveback"])):
        if scope != "both" and scope != ("dip" if source == "dip" else "mode c"):
            continue
        for entry in entries:
            line = ema if (exit_mode == "mode a" or (exit_mode == "deployed" and bullish[entry])) else None
            exit_at, price, why = resolve(entry, arm, giveback, NO_STOP if stop is None else stop, line)
            out.append({"entry": entry, "exit": exit_at, "price": price, "source": f"wide {source}", "why": why})
    return out


def simulate(trades, pots, start, end):
    """One shared wallet, per-pot slots, the live buying rule, plus hourly mark-to-market equity."""
    initial = sum(n for n, _ in pots) * LOT
    wallet, slots, taken = initial, [[] for _ in pots], []
    # A lot still open when the window ends is closed at the window's last price. Without this a slow lot would
    # reach forward for a recovery that happened after the window, which is exactly the leak a wide stop invites.
    last = int(np.searchsorted(grid.TIMES, end)) - 1
    for trade in trades:
        entry = trade["entry"]
        if not (start <= grid.TIMES[entry] < end):
            continue
        exit_at, exit_price = trade["exit"], trade["price"]
        if exit_at > last:
            exit_at, exit_price = last, float(grid.CLOSE[last])
        for p in range(len(pots)):
            for slot in [s for s in slots[p] if s[0] <= entry]:
                wallet += slot[1]
            slots[p] = [s for s in slots[p] if s[0] > entry]
        if wallet < MIN_ORDER:
            continue
        for p, (lots, sources) in enumerate(pots):
            if trade["source"] in sources and len(slots[p]) < lots:
                spend = min(LOT, np.floor(wallet * 100) / 100)
                fill = grid.OPEN[entry] * (1 + grid.SLIP)
                quantity = spend / (fill * (1 + FEE))
                proceeds = quantity * exit_price * (1 - grid.SLIP) * (1 - FEE)
                wallet -= spend
                slots[p].append((exit_at, proceeds))
                taken.append({"entry": entry, "exit": exit_at, "quantity": quantity, "spend": spend,
                              "proceeds": proceeds, "source": trade["source"], "why": trade["why"]})
                break
    for p in range(len(pots)):
        wallet += sum(s[1] for s in slots[p])

    hours = np.arange(np.searchsorted(grid.TIMES, start), np.searchsorted(grid.TIMES, end), 60)
    equity = np.full(len(hours), initial, dtype=float)
    for lot in taken:
        realised_from = np.searchsorted(hours, lot["exit"])
        equity[realised_from:] += lot["proceeds"] - lot["spend"]
        a = np.searchsorted(hours, lot["entry"])
        if realised_from > a:                       # while it is open, mark it at the hourly close
            equity[a:realised_from] += (lot["quantity"] * grid.CLOSE[hours[a:realised_from]]
                                        * (1 - grid.SLIP) * (1 - FEE) - lot["spend"])
    peak = np.maximum.accumulate(equity) if len(equity) else np.array([initial])
    ledger = pd.DataFrame([{**lot, "pnl": lot["proceeds"] - lot["spend"],
                            "minutes": lot["exit"] - lot["entry"]} for lot in taken])
    return {"profit": wallet - initial, "ledger": ledger, "capital": initial,
            "mtm_dd%": 100 * float((equity / peak - 1).min()) if len(equity) else 0.0}


def score(label, trades, pots):
    runs = {w: simulate(trades, pots, *research.WINDOWS[w]) for w in ("full", "unseen", *rg.TESTS)}
    led, wf = runs["full"]["ledger"], [runs[w]["profit"] for w in rg.TESTS]
    wide = led[led.source.isin(SLEEVE)] if len(led) else led
    return {"setup": label, "money": int(runs["full"]["capital"]), "trades": len(led), "sleeve": len(wide),
            "sleeve_pnl": round(wide.pnl.sum(), 2) if len(wide) else 0.0,
            "win%": round(100 * (led.pnl > 0).mean(), 1) if len(led) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "unseen": round(runs["unseen"]["profit"], 2),
            "mtm_dd%": round(runs["full"]["mtm_dd%"], 2)}


def name_of(key):
    stop, arm, exit_mode, scope = key
    return f"stop {'none' if stop is None else f'-{stop:g}%'}, arm +{arm:g}%, {exit_mode}, {scope}"


def main() -> None:
    raw, bullish, ema = sp.setup()
    rule, dips, breaks = signals(raw)
    core = core_trades(rule, dips, breaks, bullish, ema)
    pd.set_option("display.width", 260)
    keys = [(s, a, e, sc) for s in STOPS for a in ARMS for e in EXITS for sc in SCOPES]
    sets = {key: sorted(core + sleeve_trades(rule, dips, breaks, bullish, ema, *key), key=lambda t: t["entry"])
            for key in keys}
    print(f"SOL: {len(dips)} dip signals, {len(breaks)} Mode C signals, {len(sets)} sleeve rules x {len(SIZES)} sizes")

    print("\n=== 0. the control: SOL as deployed, and the same money simply spread over more core lots")
    controls = {n: score(f"flat core {n} (control)", core, [(n, CORE)]) for n in (3, 4, 5, 6)}
    print(pd.DataFrame(controls.values()).set_index("setup").to_string())

    print("\n=== 1. what a wide stop actually does to the same signals (sleeve lots only, -12% / +1.251% / deployed)")
    demo = simulate(sets[(12.0, 1.251, "deployed", "both")], [(3, CORE), (2, SLEEVE)], *research.WINDOWS["full"])
    led = demo["ledger"]
    rows = []
    for label, part in (("core lots (-2% / -4%)", led[led.source.isin(CORE)]),
                        ("sleeve lots (-12%)", led[led.source.isin(SLEEVE)])):
        stopped = part[part.why == 2]
        rows.append({"lots": label, "trades": len(part), "win%": round(100 * (part.pnl > 0).mean(), 1),
                     "stopped out": len(stopped), "stop loss avg $": round(stopped.pnl.mean(), 2) if len(stopped) else 0.0,
                     "avg win $": round(part[part.pnl > 0].pnl.mean(), 2),
                     "avg loss $": round(part[part.pnl <= 0].pnl.mean(), 2),
                     "median hold h": round(part.minutes.median() / 60, 1), "total $": round(part.pnl.sum(), 2)})
    print(pd.DataFrame(rows).set_index("lots").to_string())

    for size in SIZES:
        pots = [(3, CORE), (size, SLEEVE)]
        rows = [score(name_of(key), trades, pots) for key, trades in sets.items()]
        frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
        control = controls[3 + size]
        print(f"\n=== 2.{size} sleeve of {size} (${(3 + size) * 100}) - best 8 by walk-forward, against "
              f"flat core {3 + size} (+${control['walk_forward']:.2f}, {control['windows']}, "
              f"{control['mtm_dd%']}% drawdown)")
        print(frame.set_index("setup").head(8).to_string())
        better = frame[frame.walk_forward > control["walk_forward"]]
        print(f"  rules beating that control: {len(better)}/{len(frame)} on walk-forward, "
              f"{int((frame.profit > control['profit']).sum())}/{len(frame)} on the full window, "
              f"{int((frame['mtm_dd%'] > control['mtm_dd%']).sum())}/{len(frame)} on drawdown")

    print("\n=== 3. is it a plateau or a spike? walk-forward by stop and arm (sleeve of 2, deployed exit, dip)")
    table = pd.DataFrame({f"+{a:g}%": {('none' if s is None else f"-{s:g}%"):
                                       score("x", sets[(s, a, "deployed", "dip")], [(3, CORE), (2, SLEEVE)])["walk_forward"]
                                       for s in STOPS} for a in ARMS})
    print(table.to_string())

    print("\n=== 4. the honest test: the rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    for size in SIZES:
        pots, control_pots = [(3, CORE), (size, SLEEVE)], [(3 + size, CORE)]
        control_w = {w: simulate(core, control_pots, *research.WINDOWS[w])["profit"] for w in windows}
        scores = {key: {w: simulate(trades, pots, *research.WINDOWS[w])["profit"] for w in windows}
                  for key, trades in sets.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(sets, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- sleeve of {size}, ${(3 + size) * 100}, against flat core {3 + size}")
        detail = [{"window": research.TESTS[i][0], "chosen on the 6 months before": name_of(picks[i]),
                   "sleeve": round(scores[picks[i]][rg.TESTS[i]], 2),
                   "control": round(control_w[rg.TESTS[i]], 2),
                   "difference": round(scores[picks[i]][rg.TESTS[i]] - control_w[rg.TESTS[i]], 2)} for i in range(6)]
        print(pd.DataFrame(detail).to_string(index=False))
        print(f"    honest total ${honest:8.2f} ({wins}/6 beat simply owning another plain lot)")
        print(f"    best fixed rule in hindsight: {name_of(best)} "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")

    print("\n=== 5. the steadiest candidates, in full")
    steady = [(12.0, 1.251, "deployed", "both"), (12.0, 1.251, "deployed", "dip"),
              (10.0, 1.251, "deployed", "both"), (8.0, 1.251, "deployed", "both"),
              (None, 1.251, "deployed", "both"), (12.0, 3.5, "deployed", "both")]
    rows = [controls[5]]
    rows += [score(name_of(key) + " - sleeve 2", sets[key], [(3, CORE), (2, SLEEVE)]) for key in steady]
    print(pd.DataFrame(rows).set_index("setup").to_string())


if __name__ == "__main__":
    main()
