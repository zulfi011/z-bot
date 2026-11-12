"""ETH only: does market breadth across 40 large coins pick out losing buys?

Breadth is built from Binance spot daily candles of 40 coins that were large caps in mid-2024 (fixed list, chosen
before the test window so later winners are not hand-picked; data/breadth/raw). A day's figures use completed
daily closes only and become usable at 00:05 UTC the next day.

Measures: % of coins above their 30/15/7-day average, % with a positive 7-day return, the median 7-day return,
and the 7-day change of the 30-day breadth. Same money rule and tests as eth_fear_greed.py: $300, 3 x $100 ->
5 x $100 -> +$20 per lot per $100; deployed ETH entries and exits unchanged; a rule can only skip a buy.
"""

from __future__ import annotations

import io
import os
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca  # noqa: E402
from compounding_full_analysis import T, replay  # noqa: E402
from eth_fear_greed import PLAN, TESTS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "breadth" / "raw"
# ETH by default; FG_COIN=SOL (etc.) runs the identical test on another coin.
COIN = os.environ.get("FG_COIN", "ETH").upper()
OUT = ROOT / "results" / f"{COIN.lower()}_breadth_v1"
M = C = FEAT = None


def daily_closes() -> pd.DataFrame:
    frames = {}
    for path in sorted(RAW.glob("*.zip")):
        symbol = path.name.split("-")[0]
        with zipfile.ZipFile(path) as archive:
            raw = archive.read(archive.namelist()[0]).decode()
        d = pd.read_csv(io.StringIO(raw), header=None, usecols=[0, 4])
        if not str(d.iloc[0, 0]).isdigit():                     # some archives carry a header row
            d = d.iloc[1:]
        t = d[0].astype("int64")
        t = np.where(t > 10**14, t // 1000, t)                  # 2025+ files are in microseconds
        frames.setdefault(symbol, []).append(pd.Series(d[4].astype(float).to_numpy(),
                                                       index=pd.to_datetime(t, unit="ms", utc=True)))
    closes = pd.DataFrame({s: pd.concat(v).sort_index() for s, v in frames.items()})
    return closes[~closes.index.duplicated()].asfreq("D")


def build_features() -> pd.DataFrame:
    c = daily_closes()
    out = pd.DataFrame(index=c.index)
    for n in (7, 15, 30):
        avg = c.rolling(n, min_periods=n).mean()
        valid = avg.notna() & c.notna()
        out[f"above{n}"] = 100 * ((c > avg) & valid).sum(axis=1) / valid.sum(axis=1)
    ret7 = c.pct_change(7, fill_method=None) * 100
    out["pos7"] = 100 * (ret7 > 0).sum(axis=1) / ret7.notna().sum(axis=1)
    out["med7"] = ret7.median(axis=1)
    out["above30_chg7"] = out.above30 - out.above30.shift(7)
    out["coins"] = c.notna().sum(axis=1)
    # A daily candle opening at D closes at D+1 00:00; its figures are usable from D+1 00:05.
    out.index = out.index + pd.Timedelta(days=1, minutes=5)
    return out


def attach(times, feats):
    idx = feats.index.searchsorted(pd.DatetimeIndex(times), side="right") - 1
    return feats.iloc[idx].reset_index(drop=True)


def init():
    global M, C, FEAT
    M, cands = ca.load()
    C = [c for c in cands if c.coin == COIN]
    FEAT = attach([c.entry_time for c in C], build_features())


def rules():
    out = [("none", None)]
    for col, label in (("above30", "30d"), ("above15", "15d"), ("above7", "7d"), ("pos7", "7d-up")):
        out += [(f"skip if breadth {label} < {x}%", (col, "<", x)) for x in range(10, 65, 5)]
        out += [(f"skip if breadth {label} > {y}%", (col, ">", y)) for y in range(60, 100, 5)]
    out += [(f"skip if median 7d return < {z}%", ("med7", "<", z)) for z in (-15, -10, -7, -5, -3, 0)]
    out += [(f"skip if median 7d return > {z}%", ("med7", ">", z)) for z in (5, 10, 15, 20)]
    out += [(f"skip if 30d breadth fell >= {k} pts in 7d", ("above30_chg7", "<", -k)) for k in (10, 20, 30, 40)]
    out += [(f"skip if 30d breadth rose >= {k} pts in 7d", ("above30_chg7", ">", k)) for k in (10, 20, 30, 40)]
    return out


def keep_mask(rule, feat):
    if rule is None:
        return np.ones(len(feat), bool)
    col, op, x = rule
    v = feat[col].to_numpy()
    skip = (v < x) if op == "<" else (v > x)                     # NaN never skips
    return ~skip


def job(args):
    name, rule, tag, start, end, fee, slip = args
    kept = [c for c, k in zip(C, keep_mask(rule, FEAT)) if k]
    s = replay(M, kept, PLAN, start, end, fee=fee, slip=slip)
    return {"rule": name, "tag": tag, "start": start.date(), "profit": s["profit"], "dd_usd": s["dd_usd"],
            "dd_pct": s["dd_pct"], "trades": s["trades"], "win_pct": s["win_pct"]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 230)
    pd.set_option("display.max_rows", 300)
    feats = build_features()
    window = feats[(feats.index >= ca.START) & (feats.index < ca.END)]
    print(f"coins with data per day in the test window: min {window.coins.min()}, median {window.coins.median():.0f}")
    print(window[["above30", "above7", "pos7", "med7"]].describe().round(1).to_string())

    init()
    s, led, _ = replay(M, C, PLAN, want_frames=True)
    led = pd.concat([led.reset_index(drop=True), attach(led.entry_time, feats)], axis=1)
    led["win"] = led.pnl > 0
    led["ret"] = 100 * led.pnl / led.spend
    led.to_csv(OUT / "control_trades_with_breadth.csv", index=False)
    print(f"\n=== control: profit ${s['profit']:.2f}, {s['trades']} trades, win {s['win_pct']:.1f}%, DD {s['dd_pct']:.2f}%")
    print(f"\n=== {COIN} trades by breadth at the buy: win rate, average loss, profit")
    for col, bins in (("above30", [0, 20, 40, 60, 80, 100]), ("above7", [0, 20, 40, 60, 80, 100]),
                      ("med7", [-100, -10, -5, 0, 5, 10, 100]), ("above30_chg7", [-100, -30, -10, 10, 30, 100])):
        g = led.groupby(pd.cut(led[col], bins, include_lowest=True), observed=True)
        cells = [f"{k}: {len(v)} tr {100 * v.win.mean():.0f}% {v[~v.win].ret.mean():.1f}% ${v.pnl.sum():+.0f}"
                 for k, v in g]
        print(f"{col:13s} " + " | ".join(cells))

    tasks = []
    for name, rule in rules():
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
        t[f"{tag}_worse"] = (diff < -1e-9).sum()
        t[f"{tag}_median_vs_none"] = diff.median()
    t["vs_none"] = t.profit - t.loc["none", "profit"]
    t = t.sort_values("profit", ascending=False)
    print(f"\n=== {len(t)} rules, full history, best first (top 25)")
    print(t.head(25).round(2).to_string())
    print(f"rules beating no filter on full history: {(t.vs_none > 0).sum()} of {len(t) - 1}")

    rows = []
    for a, b in TESTS:
        tr = df[(df.tag == "wf_train") & (df.start == (T(a) - pd.DateOffset(months=6)).date())].set_index("rule")
        te = df[(df.tag == "wf_test") & (df.start == T(a).date())].set_index("rule")
        chosen = tr.profit.idxmax()
        rows.append({"quarter": a, "chosen": chosen, "chosen_profit": te.loc[chosen, "profit"],
                     "none_profit": te.loc["none", "profit"],
                     "change": te.loc[chosen, "profit"] - te.loc["none", "profit"]})
    wf = pd.DataFrame(rows)
    print("\n=== walk-forward: rule chosen on the previous 6 months, used blind in the next quarter")
    print(wf.round(2).to_string(index=False))
    print(f"total: chosen ${wf.chosen_profit.sum():.2f} vs no filter ${wf.none_profit.sum():.2f} = "
          f"{wf.change.sum():+.2f}, better {(wf.change > 1e-9).sum()}/6, worse {(wf.change < -1e-9).sum()}/6")

    halves = []
    for pick, test in (("earlier", "later"), ("later", "earlier")):
        chosen = t[pick].idxmax()
        halves.append({"choose_on": pick, "chosen": chosen, "test_profit": t.loc[chosen, test],
                       "none_test": t.loc["none", test], "change": t.loc[chosen, test] - t.loc["none", test]})
    print("\n=== choose on one year, test on the other")
    print(pd.DataFrame(halves).round(2).to_string(index=False))

    best = t.index[0] if t.index[0] != "none" else t.index[1]
    q = df[(df.tag == "wf_test") & df.rule.isin([best, "none"])].pivot(index="start", columns="rule", values="profit")
    print(f"\n=== best full-history rule '{best}' held fixed in each quarter (hindsight choice)")
    print(q.round(2).to_string())
    skipped = led[~keep_mask(dict(rules())[best], attach(led.entry_time, feats))]
    print(f"control trades this rule skips: {len(skipped)}, win {100 * skipped.win.mean():.0f}%, "
          f"profit ${skipped.pnl.sum():.2f}")
    print(skipped.groupby(skipped.entry_time.astype(str).str[:7]).pnl.agg(["size", "sum"]).round(2).T.to_string())
    t.to_csv(OUT / "summary.csv")
    wf.to_csv(OUT / "walk_forward.csv", index=False)


if __name__ == "__main__":
    main()
