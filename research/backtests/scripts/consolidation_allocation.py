"""Fixed $100 per coin (what the live app does now) vs one shared $300 pot, on the consolidation rules."""

from __future__ import annotations

import pandas as pd

import consolidation_portfolio as portfolio
import run_eth_full_research as research

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]


def periods(trades, initial, cap, max_open):
    return {name: portfolio.run(trades, *research.WINDOWS[name], initial=initial, cap=cap, max_open=max_open)
            for name in ("full", "earlier", "later", "unseen", *WF)}


def summarise(label, parts):
    full = {key: sum(p["full"][key] for p in parts) for key in ("profit", "trades", "wins", "skipped")}
    return {"setup": label, "trades": full["trades"], "missed": full["skipped"],
            "win_rate": round(100 * full["wins"] / max(full["trades"], 1)),
            "full": full["profit"],
            "earlier": sum(p["earlier"]["profit"] for p in parts),
            "later": sum(p["later"]["profit"] for p in parts),
            "unseen": sum(p["unseen"]["profit"] for p in parts),
            "walk_forward": sum(p[w]["profit"] for p in parts for w in WF),
            "wf_windows": f"{sum(sum(p[w]['profit'] for p in parts) > 0 for w in WF)}/6",
            "drawdown": min(p["full"]["dd"] for p in parts) if len(parts) == 1 else float("nan"),
            "busy_pct": sum(p["full"]["busy_pct"] for p in parts) / len(parts)}


def main() -> None:
    per_coin = {coin: portfolio.trades_for(coin) for coin in portfolio.RULES}
    three = pd.concat([per_coin[c] for c in ("SOL", "ETH", "TRX")], ignore_index=True)
    five = pd.concat(per_coin.values(), ignore_index=True)
    rows = []

    # what the live app does now: each of the three coins gets its own $100 and cannot borrow from the others
    parts = [periods(per_coin[c], 100.0, 1.0, 1) for c in ("SOL", "ETH", "TRX")]
    rows.append(summarise("fixed $100 each to SOL/ETH/TRX (today)", parts))

    for label, trades, cap, max_open in [("shared $300, 3 lots, SOL/ETH/TRX", three, 1 / 3, 3),
                                         ("shared $300, 3 lots, all 5 coins", five, 1 / 3, 3),
                                         ("shared $300, 4 lots of $75, all 5 coins", five, 0.25, 4),
                                         ("shared $300, 5 lots of $60, all 5 coins", five, 0.2, 5),
                                         ("shared $300, 2 lots, all 5 coins", five, 0.5, 2),
                                         ("shared $300, all-in, all 5 coins", five, 1.0, 1)]:
        rows.append(summarise(label, [periods(trades, 300.0, cap, max_open)]))

    pd.set_option("display.width", 220)
    print("consolidation rules, $300 total, BNB fees\n")
    print(pd.DataFrame(rows).set_index("setup").round(2).to_string())

    print("\nper coin inside today's fixed-$100 setup:")
    detail = []
    for coin, frame in per_coin.items():
        result = periods(frame, 100.0, 1.0, 1)
        detail.append({"coin": coin, "trades": result["full"]["trades"], "missed": result["full"]["skipped"],
                       "profit": result["full"]["profit"], "drawdown": result["full"]["dd"],
                       "busy_pct": result["full"]["busy_pct"]})
    print(pd.DataFrame(detail).set_index("coin").round(2).to_string())


if __name__ == "__main__":
    main()
