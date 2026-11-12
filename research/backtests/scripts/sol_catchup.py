"""SOL catch-up to BTC: buy SOL when BTC is climbing but SOL has fallen behind it.

The BTC-relative gate failed on SOL because it bought late ([[sol-btc-gates-rejected]]). This flips that finding
into an entry of its own: BTC is healthy, SOL has lagged it, so buy SOL and wait for the gap to close.

  lag        the hourly SOL/BTC ratio sits at least X% below its own N-day average
  btc        what BTC has to be doing: averages stacked 7d > 15d > 30d, above its own 30-day average,
             up over the last 3 days, or nothing at all (pure SOL lag, as a control)
  health     optionally require SOL's own averages NOT stacked downward - lagging, not collapsing
  buy        the first hour all of it holds, at the next minute's open; one buy per episode
  exit       "dip"     SOL's deployed dip exit (stop -2%, trail +1.251% / 12%, Mode A in a clean uptrend)
             "mode a"  always held against the 8-hour line
             "mode b"  always the giveback trail
             "revert"  sell once the ratio is back at its own average - the catch-up is complete - stop -2%
  lots       SHARED with SOL's 3 deployed lots, or 1-3 lots of its own on top

No blocked hours: those were fitted to the dip entry and a new rule should not inherit another rule's fit.
Corrected window engine, hourly mark-to-market drawdown, walk-forward selection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import stage3_replay as replay
import eth_regime as rg
import sol_pullback as sp
import sol_wide_stop as w
from sol_wide_stop import CORE, TRAINS, simulate

CATCH = {"catchup"}
DAYS = [3, 7, 14, 30]
LAGS = [1.0, 2.0, 3.0, 5.0, 8.0]
BTCS = ["stacked up", "above 30d", "up 3 days", "anything"]
HEALTH = ["not collapsing", "any"]
EXITS = ["dip", "mode a", "mode b", "revert"]
SIZES = [1, 2, 3]


def daily_flags(raw: pd.DataFrame) -> pd.DataFrame:
    """Per-day flags from completed days only, effective the next UTC day."""
    day = raw.open_time.dt.floor("D")
    grouped = raw.groupby(day).agg(close=("close", "last"), n=("close", "size"))
    close = grouped[grouped.n == 1440].close
    a7, a15, a30 = (close.rolling(n).mean() for n in (7, 15, 30))
    frame = pd.DataFrame({"stacked up": (a7 > a15) & (a15 > a30), "above 30d": close > a30,
                          "up 3 days": close > close.shift(3),
                          "bearish": (a7 < a15) & (a15 < a30)})[a30.notna()]
    frame.index = frame.index + pd.Timedelta(days=1)
    return frame


class Signals:
    """The hourly SOL/BTC picture, and where each hour's decision can first be acted on."""

    def __init__(self, raw, btc):
        sol_h = raw.set_index("open_time").close.resample("1h").last()
        btc_h = btc.set_index("open_time").close.resample("1h").last()
        frame = pd.concat({"sol": sol_h, "btc": btc_h}, axis=1).dropna()
        frame["ratio"] = frame.sol / frame.btc
        days = frame.index.floor("D")
        btc_daily, sol_daily = daily_flags(btc), daily_flags(raw)
        for name in BTCS[:-1]:
            frame[name] = days.map(btc_daily[name]).fillna(False).astype(bool).to_numpy()
        frame["anything"] = True
        frame["collapsing"] = days.map(sol_daily["bearish"]).fillna(True).astype(bool).to_numpy()
        self.frame = frame
        self.act = np.searchsorted(w.grid.TIMES, frame.index + pd.Timedelta(hours=1))
        self._dev = {}

    def deviation(self, days):
        if days not in self._dev:
            mean = self.frame.ratio.rolling(days * 24).mean().shift(1)
            self._dev[days] = (self.frame.ratio / mean - 1).to_numpy()
        return self._dev[days]

    def entries(self, days, lag, btc, health):
        on = (self.deviation(days) <= -lag / 100) & self.frame[btc].to_numpy()
        if health == "not collapsing":
            on = on & ~self.frame.collapsing.to_numpy()
        first = on & ~np.r_[False, on[:-1]]
        where = np.flatnonzero(first)
        return where[self.act[where] < len(w.grid.OPEN) - 1]


