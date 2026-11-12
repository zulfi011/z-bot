"""Does volume improve SOL - taking a trade only when the market is busy (or only when it is quiet)?

The same question that was asked of ETH and answered no, asked again from scratch for SOL, because a filter that
fails on one coin says nothing about another.

The measure is always a RATIO, never an absolute: how busy the hour before the buy was, compared with the same
coin's own normal. 1.0 is a perfectly ordinary hour, 2.0 is twice normal. That is the only fair way to compare
2024 volume with 2026 volume.

  volume  base volume, SOL traded, in the 60 minutes before the buy / its average hour over the prior 7 days
  quote   the same in USDT traded
  trades  the same in number of individual trades
  taker   the taker-buy share of that hour's volume - who was the aggressor, not how much (an absolute, 0-1)
  band    Mode C only, ETH's original measure: the breakout bar's volume / the average bar of the quiet band

Everything is known before the buy: the ratios end at the minute before the entry minute, whose open is the fill.

Every combination: 5 measures x both directions (only when busy / only when quiet) x every sensible threshold x
which way in it gates (Mode C only, the dip only, or both) x 3, 4 and 5 core lots. Then the honest test: choose
the filter on the six months before each window and see what it earns in the window it never saw.
"""

from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd

import eth_optimal as opt
import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import eth_regime as rg
import sol_pullback as sp

COIN, SYMBOL = "sol", "SOLUSDT"
COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume",
           "number_of_trades", "taker_buy_base_volume"]
HOUR, NORMAL = 60, 7 * 1440              # the hour before the buy, against the prior week's average hour
FEE, MIN_ORDER, LOT = 7.5 / 10_000, 5.0, 100.0
CORE = {"dip", "breakout"}
TRAINS = [f"wf{i}_train" for i in range(6)]
RATIO_FLOORS = [0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
TAKER_FLOORS = [0.45, 0.48, 0.50, 0.52, 0.55, 0.60]


def load_raw_volume() -> pd.DataFrame:
    """The same rows replay.load_raw gives, with the four participation columns kept."""
    frame = pd.read_parquet(replay.RAW_DIR / SYMBOL / f"{SYMBOL}_1m.parquet", columns=COLUMNS)
    parts = []
    for path in sorted(replay.HOLDOUT_DIR.glob(f"{SYMBOL}-1m-*.zip")):
        with zipfile.ZipFile(path) as archive:
            with archive.open(archive.namelist()[0]) as handle:
                part = pd.read_csv(handle, header=None, usecols=[0, 1, 2, 3, 4, 5, 7, 8, 9])
        if not str(part.iloc[0, 0]).isdigit():
            part = part.iloc[1:]
        parts.append(part)
    extra = pd.concat(parts)
    extra.columns = COLUMNS
    stamps = extra.open_time.astype("int64")
    micros = np.where(stamps > 10**14, stamps, stamps * 1000)          # the archives switched units in 2025
    extra["open_time"] = pd.to_datetime(micros, unit="us", utc=True)
    for column in COLUMNS[1:]:
        extra[column] = extra[column].astype(float)
    frame = pd.concat([frame, extra]).drop_duplicates("open_time").sort_values("open_time")
    return frame.reset_index(drop=True)


def setup():
    """sol_pullback.setup(), but from the volume-carrying rows, so every array lines up."""
    raw = load_raw_volume()
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=sp.EMA_HOURS * 60, adjust=False).mean().to_numpy()
    return raw, bullish, ema


def minute_ratios(raw: pd.DataFrame) -> dict[str, np.ndarray]:
    """For every minute: how busy the hour BEFORE it was, against this coin's own normal hour."""
    out = {}
    for name, column in (("volume", "volume"), ("quote", "quote_volume"), ("trades", "number_of_trades")):
        series = pd.Series(raw[column].to_numpy(float))
        recent = series.rolling(HOUR).sum().shift(1)                   # ends one minute before the fill
        normal = series.rolling(NORMAL).mean().shift(1) * HOUR
        out[name] = (recent / normal).to_numpy()
    volume = pd.Series(raw.volume.to_numpy(float)).rolling(HOUR).sum().shift(1)
    taker = pd.Series(raw.taker_buy_base_volume.to_numpy(float)).rolling(HOUR).sum().shift(1)
    out["taker"] = (taker / volume).to_numpy()
    return out


