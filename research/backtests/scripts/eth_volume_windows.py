"""ETH only: does spot volume over LONGER windows (4h, 12h, 24h, 3 days) pick out losing buys?

The earlier volume tests on every coin used only the hour before the buy. Here, for each window W, using only the
minutes before the buy:
  quote    USDT traded in the last W / the average W over the prior 30 days ("normal")
  trades   number of trades in the last W / the same 30-day normal
  taker    taker-buy share of the last W's volume (who was aggressive: >0.5 = buyers)
Same money rule and tests as eth_fear_greed.py: $300, 3 x $100 -> 5 x $100 -> +$20 per lot per $100; deployed ETH
entries and exits unchanged; a rule can only skip a buy.
"""

from __future__ import annotations

import os
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compounding_full_analysis as ca  # noqa: E402
import stage3_replay as replay  # noqa: E402
from compounding_full_analysis import T  # noqa: E402
from eth_fear_greed import PLAN, TESTS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# ETH by default; FG_COIN=SOL (etc.) runs the identical test on another coin.
COIN = os.environ.get("FG_COIN", "ETH").upper()
OUT = ROOT / "results" / f"{COIN.lower()}_volume_windows_v1"
SYMBOL = f"{COIN}USDT"
COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume", "number_of_trades",
           "taker_buy_base_volume"]
WINDOWS = {"4h": 240, "12h": 720, "24h": 1440, "3d": 4320}
NORMAL = 30 * 1440
M = C = FEAT = None


def load_raw_volume() -> pd.DataFrame:
    frame = pd.read_parquet(replay.RAW_DIR / SYMBOL / f"{SYMBOL}_1m.parquet", columns=COLUMNS)
    parts = []
    for path in sorted(replay.HOLDOUT_DIR.glob(f"{SYMBOL}-1m-*.zip")):
        with zipfile.ZipFile(path) as archive:
            with archive.open(archive.namelist()[0]) as handle:
                part = pd.read_csv(handle, header=None, usecols=[0, 1, 2, 3, 4, 5, 7, 8, 9])
        if not str(part.iloc[0, 0]).isdigit():
            part = part.iloc[1:]
        parts.append(part)
    if parts:
        extra = pd.concat(parts)
        extra.columns = COLUMNS
        stamps = extra.open_time.astype("int64")
        extra["open_time"] = pd.to_datetime(np.where(stamps > 10**14, stamps, stamps * 1000), unit="us", utc=True)
        for column in COLUMNS[1:]:
            extra[column] = extra[column].astype(float)
        frame = pd.concat([frame, extra])
    frame = frame.drop_duplicates("open_time").sort_values("open_time").set_index("open_time")
    return frame.asfreq("1min").fillna({c: 0.0 for c in COLUMNS[5:]})


def build_features():
    raw = load_raw_volume()
    out = {"times": raw.index}
    cs = {name: np.concatenate([[0.0], np.cumsum(raw[col].to_numpy())])
          for name, col in (("quote", "quote_volume"), ("trades", "number_of_trades"),
                            ("vol", "volume"), ("taker", "taker_buy_base_volume"))}
    n = len(raw)
    i = np.arange(n + 1)                                       # i = number of complete minutes before minute i
    for label, w in WINDOWS.items():
        for name in ("quote", "trades"):
            last = cs[name][i] - cs[name][np.maximum(i - w, 0)]
            normal = (cs[name][i] - cs[name][np.maximum(i - NORMAL, 0)]) * w / NORMAL
            ratio = np.where((i >= NORMAL) & (normal > 0), last / np.where(normal > 0, normal, 1), np.nan)
            out[f"{name}_{label}"] = ratio
        vol = cs["vol"][i] - cs["vol"][np.maximum(i - w, 0)]
        tak = cs["taker"][i] - cs["taker"][np.maximum(i - w, 0)]
        out[f"taker_{label}"] = np.where((i >= w) & (vol > 0), tak / np.where(vol > 0, vol, 1), np.nan)
    return out


