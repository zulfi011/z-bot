"""Which three coins deserve the $100 each, under the strategies now built.

Every figure so far has been $300 as 3 x $100 lots. One lot changes things: a coin that fires overlapping
signals cannot take most of them, so the coins that benefit from many chances lose more than the patient ones.
This measures each coin's NEW strategy on exactly what is being proposed - a single $100 lot.
"""

from __future__ import annotations

import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay
import three_modes as three

WF = [f"wf{i}_test" for i in range(len(research.TESTS))]
# Each coin as built: (Mode A hours or None, Mode C settings or None)
BUILT = {
    "eth": (16, dict(chart=120, bars=12, zone=2.5, confirm=30, stop=3.5, arm=1.283, giveback=22.0), 4.5),
    "sol": (8, dict(chart=60, bars=24, zone=2.0, confirm=0, stop=4.0, arm=1.283, giveback=22.0), None),
    "trx": (None, dict(chart=60, bars=40, zone=2.0, confirm=3, stop=3.0, arm=1.283, giveback=22.0), None),
    "aave": (None, dict(chart=30, bars=24, zone=2.0, confirm=60, stop=3.5, arm=1.283, giveback=22.0), None),
    "btc": (None, None, None),
}


def measure(coin: str, lots: int, lot_usd: float) -> dict:
    three.COIN = coin
    hours, mode_c, dip_stop = BUILT[coin]
    rule = live.load_rule(coin)
    raw = replay.load_raw(f"{coin.upper()}USDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = 2 / 10_000
    grid.TIMES = pd.DatetimeIndex(raw.open_time)
    bullish = live.regime_flags(raw)
    ema = pd.Series(grid.CLOSE).ewm(span=hours * 60, adjust=False).mean().to_numpy() if hours else None
    use = ({"dip", "breakout"} if hours else set())
    three.LOT, three.LOTS, three.INITIAL = lot_usd, lots, lot_usd * lots

    def run(trades, label):
        return three.evaluate(label, trades)

    new = run(three.build(raw, bullish, ema, use, mode_c=mode_c, dip_stop=dip_stop or rule["stop_pct"]), coin)
    old = run(three.build(raw, bullish, None, set(), mode_c=None, dip_stop=rule["stop_pct"]), coin)
    return {"coin": coin.upper(), "trades": new["trades"], "win_rate": new["win_rate"],
            "new_profit": new["profit"], "old_profit": old["profit"],
            "gain": round(new["profit"] - old["profit"], 2),
            "return_pct": round(new["profit"] / (lot_usd * lots) * 100, 1),
            "unseen": new["unseen"], "walk_forward": new["walk_forward"],
            "wf_windows": new["wf_windows"], "drawdown": new["drawdown"]}


def main() -> None:
    pd.set_option("display.width", 250)
    for lots, lot_usd, title in ((1, 100.0, "ONE $100 lot per coin - what you are actually proposing"),
                                 (3, 100.0, "three $100 lots (what every earlier figure used)")):
        rows = [measure(coin, lots, lot_usd) for coin in BUILT]
        frame = pd.DataFrame(rows).sort_values("new_profit", ascending=False)
        print(f"\n=== {title}")
        print(frame.set_index("coin").to_string())


if __name__ == "__main__":
    main()
