"""ETH only: does the Crypto Fear & Greed Index make buys more reliable?

Money rule (as compounding_eth_only.py): $300 start, 3 x $100 lots, a 4th lot at $400, a 5th at $500, then +$20 per
lot for each further $100 of marked high-water. Every deployed ETH entry (dip, Mode C, pullback) and exit unchanged;
a rule can only SKIP a buy. The index value stamped day D (published 00:00 UTC) is used from D 00:05 onward, so a buy
never sees a value from its own future. A skipped signal frees the lot for the next one.

Tests: win rate by index level, full history, halves, choose-on-6-months/test-next-quarter walk-forward (six
quarters, fresh $300 each), every monthly start (12- and 6-month runs), 10+10 bps costs.
"""

from __future__ import annotations

import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca  # noqa: E402
from compounding_full_analysis import Policy, T, replay  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# The coin under test: ETH by default; FG_COIN=SOL (etc.) runs the identical test on another coin. An environment
# variable rather than an argument, so the worker processes see it too.
COIN = os.environ.get("FG_COIN", "ETH").upper()
OUT = ROOT / "results" / ("eth_fear_greed_v1" if COIN == "ETH" else f"{COIN.lower()}_fear_greed_v1")
PLAN = Policy("ETH 3->5 then +$20", "plan", 300.0, 5, 1.0)
TESTS = [("2025-04-01", "2025-07-01"), ("2025-07-01", "2025-10-01"), ("2025-10-01", "2026-01-01"),
         ("2026-01-01", "2026-04-01"), ("2026-04-01", "2026-07-01"), ("2026-07-01", "2026-09-10")]
M = C = FNG = None


def load_fng():
    d = pd.read_csv(ROOT / "data" / "fear_greed" / "fng_daily.csv", parse_dates=["date"])
    d = d.set_index("date").value.asfreq("D").ffill()
    frame = pd.DataFrame({"value": d, "chg3": d - d.shift(3), "chg7": d - d.shift(7)})
    frame.index = frame.index + pd.Timedelta(minutes=5)          # usable from 00:05 UTC of its own day
    return frame


def init():
    global M, C, FNG
    M, cands = ca.load()
    FNG = load_fng()
    C = [c for c in cands if c.coin == COIN]


def features(cands):
    times = pd.DatetimeIndex([c.entry_time for c in cands])
    idx = FNG.index.searchsorted(times, side="right") - 1
    return FNG.iloc[idx].reset_index(drop=True)


def rules():
    out = [("none", None)]
    out += [(f"skip if F&G < {x}", ("min", x)) for x in range(10, 65, 5)]
    out += [(f"skip if F&G > {y}", ("max", y)) for y in range(40, 95, 5)]
    out += [(f"buy only {lo}-{hi}", ("band", lo, hi)) for lo in (10, 20, 25, 30) for hi in (60, 70, 75, 80)]
    out += [(f"skip if 7d drop >= {k}", ("drop7", k)) for k in range(5, 35, 5)]
    out += [(f"skip if 7d rise >= {k}", ("rise7", k)) for k in range(5, 35, 5)]
    out += [(f"skip if 3d drop >= {k}", ("drop3", k)) for k in range(5, 30, 5)]
    return out


def keep_mask(rule, f):
    if rule is None:
        return np.ones(len(f), bool)
    kind, *a = rule
    v = f.value.to_numpy()
    if kind == "min":
        return v >= a[0]
    if kind == "max":
        return v <= a[0]
    if kind == "band":
        return (v >= a[0]) & (v <= a[1])
    if kind == "drop7":
        return ~(f.chg7.to_numpy() <= -a[0])
    if kind == "rise7":
        return ~(f.chg7.to_numpy() >= a[0])
    if kind == "drop3":
        return ~(f.chg3.to_numpy() <= -a[0])
    raise ValueError(kind)


def job(args):
    name, rule, tag, start, end, fee, slip = args
    f = features(C)
    kept = [c for c, k in zip(C, keep_mask(rule, f)) if k]
    s = replay(M, kept, PLAN, start, end, fee=fee, slip=slip)
    return {"rule": name, "tag": tag, "start": start.date(), "profit": s["profit"], "dd_usd": s["dd_usd"],
            "dd_pct": s["dd_pct"], "trades": s["trades"], "win_pct": s["win_pct"]}