def mode_c_with_band(raw: pd.DataFrame, bullish, ema):
    """Mode C's entries plus each break's band ratio: the breakout bar's volume / the band's average bar."""
    mc = sp.MODE_C
    minutes = mc["chart"]
    bucket = np.arange(len(raw)) // minutes
    frame = pd.DataFrame({"bucket": bucket, "high": raw.high.to_numpy(float), "low": raw.low.to_numpy(float),
                          "close": raw.close.to_numpy(float), "volume": raw.volume.to_numpy(float),
                          "index": np.arange(len(raw))})
    g = frame.groupby("bucket").agg(high=("high", "max"), low=("low", "min"), close=("close", "last"),
                                    volume=("volume", "sum"), index=("index", "last"), count=("index", "size"))
    g = g[g["count"] == minutes]
    high, low, close = g.high.to_numpy(), g.low.to_numpy(), g.close.to_numpy()
    last_minute, volume = g["index"].to_numpy(), g.volume.to_numpy()

    top = pd.Series(high).rolling(mc["bars"]).max().to_numpy()
    bottom = pd.Series(low).rolling(mc["bars"]).min().to_numpy()
    zone_top, zone_bottom = np.r_[np.nan, top[:-1]], np.r_[np.nan, bottom[:-1]]
    quiet = (zone_top / zone_bottom - 1) <= mc["zone"] / 100
    broke = quiet & (close > zone_top)
    first = broke & ~np.r_[False, broke[:-1]]
    where = np.flatnonzero(first)
    check = last_minute[where] + mc["confirm"]
    keep = check < len(raw) - 1
    where, check = where[keep], check[keep]
    held = grid.CLOSE[check] > zone_top[where]
    where, entries = where[held], (check[held] + 1).astype(np.int64)
    band = pd.Series(volume).rolling(mc["bars"]).mean().to_numpy()
    ratio = volume[where] / np.r_[np.nan, band[:-1]][where]             # the band's own bars, not the break
    return entries, ratio


def all_trades(raw, bullish, ema):
    """SOL exactly as deployed, with each lot carrying the band ratio when Mode C bought it."""
    rule = live.load_rule(COIN)
    trades = []
    for entry in live.live_entries(raw, rule):
        entry = int(entry)
        out, price, _ = opt.trade(entry, rule["activation_pct"], rule["giveback_pct"], rule["stop_pct"],
                                  ema if bullish[entry] else None)
        trades.append({"entry": entry, "exit": out, "price": price, "source": "dip", "band": np.nan})
    entries, band = mode_c_with_band(raw, bullish, ema)
    blocked = rule["blocked"]
    if blocked:
        hours = grid.TIMES[entries].hour
        keep = ~((hours >= blocked[0]) & (hours < blocked[1]))
        entries, band = entries[keep], band[keep]
    for entry, ratio in zip(entries, band):
        entry = int(entry)
        out, price, _ = opt.trade(entry, sp.MODE_C["arm"], sp.MODE_C["giveback"], sp.MODE_C["stop"],
                                  ema if bullish[entry] else None)
        trades.append({"entry": entry, "exit": out, "price": price, "source": "breakout", "band": ratio})
    return sorted(trades, key=lambda t: t["entry"])


def simulate(trades, lots, start, end):
    """One shared wallet, `lots` slots, the live buying rule (a full lot, or whatever is left)."""
    initial, wallet, slots, taken = lots * LOT, lots * LOT, [], []
    for trade in trades:
        entry = trade["entry"]
        if not (start <= grid.TIMES[entry] < end):
            continue
        for slot in [s for s in slots if s[0] <= entry]:
            wallet += slot[1]                          # every lot that has closed by now is cash again
        slots = [s for s in slots if s[0] > entry]
        if trade["exit"] < 0 or wallet < MIN_ORDER or len(slots) >= lots:
            continue
        spend = min(LOT, np.floor(wallet * 100) / 100)
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        proceeds = spend / (fill * (1 + FEE)) * trade["price"] * (1 - grid.SLIP) * (1 - FEE)
        wallet -= spend
        slots.append((trade["exit"], proceeds))
        taken.append({"source": trade["source"], "pnl": proceeds - spend, "entry": entry})
    wallet += sum(s[1] for s in slots)
    return {"profit": wallet - initial, "ledger": pd.DataFrame(taken)}


def apply_filter(trades, ratios, measure, direction, level, which):
    """Keep the trades this filter allows. `which` says which ways in it gates; the rest are always kept."""
    kept = []
    for trade in trades:
        gated = which == "both" or (which == "mode c" and trade["source"] == "breakout") \
            or (which == "dip" and trade["source"] == "dip")
        if not gated:
            kept.append(trade)
            continue
        value = trade["band"] if measure == "band" else ratios[measure][trade["entry"]]
        if np.isnan(value):
            continue                                   # not enough history to judge: do not buy blind
        if (value >= level) if direction == "busy" else (value <= level):
            kept.append(trade)
    return kept


def score(label, trades, lots=3):
    runs = {w: simulate(trades, lots, *research.WINDOWS[w]) for w in ("full", "unseen", *rg.TESTS)}
    led = runs["full"]["ledger"]
    wf = [runs[w]["profit"] for w in rg.TESTS]
    return {"setup": label, "lots": lots, "trades": len(led),
            "win%": round(100 * (led.pnl > 0).mean(), 1) if len(led) else 0.0,
            "profit": round(runs["full"]["profit"], 2), "walk_forward": round(sum(wf), 2),
            "windows": f"{sum(x > 0 for x in wf)}/6", "unseen": round(runs["unseen"]["profit"], 2)}