def attach(times, feats):
    # A buy at minute t sees only the minutes before t: index = position of t in the minute grid.
    pos = feats["times"].searchsorted(pd.DatetimeIndex(times))
    return pd.DataFrame({k: v[pos] for k, v in feats.items() if k != "times"})


def init():
    global M, C, FEAT
    M, cands = ca.load()
    C = [c for c in cands if c.coin == COIN]
    FEAT = attach([c.entry_time for c in C], build_features())


def rules():
    out = [("none", None)]
    for label in WINDOWS:
        for name in ("quote", "trades"):
            out += [(f"skip if {name} {label} > {x}x", (f"{name}_{label}", ">", x)) for x in (1.25, 1.5, 2.0, 2.5, 3.0)]
            out += [(f"skip if {name} {label} < {x}x", (f"{name}_{label}", "<", x)) for x in (0.5, 0.6, 0.75, 0.9)]
        out += [(f"skip if taker {label} > {x}", (f"taker_{label}", ">", x)) for x in (0.52, 0.55, 0.6)]
        out += [(f"skip if taker {label} < {x}", (f"taker_{label}", "<", x)) for x in (0.45, 0.48, 0.5)]
    return out


def keep_mask(rule, feat):
    if rule is None:
        return np.ones(len(feat), bool)
    col, op, x = rule
    v = feat[col].to_numpy()
    return ~((v > x) if op == ">" else (v < x))                 # NaN never skips


def job(args):
    name, rule, tag, start, end, fee, slip = args
    kept = [c for c, k in zip(C, keep_mask(rule, FEAT)) if k]
    s = ca.replay(M, kept, PLAN, start, end, fee=fee, slip=slip)
    return {"rule": name, "tag": tag, "start": start.date(), "profit": s["profit"], "dd_usd": s["dd_usd"],
            "dd_pct": s["dd_pct"], "trades": s["trades"], "win_pct": s["win_pct"]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 240)
    pd.set_option("display.max_rows", 300)
    feats = build_features()
    init()
    s, led, _ = ca.replay(M, C, PLAN, want_frames=True)
    led = pd.concat([led.reset_index(drop=True), attach(led.entry_time, feats)], axis=1)
    led["win"] = led.pnl > 0
    led["ret"] = 100 * led.pnl / led.spend
    led.to_csv(OUT / "control_trades_with_volume.csv", index=False)
    print(f"=== control: profit ${s['profit']:.2f}, {s['trades']} trades, win {s['win_pct']:.1f}%, DD {s['dd_pct']:.2f}%")
    print(f"\n=== {COIN} trades by volume at the buy: trades, win rate, average loss, profit")
    for label in WINDOWS:
        for col, bins in ((f"quote_{label}", [0, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 100]),
                          (f"taker_{label}", [0, 0.46, 0.48, 0.50, 0.52, 0.54, 1])):
            g = led.groupby(pd.cut(led[col], bins), observed=True)
            print(f"{col:10s} " + " | ".join(
                f"{k}: {len(v)} {100 * v.win.mean():.0f}% {v[~v.win].ret.mean():.1f}% ${v.pnl.sum():+.0f}" for k, v in g))

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
    t["vs_none"] = t.profit - t.loc["none", "profit"]
    t = t.sort_values("profit", ascending=False)
    print(f"\n=== {len(t)} rules, full history, best first (top 20)")
    print(t.head(20).round(2).to_string())
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
    skipped = led[~keep_mask(dict(rules())[best], led)]
    print(f"control trades this rule skips: {len(skipped)}, win {100 * skipped.win.mean():.0f}%, "
          f"profit ${skipped.pnl.sum():.2f}")
    print(skipped.groupby(skipped.entry_time.astype(str).str[:7]).pnl.agg(["size", "sum"]).round(2).T.to_string())
    t.to_csv(OUT / "summary.csv")
    wf.to_csv(OUT / "walk_forward.csv", index=False)


if __name__ == "__main__":
    main()