def diagnostics():
    init()
    s, led, _ = replay(M, C, PLAN, want_frames=True)
    led = led.copy()
    f = load_fng()
    idx = f.index.searchsorted(pd.DatetimeIndex(led.entry_time), side="right") - 1
    led["fng"] = f.value.iloc[idx].to_numpy()
    led["chg7"] = f.chg7.iloc[idx].to_numpy()
    led["win"] = led.pnl > 0
    led["ret"] = 100 * led.pnl / led.spend
    bands = pd.cut(led.fng, [0, 24, 44, 55, 75, 100],
                   labels=["extreme fear 0-24", "fear 25-44", "neutral 45-55", "greed 56-75", "extreme greed 76+"])
    rows = []
    for label, g in led.groupby(bands, observed=True):
        w, l = g[g.win], g[~g.win]
        rows.append({"F&G": label, "trades": len(g), "win%": 100 * g.win.mean(), "avg_win%": w.ret.mean(),
                     "avg_loss%": l.ret.mean(), "profit": g.pnl.sum(), "per_trade": g.pnl.mean()})
    by_band = pd.DataFrame(rows)
    chg = pd.cut(led.chg7, [-100, -20, -10, 0, 10, 20, 100])
    by_chg = led.groupby(chg, observed=True).agg(trades=("win", "size"), win_pct=("win", lambda x: 100 * x.mean()),
                                                 profit=("pnl", "sum")).reset_index()
    return s, by_band, by_chg, led


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 200)
    s, by_band, by_chg, led = diagnostics()
    led.to_csv(OUT / "control_trades_with_fng.csv", index=False)
    print(f"=== control: {COIN} plan, no filter: profit ${s['profit']:.2f}, {s['trades']} trades, win {s['win_pct']:.1f}%, "
          f"DD {s['dd_pct']:.2f}%")
    print(f"\n=== {COIN} trades by Fear & Greed level at the buy")
    print(by_band.round(2).to_string(index=False))
    print("\n=== by 7-day change in the index")
    print(by_chg.round(2).to_string(index=False))

    rs = rules()
    tasks = []
    for name, rule in rs:
        tasks.append((name, rule, "full", ca.START, ca.END, 7.5, 2.0))
        tasks.append((name, rule, "stress", ca.START, ca.END, 10.0, 10.0))
        tasks.append((name, rule, "earlier", T("2024-10-01"), T("2025-09-01"), 7.5, 2.0))
        tasks.append((name, rule, "later", T("2025-09-01"), ca.END, 7.5, 2.0))
        for a, b in TESTS:
            tasks.append((name, rule, "wf_test", T(a), T(b), 7.5, 2.0))
            tasks.append((name, rule, "wf_train", T(a) - pd.DateOffset(months=6), T(a), 7.5, 2.0))
        for st in pd.date_range(ca.START, T("2025-09-01"), freq="MS"):
            tasks.append((name, rule, "r12", st, min(st + pd.DateOffset(months=12), ca.END), 7.5, 2.0))
        for st in pd.date_range(ca.START, T("2026-03-01"), freq="MS"):
            tasks.append((name, rule, "r6", st, st + pd.DateOffset(months=6), 7.5, 2.0))
    with Pool(8, initializer=init) as pool:
        df = pd.DataFrame(pool.map(job, tasks, chunksize=16))
    df.to_csv(OUT / "all_runs.csv", index=False)

    full = df[df.tag == "full"].set_index("rule")
    t = full[["profit", "dd_usd", "dd_pct", "trades", "win_pct"]].copy()
    t["stress"] = df[df.tag == "stress"].set_index("rule").profit
    for h in ("earlier", "later"):
        t[h] = df[df.tag == h].set_index("rule").profit
    for tag in ("r12", "r6"):
        piv = df[df.tag == tag].pivot(index="start", columns="rule", values="profit")
        diff = piv.sub(piv["none"], axis=0)
        t[f"{tag}_beats"] = (diff > 1e-9).sum()
        t[f"{tag}_median_vs_none"] = diff.median()
    t["vs_none"] = t.profit - t.loc["none", "profit"]
    t = t.sort_values("profit", ascending=False)
    print("\n=== every rule, full history (Oct 2024 - Sep 10 2026), best first")
    print(t.round(2).to_string())

    # honest walk-forward: choose the best rule on the 6 months before each quarter, use it in that quarter
    rows = []
    for a, b in TESTS:
        tr = df[(df.tag == "wf_train") & (df.start == (T(a) - pd.DateOffset(months=6)).date())].set_index("rule")
        te = df[(df.tag == "wf_test") & (df.start == T(a).date())].set_index("rule")
        chosen = tr.profit.idxmax()
        rows.append({"quarter": a, "chosen": chosen, "chosen_profit": te.loc[chosen, "profit"],
                     "none_profit": te.loc["none", "profit"], "change": te.loc[chosen, "profit"] - te.loc["none", "profit"],
                     "best_in_hindsight": te.profit.idxmax()})
    wf = pd.DataFrame(rows)
    print("\n=== walk-forward: rule chosen on the previous 6 months, used blind in the next quarter")
    print(wf.round(2).to_string(index=False))
    print(f"total: chosen ${wf.chosen_profit.sum():.2f} vs no filter ${wf.none_profit.sum():.2f} "
          f"= {wf.change.sum():+.2f}, better in {(wf.change > 1e-9).sum()}/6, worse in {(wf.change < -1e-9).sum()}/6")

    halves = []
    for pick, test in (("earlier", "later"), ("later", "earlier")):
        chosen = t[pick].idxmax()
        halves.append({"choose_on": pick, "chosen": chosen, "test_profit": t.loc[chosen, test],
                       "none_test": t.loc["none", test], "change": t.loc[chosen, test] - t.loc["none", test]})
    print("\n=== choose on one year, test on the other")
    print(pd.DataFrame(halves).round(2).to_string(index=False))
    t.to_csv(OUT / "summary.csv")
    wf.to_csv(OUT / "walk_forward.csv", index=False)
    by_band.to_csv(OUT / "by_fng_level.csv", index=False)


if __name__ == "__main__":
    main()
