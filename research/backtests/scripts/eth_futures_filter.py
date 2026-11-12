"""ETH only: can Binance futures positioning (funding, open interest, long/short ratios) pick out losing buys?

Same money rule and tests as eth_fear_greed.py: $300, 3 x $100 -> 5 x $100 -> +$20 per lot per $100; deployed ETH
entries and exits unchanged; a rule can only skip a buy.

Features are built on hourly bars from the 5-minute metrics (data/eth_futures_crowding, Binance archive) and the
8-hourly funding rate. A row stamped T is used only from T+5 min; an hourly feature only after its hour closes.
Thresholds are causal: each feature is turned into its percentile within the TRAILING 90 days, so a rule like
"skip when funding is in its top 10%" never uses data from after the buy.
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
from compounding_full_analysis import T, replay  # noqa: E402
from eth_fear_greed import PLAN, TESTS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# ETH by default; FG_COIN=SOL (etc.) runs the identical test on another coin's futures data.
COIN = os.environ.get("FG_COIN", "ETH").upper()
DATA = ROOT / "data" / ("eth_futures_crowding" if COIN == "ETH" else f"{COIN.lower()}_futures")
OUT = ROOT / "results" / f"{COIN.lower()}_futures_filter_v1"
WINDOW_H = 90 * 24
FEATURES = {
    "funding": "funding rate (latest settled)",
    "funding_24h": "funding, average of last 3",
    "oi_chg_1h": "open interest change, 1h",
    "oi_chg_4h": "open interest change, 4h",
    "oi_chg_24h": "open interest change, 24h",
    "oi_vs_7d": "open interest vs its 7-day average",
    "top_acct_ls": "top traders long/short (accounts)",
    "top_pos_ls": "top traders long/short (positions)",
    "global_ls": "all accounts long/short",
    "taker_1h": "taker buy/sell volume, 1h",
    "taker_4h": "taker buy/sell volume, 4h",
    "oi_minus_price_24h": "OI change minus price change, 24h",
}
M = C = FEAT = None


def build_features(market) -> pd.DataFrame:
    m = pd.read_csv(DATA / "metrics_5m.csv", parse_dates=["create_time"]).sort_values("create_time")
    m = m.set_index("create_time")
    h = pd.DataFrame({
        "oi": m.sum_open_interest.resample("1h").last(),
        "top_acct_ls": m.count_toptrader_long_short_ratio.resample("1h").last(),
        "top_pos_ls": m.sum_toptrader_long_short_ratio.resample("1h").last(),
        "global_ls": m.count_long_short_ratio.resample("1h").last(),
        "taker": m.sum_taker_long_short_vol_ratio.resample("1h").mean(),
    }).ffill()
    close = pd.Series(market.close, index=market.times).resample("1h").last().reindex(h.index).ffill()
    f = pd.read_csv(DATA / "funding_rates.csv")
    f["t"] = pd.to_datetime(f.fundingTime, unit="ms", utc=True)
    fr = f.set_index("t").fundingRate.sort_index()
    h["funding"] = fr.reindex(h.index, method="ffill")
    h["funding_24h"] = fr.rolling(3).mean().reindex(h.index, method="ffill")
    for k in (1, 4, 24):
        h[f"oi_chg_{k}h"] = h.oi.pct_change(k) * 100
    h["oi_vs_7d"] = (h.oi / h.oi.rolling(168).mean() - 1) * 100
    h["taker_1h"] = h.taker
    h["taker_4h"] = h.taker.rolling(4).mean()
    h["oi_minus_price_24h"] = h.oi_chg_24h - close.pct_change(24) * 100
    feats = h[list(FEATURES)]
    pct = feats.rolling(WINDOW_H, min_periods=24 * 30).rank(pct=True)
    out = pd.concat([feats, pct.add_suffix("_pct")], axis=1)
    # An hourly row is labelled with its start; it is complete an hour (plus the 5-minute stamp lag) later.
    out.index = out.index + pd.Timedelta(minutes=65)
    return out


def attach(cands, feats):
    times = pd.DatetimeIndex([c.entry_time for c in cands])
    idx = feats.index.searchsorted(times, side="right") - 1
    return feats.iloc[idx].reset_index(drop=True)


def init():
    global M, C, FEAT
    M, cands = ca.load()
    C = [c for c in cands if c.coin == COIN]
    FEAT = attach(C, build_features(M[COIN]))


def rules():
    out = [("none", None)]
    for f in FEATURES:
        for q in (0.8, 0.9, 0.95):
            out.append((f"skip {f} top {round((1 - q) * 100)}%", (f, ">=", q)))
        for q in (0.05, 0.1, 0.2):
            out.append((f"skip {f} bottom {round(q * 100)}%", (f, "<=", q)))
    combos = {
        "crowded longs: funding & OI24h top 20%": [("funding", ">=", 0.8), ("oi_chg_24h", ">=", 0.8)],
        "crowded longs: funding & top-pos L/S top 20%": [("funding", ">=", 0.8), ("top_pos_ls", ">=", 0.8)],
        "shorts piling: OI24h top 20% & taker bottom 20%": [("oi_chg_24h", ">=", 0.8), ("taker_4h", "<=", 0.2)],
        "deleveraging: OI24h bottom 10% & funding bottom 20%": [("oi_chg_24h", "<=", 0.1), ("funding", "<=", 0.2)],
        "retail long, whales short: global L/S top 20% & top-pos bottom 20%": [("global_ls", ">=", 0.8),
                                                                           ("top_pos_ls", "<=", 0.2)],
    }
    out += [(f"skip {name}", ("and", conds)) for name, conds in combos.items()]
    return out


def keep_mask(rule, feat):
    if rule is None:
        return np.ones(len(feat), bool)

    def hit(f, op, q):
        v = feat[f"{f}_pct"].to_numpy()
        return (v >= q) if op == ">=" else (v <= q)          # NaN (warm-up) never skips

    if rule[0] == "and":
        skip = np.ones(len(feat), bool)
        for cond in rule[1]:
            skip &= hit(*cond)
        return ~skip
    return ~hit(*rule)


def job(args):
    name, rule, tag, start, end, fee, slip = args
    kept = [c for c, k in zip(C, keep_mask(rule, FEAT)) if k]
    s = replay(M, kept, PLAN, start, end, fee=fee, slip=slip)
    return {"rule": name, "tag": tag, "start": start.date(), "profit": s["profit"], "dd_usd": s["dd_usd"],
            "dd_pct": s["dd_pct"], "trades": s["trades"], "win_pct": s["win_pct"]}


def diagnostics():
    init()
    s, led, _ = replay(M, C, PLAN, want_frames=True)
    led = led.reset_index(drop=True)
    feat = attach([type("c", (), {"entry_time": t})() for t in led.entry_time], build_features(M[COIN]))
    led = pd.concat([led, feat], axis=1)
    led["win"] = led.pnl > 0
    led["ret"] = 100 * led.pnl / led.spend
    rows = []
    for f, label in FEATURES.items():
        q = pd.qcut(led[f].rank(method="first"), 5, labels=False)
        for i, g in led.groupby(q):
            rows.append({"feature": label, "quintile": f"Q{int(i) + 1}", "trades": len(g),
                         "win%": 100 * g.win.mean(), "avg_loss%": g[~g.win].ret.mean(), "profit": g.pnl.sum()})
    return s, pd.DataFrame(rows), led


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 230)
    pd.set_option("display.max_rows", 300)
    s, quint, led = diagnostics()
    led.to_csv(OUT / "control_trades_with_features.csv", index=False)
    quint.to_csv(OUT / "quintiles.csv", index=False)
    print(f"=== control: profit ${s['profit']:.2f}, {s['trades']} trades, win {s['win_pct']:.1f}%, DD {s['dd_pct']:.2f}%")
    print("\n=== win rate, average loss and profit by quintile of each feature at the buy (Q1 lowest)")
    piv = quint.assign(cell=lambda d: d.apply(lambda r: f"{r['win%']:.0f}% {r['avg_loss%']:.1f}% ${r.profit:+.0f}", axis=1))
    print(piv.pivot(index="feature", columns="quintile", values="cell").to_string())

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
    t.to_csv(OUT / "summary.csv")
    wf.to_csv(OUT / "walk_forward.csv", index=False)


if __name__ == "__main__":
    main()