def combinations():
    for measure, levels in (("volume", RATIO_FLOORS), ("quote", RATIO_FLOORS), ("trades", RATIO_FLOORS),
                            ("band", RATIO_FLOORS), ("taker", TAKER_FLOORS)):
        for direction in ("busy", "quiet"):
            for level in levels:
                for which in (("mode c",) if measure == "band" else ("mode c", "dip", "both")):
                    yield measure, direction, level, which


def main() -> None:
    raw, bullish, ema = setup()
    ratios = minute_ratios(raw)
    trades = all_trades(raw, bullish, ema)
    pd.set_option("display.width", 260)

    dips = [t for t in trades if t["source"] == "dip"]
    breaks = [t for t in trades if t["source"] == "breakout"]
    print(f"SOL candidates: {len(dips)} dips, {len(breaks)} Mode C breaks")
    print("\n=== how busy SOL is when it buys (ratio to its own normal hour; taker is a 0-1 share)")
    described = {name: pd.Series([ratios[name][t['entry']] for t in trades]) for name in ratios}
    described["band (Mode C)"] = pd.Series([t["band"] for t in breaks])
    print(pd.DataFrame(described).describe(percentiles=[.1, .25, .5, .75, .9]).round(3).to_string())

    print("\n=== does a busier hour actually pay better? (every lot, by the hour-before volume ratio)")
    ledger = simulate(trades, 3, *research.WINDOWS["full"])["ledger"]
    ledger = ledger.assign(ratio=[ratios["volume"][e] for e in ledger.entry])
    buckets = pd.cut(ledger.ratio, [0, 0.75, 1.0, 1.5, 2.0, np.inf],
                     labels=["<0.75", "0.75-1.0", "1.0-1.5", "1.5-2.0", ">2.0"])
    rows = [{"volume ratio": name, "trades": len(part), "win%": round(100 * (part.pnl > 0).mean(), 1),
             "total_pnl": round(part.pnl.sum(), 2), "avg_pnl": round(part.pnl.mean(), 3)}
            for name, part in ledger.groupby(buckets, observed=True)]
    print(pd.DataFrame(rows).set_index("volume ratio").to_string())

    base = score("no filter (deployed today)", trades)
    print("\n=== SOL as deployed, 3 x $100")
    print(pd.DataFrame([base]).set_index("setup").to_string())

    sets = {key: apply_filter(trades, ratios, *key) for key in combinations()}
    print(f"\n=== 1. all {len(sets)} filters on SOL's 3 lots (best 12 by walk-forward, then the worst 3)")
    rows = [score(f"{m} {d} {l:g}, {w}", kept) for (m, d, l, w), kept in sets.items()]
    frame = pd.DataFrame(rows).sort_values("walk_forward", ascending=False)
    print(frame.set_index("setup").head(12).to_string())
    print("  worst three:"); print(frame.set_index("setup").tail(3).to_string())
    print(f"  filters that beat doing nothing on the full window: "
          f"{int((frame.profit > base['profit']).sum())}/{len(frame)}; "
          f"on walk-forward: {int((frame.walk_forward > base['walk_forward']).sum())}/{len(frame)}")

    print("\n=== 2. the best four filters at 3, 4 and 5 core lots, against no filter at the same money")
    best_keys = [key for key, _ in sorted(zip(sets, rows), key=lambda item: -item[1]["walk_forward"])][:4]
    table = []
    for lots in (3, 4, 5):
        table.append(score(f"no filter, {lots} lots", trades, lots))
        for key in best_keys:
            m, d, l, w = key
            table.append(score(f"{m} {d} {l:g}, {w}", sets[key], lots))
    print(pd.DataFrame(table).set_index("setup").to_string())

    print("\n=== 3. honest test: choose the filter on the six months before each window, then use it unseen")
    for lots in (3, 5):
        base_w = {w: simulate(trades, lots, *research.WINDOWS[w])["profit"] for w in (*TRAINS, *rg.TESTS)}
        scores = {k: {w: simulate(v, lots, *research.WINDOWS[w])["profit"] - base_w[w]
                      for w in (*TRAINS, *rg.TESTS)} for k, v in sets.items()}
        picks = [max(scores, key=lambda k: scores[k][TRAINS[i]]) for i in range(6)]
        honest = sum(scores[p][t] for p, t in zip(picks, rg.TESTS))
        wins = sum(scores[p][t] > 0 for p, t in zip(picks, rg.TESTS))
        best = max(sets, key=lambda k: sum(scores[k][t] for t in rg.TESTS))
        print(f"  {lots} lots: honest ${honest:8.2f} ({wins}/6 windows) | best fixed filter in hindsight "
              f"{best[0]} {best[1]} {best[2]:g}, {best[3]}: ${sum(scores[best][t] for t in rg.TESTS):8.2f}")
        print(f"           what it picked each time: {', '.join(f'{p[0]} {p[1]} {p[2]:g}/{p[3]}' for p in picks)}")


if __name__ == "__main__":
    main()