def build(sig, rule, bullish, ema, days, lag, btc, health, exit_style):
    dev = sig.deviation(days)
    trades = []
    for hour in sig.entries(days, lag, btc, health):
        entry = int(sig.act[hour])
        if exit_style != "revert":
            line = ema if (exit_style == "mode a" or (exit_style == "dip" and bullish[entry])) else None
            out, price, why = w.resolve(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"], line)
        else:
            back = np.flatnonzero(dev[hour + 1:] >= 0)
            out = int(sig.act[hour + 1 + back[0]]) if len(back) else len(w.grid.OPEN) - 1
            out = min(out, len(w.grid.OPEN) - 1)
            price, why = float(w.grid.OPEN[out]), 6
            level = w.grid.OPEN[entry] * (1 + w.grid.SLIP) * (1 - rule["stop_pct"] / 100)
            hit = np.flatnonzero(w.grid.LOW[entry:out] <= level)
            if len(hit):
                out, why = entry + int(hit[0]), 2
                price = min(level, float(w.grid.OPEN[out]))
        trades.append({"entry": entry, "exit": int(out), "price": price, "source": "catchup", "why": why})
    return trades


def name_of(key):
    days, lag, btc, health, exit_style = key
    return f"lag {lag:g}% vs {days}d ratio, btc {btc}, sol {health}, exit {exit_style}"


def main() -> None:
    raw, bullish, ema = sp.setup()
    btc = replay.load_raw("BTCUSDT", include_holdout=True)
    btc = btc[btc.open_time < research.T("2026-09-11")].reset_index(drop=True)
    rule, dips, breaks = w.signals(raw)
    core = w.core_trades(rule, dips, breaks, bullish, ema)
    sig = Signals(raw, btc)
    pd.set_option("display.width", 275)

    base = w.score("SOL as deployed, 3 x $100", core, [(3, CORE)])
    controls = {n: w.score(f"flat core {n} (control)", core, [(n, CORE)]) for n in (4, 5, 6)}
    print("=== the controls")
    print(pd.DataFrame([base, *controls.values()]).set_index("setup").to_string())

    keys = [(d, l, b, h, e) for d in DAYS for l in LAGS for b in BTCS for h in HEALTH for e in EXITS]
    sets = {key: build(sig, rule, bullish, ema, *key) for key in keys}
    counts = pd.Series({name_of(k): len(v) for k, v in sets.items()})
    print(f"\n{len(sets)} catch-up rules; signals per rule: median {counts.median():.0f}, "
          f"range {counts.min()}-{counts.max()}")

    print("\n=== 1. catch-up ALONE, on its own money (best 10 by walk-forward, 2 x $100)")
    rows = [w.score(name_of(key), trades, [(2, CATCH)]) for key, trades in sets.items() if trades]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(10).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())

    print("\n=== 2. SHARED: catch-up competes for SOL's 3 deployed lots")
    rows = [base] + [w.score(name_of(key), sorted(core + trades, key=lambda t: t["entry"]), [(3, CORE | CATCH)])
                     for key, trades in sets.items() if trades]
    frame2 = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame2.set_index("setup").head(8).to_string())
    print(f"  beating no catch-up: {int((frame2.walk_forward > base['walk_forward']).sum())}/{len(frame2) - 1} on "
          f"walk-forward, {int((frame2.profit > base['profit']).sum())}/{len(frame2) - 1} on the full window")

    print("\n=== 3. SEPARATE: the core carries on, catch-up holds lots of its own")
    for size in SIZES:
        control = controls[3 + size]
        rows = [w.score(name_of(key), sorted(core + trades, key=lambda t: t["entry"]), [(3, CORE), (size, CATCH)])
                for key, trades in sets.items() if trades]
        part = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
        print(f"\n  --- own {size} (${(3 + size) * 100}) against flat core {3 + size} "
              f"(+${control['walk_forward']:.2f}, {control['windows']}, {control['mtm_dd%']}%)")
        print(part.set_index("setup").head(5).to_string())
        print(f"    beating that control: {int((part.walk_forward > control['walk_forward']).sum())}/{len(part)} "
              f"on walk-forward, {int((part['mtm_dd%'] > control['mtm_dd%']).sum())}/{len(part)} on drawdown")

    print("\n=== 4. the honest test: the catch-up rule is chosen on the six months before each window")
    windows = (*TRAINS, *rg.TESTS)
    usable = {k: v for k, v in sets.items() if v}
    for label, pots, control_pots in (("shared, 3 lots", [(3, CORE | CATCH)], [(3, CORE)]),
                                      ("own 1", [(3, CORE), (1, CATCH)], [(4, CORE)]),
                                      ("own 2", [(3, CORE), (2, CATCH)], [(5, CORE)]),
                                      ("own 3", [(3, CORE), (3, CATCH)], [(6, CORE)])):
        control_w = {x: simulate(core, control_pots, *research.WINDOWS[x])["profit"] for x in windows}
        scores = {key: {x: simulate(sorted(core + trades, key=lambda t: t["entry"]), pots,
                                    *research.WINDOWS[x])["profit"] for x in windows}
                  for key, trades in usable.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]] - control_w[TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] - control_w[t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > control_w[t] for p, t in zip(picks, rg.TESTS))
        best = max(usable, key=lambda k: sum(scores[k][t] - control_w[t] for t in rg.TESTS))
        print(f"\n  --- {label}")
        print(f"    honest ${honest:8.2f} ({wins}/6 beat the control)")
        print(f"    best fixed rule in hindsight {name_of(best)}: "
              f"${sum(scores[best][t] - control_w[t] for t in rg.TESTS):8.2f}, window by window "
              f"{', '.join(f'{scores[best][t] - control_w[t]:+.2f}' for t in rg.TESTS)}")
        print(f"    it picked: {'; '.join(name_of(p) for p in picks)}")


if __name__ == "__main__":
    main()
