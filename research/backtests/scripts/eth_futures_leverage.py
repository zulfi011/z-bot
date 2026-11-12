"""ETH's live strategy on USDT-M futures at 3x, 5x and 10x, instead of spot. No change to the rules.

The same lots, the same entries and the same exits as the deployed strategy (dip + Mode C + pullback, shared
pool, break-even floor, no pyramid) - only the instrument changes. Futures differ from spot in three ways that
matter, and all three are modelled rather than waved at:

  fees      taker 0.05% per side on the NOTIONAL (cheaper than spot's 0.075% in BNB, but the notional is
            `leverage` times bigger)
  funding   longs pay the funding rate every 8 hours at 00:00 / 08:00 / 16:00 UTC, on the notional. Counted per
            lot from how many of those stamps it is open across. The rate is an assumption, so it is swept.
  death     equity is marked every hour; when it reaches zero the account is gone and nothing trades again.
            This is generous - Binance liquidates at the maintenance margin, before equity is actually zero.

Two honestly different ways to use leverage, both reported, because they are not the same trade:

  "same position"  each lot still controls $100 of ETH, so a lot needs only $100/leverage of margin. The risk is
                   identical to spot; leverage only frees up cash. Profit is spot's, less funding.
  "same money"     each lot still puts up $100, so it controls $100 x leverage of ETH. This is what people mean
                   by trading with leverage, and it multiplies the losing streaks as well as the wins.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eth_floor_and_arm as f
import all_coins_compare as cmp
import live_ema_hold_all as live
import run_sol_stage3_space_grid as grid
import run_eth_full_research as research
import eth_pullback as pb
import three_modes as tm
import eth_regime as rg
from sol_wide_stop import simulate, FEE, LOT

TAKER = 0.0005                 # Binance USDT-M futures taker, per side
FUNDING = 0.0001               # per 8-hour stamp; ETH perp has historically averaged near this
LOTS = 5
STAMPS = (0, 8, 16)            # UTC hours at which funding is charged


def book_of():
    raw, bullish = cmp.load("ETHUSDT")
    rule = live.load_rule("eth")
    sources = ((live.live_entries(raw, rule), "dip", tm.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]),
               ([t["entry"] for t in cmp.mode_c(raw, rule, 120, 12, 2.5, 30, 1.283, 22.0, 3.5)],
                "breakout", 3.5, 1.283, 22.0),
               (pb.pullback_entries(grid.CLOSE, bullish, 24, 180, grid.TIMES, blocked=rule["blocked"]),
                "pullback", tm.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]))
    line = pd.Series(grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    f.LINE_FLOOR = line * (1 + f.COSTS / 100)
    return f.book(sources, bullish, line, 1.315, "buy price", "on arming")


def lots_of(book):
    """The deployed ledger, with the raw fill and exit prices recovered and funding stamps counted."""
    led = simulate(book, [(LOTS, f.CORE)], *research.WINDOWS["full"])["ledger"]
    hour = grid.TIMES.hour.to_numpy()
    stamp = np.isin(hour, STAMPS) & (grid.TIMES.minute.to_numpy() == 0)
    crossed = np.cumsum(stamp)
    out = []
    for lot in led.itertuples():
        fill = lot.spend / (lot.quantity * (1 + FEE))
        exit_price = lot.proceeds / (lot.quantity * (1 - grid.SLIP) * (1 - FEE))
        out.append({"entry": lot.entry, "exit": lot.exit, "fill": fill, "exit_price": exit_price,
                    "gross": exit_price / fill - 1, "source": lot.source,
                    "stamps": int(crossed[lot.exit] - crossed[lot.entry])})
    return pd.DataFrame(out)


MMR = 0.005               # maintenance margin, ETH's lowest Binance tier


def run(lots, lev, equity0, funding=FUNDING, per_lot_margin=None, gated=True):
    """Hourly equity for the whole book at one leverage. per_lot_margin None = each lot puts up $100.

    `gated` adds the two things that actually end a leveraged account, and that a naive x-the-returns model
    misses entirely: a lot can only be opened when there is FREE MARGIN for it, so a drawdown stops the
    strategy trading long before equity reaches zero; and the account is liquidated when equity falls under
    the maintenance margin on everything still open.
    """
    margin = LOT if per_lot_margin is None else per_lot_margin
    notional = margin * lev
    if gated:
        return gated_run(lots, lev, equity0, funding, margin, notional)
    hours = np.arange(np.searchsorted(grid.TIMES, research.WINDOWS["full"][0]),
                      np.searchsorted(grid.TIMES, research.WINDOWS["full"][1]), 60)
    equity = np.full(len(hours), float(equity0))
    dead_at, costs, gross_usd = None, 0.0, 0.0
    for lot in lots.itertuples():
        cost = 2 * TAKER + lot.stamps * funding                      # fraction of notional
        net = notional * (lot.gross - cost)
        costs += notional * cost
        gross_usd += notional * lot.gross
        out = np.searchsorted(hours, lot.exit)
        start = np.searchsorted(hours, lot.entry)
        equity[out:] += net
        if out > start:
            marked = notional * (grid.CLOSE[hours[start:out]] / lot.fill - 1) - notional * 2 * TAKER
            equity[start:out] += marked
    gone = np.flatnonzero(equity <= 0)
    if len(gone):
        dead_at = grid.TIMES[hours[gone[0]]]
    peak = np.maximum.accumulate(equity)
    return {"profit": equity[-1] - equity0, "fees+funding": costs, "gross": gross_usd,
            "worst equity": equity.min(), "dd%": 100 * float((equity / peak - 1).min()),
            "dead": dead_at, "equity": equity, "hours": hours, "taken": len(lots), "skipped": 0}


def gated_run(lots, lev, equity0, funding, margin, notional):
    """The same book, but a lot is only opened when the account can post its margin, and the account can be
    liquidated on the maintenance requirement."""
    hours = np.arange(np.searchsorted(grid.TIMES, research.WINDOWS["full"][0]),
                      np.searchsorted(grid.TIMES, research.WINDOWS["full"][1]), 60)
    free, open_lots, taken, skipped = float(equity0), [], [], 0
    realised = np.zeros(len(hours))
    costs = gross_usd = 0.0
    for lot in lots.itertuples():
        for held in [o for o in open_lots if o["exit"] <= lot.entry]:
            free += margin + held["net"]
        open_lots = [o for o in open_lots if o["exit"] > lot.entry]
        if free < margin:
            skipped += 1
            continue
        cost = 2 * TAKER + lot.stamps * funding
        net = notional * (lot.gross - cost)
        costs += notional * cost
        gross_usd += notional * lot.gross
        free -= margin
        rec = {"entry": lot.entry, "exit": lot.exit, "fill": lot.fill, "net": net}
        open_lots.append(rec)
        taken.append(rec)
        realised[np.searchsorted(hours, lot.exit):] += net
    equity = np.full(len(hours), float(equity0)) + realised
    exposure = np.zeros(len(hours))
    for rec in taken:
        a, b = np.searchsorted(hours, rec["entry"]), np.searchsorted(hours, rec["exit"])
        if b > a:
            equity[a:b] += notional * (grid.CLOSE[hours[a:b]] / rec["fill"] - 1) - notional * 2 * TAKER
            exposure[a:b] += notional
    dead = np.flatnonzero(equity <= MMR * exposure)
    dead_at = grid.TIMES[hours[dead[0]]] if len(dead) else None
    peak = np.maximum.accumulate(equity)
    return {"profit": equity[-1] - equity0, "fees+funding": costs, "gross": gross_usd,
            "worst equity": equity.min(), "dd%": 100 * float((equity / peak - 1).min()),
            "dead": dead_at, "equity": equity, "hours": hours,
            "taken": len(taken), "skipped": skipped}


def main() -> None:
    lots = lots_of(book_of())
    pd.set_option("display.width", 240)
    print(f"the deployed book: {len(lots)} lots, median {lots.stamps.median():.0f} funding stamps each "
          f"(mean {lots.stamps.mean():.2f}, max {lots.stamps.max()}), "
          f"gross price return per lot: mean {100 * lots.gross.mean():+.3f}%, "
          f"win rate on gross {100 * (lots.gross > 0).mean():.1f}%")

    print("\n=== A. same position, less cash tied up ($100 of ETH per lot, margin = $100/leverage)")
    rows = []
    for lev in (1, 3, 5, 10):
        r = run(lots, lev, LOTS * LOT / lev, per_lot_margin=LOT / lev)
        rows.append({"leverage": f"{lev}x", "margin needed": round(LOTS * LOT / lev, 2),
                     "cash freed": round(LOTS * LOT - LOTS * LOT / lev, 2), "profit": round(r["profit"], 2),
                     "fees+funding": round(r["fees+funding"], 2),
                     "return on margin %": round(100 * r["profit"] / (LOTS * LOT / lev), 1),
                     "worst dip %": round(r["dd%"], 1), "lots skipped": r["skipped"],
                     "wiped out": r["dead"] or "no"})
    print(pd.DataFrame(rows).set_index("leverage").to_string())

    print("\n=== B. same money, bigger position ($500 of margin, $100 per lot, notional = $100 x leverage)")
    rows = []
    for lev in (1, 2, 3, 5, 7, 10):
        r = run(lots, lev, LOTS * LOT)
        rows.append({"leverage": f"{lev}x", "notional per lot": LOT * lev,
                     "gross P&L": round(r["gross"], 2), "fees+funding": round(r["fees+funding"], 2),
                     "profit": round(r["profit"], 2), "worst equity": round(r["worst equity"], 2),
                     "worst dip %": round(r["dd%"], 1), "lots taken": r["taken"],
                     "lots skipped": r["skipped"],
                     "wiped out": str(r["dead"].date()) if r["dead"] is not None else "no"})
    frame = pd.DataFrame(rows).set_index("leverage")
    print(frame.to_string())
    print("  (a row that was wiped out never collected its profit - the account was gone first)")

    print("\n=== B, with the funding rate swept (profit, and the date the account dies)")
    rows = []
    for rate, label in ((0.00005, "0.005% / 8h (calm)"), (FUNDING, "0.01% / 8h (typical)"),
                        (0.0002, "0.02% / 8h (hot market)"), (0.0005, "0.05% / 8h (mania)")):
        row = {"funding": label}
        for lev in (3, 5, 10):
            r = run(lots, lev, LOTS * LOT, funding=rate)
            row[f"{lev}x"] = (f"dead {r['dead'].date()}" if r["dead"] is not None
                              else f"${r['profit']:.0f} (dd {r['dd%']:.0f}%)")
        rows.append(row)
    print(pd.DataFrame(rows).set_index("funding").to_string())

    print("\n=== why it dies: the worst losing run, at each leverage ($500 of margin)")
    for lev in (1, 3, 5, 10):
        r = run(lots, lev, LOTS * LOT)
        e = r["equity"]
        peak = np.maximum.accumulate(e)
        trough = int(np.argmin(e / peak))
        top = int(np.argmax(peak[:trough + 1] == peak[trough]))
        print(f"  {lev:2d}x: {grid.TIMES[r['hours'][top]].date()} -> {grid.TIMES[r['hours'][trough]].date()}  "
              f"${e[top]:8.2f} -> ${e[trough]:8.2f}  ({100 * (e[trough] / e[top] - 1):+.1f}%)")

    print("\n=== the single worst day and week of the spot strategy, multiplied")
    r1 = run(lots, 1, LOTS * LOT)
    e = r1["equity"]
    day = pd.Series(e).diff(24).min()
    week = pd.Series(e).diff(24 * 7).min()
    print(f"  worst 24h on spot ${day:.2f} -> at 3x ${day * 3:.2f}, 5x ${day * 5:.2f}, 10x ${day * 10:.2f}")
    print(f"  worst 7d  on spot ${week:.2f} -> at 3x ${week * 3:.2f}, 5x ${week * 5:.2f}, 10x ${week * 10:.2f}")
    print(f"  ({100 * week * 10 / (LOTS * LOT):.0f}% of a $500 account in one week at 10x)")


if __name__ == "__main__":
    main()
