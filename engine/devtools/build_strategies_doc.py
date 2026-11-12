"""Write docs/guide/STRATEGIES.md from the strategy files the bot actually runs.

Run from the repository root after changing any engine/*_strategy.json:

    python engine/devtools/build_strategies_doc.py

The page shows rules and settings in plain words and percentages. It never prints money amounts.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COINS = [("SOL", "Solana"), ("ETH", "Ethereum"), ("BTC", "Bitcoin"), ("AAVE", "Aave"), ("TRX", "Tron")]
OUT = ROOT / "docs" / "guide" / "STRATEGIES.md"


def pct(value: float) -> str:
    return f"{value:g}%"


def hours(minutes: float) -> str:
    return f"{minutes / 60:g}h" if minutes >= 60 else f"{minutes:g} min"


def coin_section(code: str, name: str, s: dict) -> str:
    entry, exit_ = s["entry"], s["exit"]
    days = s["averages"]["signal_average_days"]
    candle = s["market"]["signal_timeframe"].replace("m", "-min")
    trail = exit_["trailing_stop"]
    blocked = entry.get("blocked_entry_hours_utc")
    trend = exit_.get("trend_exit") or {}
    extra = entry.get("trend_filter") or {}
    rows = [
        ("Average", f"{days}-day simple average of daily closes"),
        ("Dip: buys when", f"the price rises from below into ±{pct(entry['touch_zone_pct'])} of the average, "
                           f"then a green {candle} candle confirms within {entry['confirmation']['maximum_wait_minutes']} min"),
        ("Skips buying when", "the 7-, 15- and 30-day averages are stacked downward (a strong downtrend)"
                               + (f", or between {blocked['start']:02d}:00 and {blocked['end']:02d}:00 UTC" if blocked else "")),
    ]
    if extra:
        cap = extra.get("maximum_above_average_pct")
        rows.append(("Extra dip rule", "the confirming candle must close above the 30-day average"
                     + (f", by at most {pct(cap)}" if cap else "")))
    cb = entry.get("consolidation_breakout")
    if cb:
        span = cb["chart_minutes"] * cb["zone_bars"]
        wait = cb["confirmation_wait_minutes"]
        cbx = cb.get("exit") or {}
        rows.append(("Quiet-band breakout", f"after {hours(span)} inside a band no wider than {pct(cb['maximum_zone_pct'])}, "
                     f"a close above the band buys" + (f" if the price is still above it {wait} min later" if wait else " at the next minute")))
        if cbx:
            rows.append(("Breakout lots sell", f"stop −{pct(cbx['protective_stop_pct_from_entry_fill'])}, take profit from "
                         f"+{pct(cbx['activation_pct_from_entry_fill'])}, keep {pct(100 - cbx['giveback_of_open_profit_pct'])} of the best gain"))
    pb = entry.get("pullback_to_trend")
    if pb:
        rows.append(("Pullback", f"in a clean uptrend, after {hours(pb['dwell_minutes'])} under the {hours(pb['ema_minutes'])} line, "
                     "the first close back above it buys"))
    py = entry.get("pyramid_add")
    if py:
        rows.append(("Add-ons (optional, off by default)", f"while a lot is winning, add one more every +{pct(py['step_pct'])}, "
                     f"up to {py['maximum_adds']}"))
    rows += [
        ("Stop-loss", f"−{pct(exit_['protective_stop_pct_from_entry_fill'])} below the buy price, parked on Binance"),
        ("Takes profit", f"from +{pct(trail['activation_pct_from_entry_fill'])}: a trailing stop keeps "
                         f"{pct(100 - trail['giveback_of_open_profit_pct'])} of the best gain"),
    ]
    if trend:
        rows.append(("Trend ride", f"a lot bought in a clean uptrend is instead held while the price stays above the "
                     f"{hours(trend['ema_minutes'])} trend line, with a break-even floor once it is in profit"))
    costs = s["execution_model"]
    rows.append(("Costs assumed", f"{costs['bnb_fee_bps_per_side'] / 100:g}% fee per side with BNB "
                 f"({costs['usdt_fee_bps_per_side'] / 100:g}% without), plus {costs['slippage_bps_per_side'] / 100:g}% slippage"))
    table = "\n".join(f"| {label} | {text} |" for label, text in rows)
    return f"<a id=\"coin-{code.lower()}\"></a>\n\n### {name} ({code})\n\n| Rule | Setting |\n|---|---|\n{table}\n"


def main() -> None:
    sections = []
    for code, name in COINS:
        path = ROOT / "engine" / f"{code.lower()}_strategy.json"
        sections.append(coin_section(code, name, json.loads(path.read_text())))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(HEADER + "\n".join(sections) + FOOTER)
    print(f"wrote {OUT.relative_to(ROOT)}")


HEADER = """# Strategies

Z-Bot buys spot coins (no leverage, no shorting) and sells them again. Every coin follows the same building blocks
with its own settings. This page is generated from the strategy files the bot runs
(`engine/*_strategy.json`), so it always matches the code.

## Ways in (how it buys)

| | Way in | In one line | Default |
|---|---|---|---|
| **D** | <a id="dip"></a>**Dip** | The price dips into the coin's average while the trend allows it, and a green candle confirms. | On — the tested core |
| **Q** | <a id="breakout"></a>**Quiet-band breakout** | The price breaks above a quiet, narrow range it has been stuck in. | On — the tested core |
| **P** | <a id="pullback"></a>**Pullback** | In a clean uptrend, a short dip below the trend line, bought when it turns back up. | On (ETH only) |
| **+** | <a id="add-ons"></a>**Add-ons** | One more lot on a lot that is already winning, while the climb holds. | Off (SOL only) |
| **B** | <a id="buy-now"></a>**Buy now** | You buy one lot yourself from the dashboard. | — |

Every way in buys from the same **shared pot** of lots, first come first served. The dip and the breakout can be
switched off per coin, but they are the setup the coin was tested with.

## Ways out (how it sells)

| Way out | In one line |
|---|---|
| <a id="stop-loss"></a>**Stop-loss** | If the price falls a set % below the buy, the lot is sold. The stop sits on Binance itself from the first minute. |
| <a id="trailing-stop"></a>**Trailing stop** | Once a lot is up a set %, a stop follows the best price and sells after a set share of the gain is given back. |
| <a id="trend-ride"></a>**Trend ride** | A lot bought in a clean uptrend (7-day > 15-day > 30-day average) is held while the price stays above a trend line, and sold when a minute closes below it. |
| <a id="break-even-floor"></a>**Break-even floor** | When a trend-ride lot starts taking profit, its stop moves up to the buy price plus costs, so it can no longer close at a loss. |

How a lot will sell is fixed the moment it is bought.

## Per coin

"""

FOOTER = """
---

Settings were chosen from backtests on Binance 1-minute data and then checked on periods the search never saw. How
that was done, and what did not work, is in [Research](RESEARCH.md). Past results do not predict future ones.
"""


if __name__ == "__main__":
    main()
