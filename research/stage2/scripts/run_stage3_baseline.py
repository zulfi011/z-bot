"""Replay the live Stage 3 SOL/ETH/BTC strategies over the full history.

This is the fixed benchmark every new strategy is compared against. The
strategy JSON files are read from live_bot and never modified.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import stage3_replay as replay

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "stage3_baseline_v1"
RESULT_DIR = ROOT / "results" / EXPERIMENT_ID
DATA_DIR = ROOT / "data" / EXPERIMENT_ID

UTC = "UTC"
# 2024-10-01 is the first day all 7/15/30-day completed-close averages exist.
PERIODS = {
    "full": (pd.Timestamp("2024-10-01", tz=UTC), pd.Timestamp("2026-08-01", tz=UTC)),
    "earlier": (pd.Timestamp("2024-10-01", tz=UTC), pd.Timestamp("2025-09-01", tz=UTC)),
    "later": (pd.Timestamp("2025-09-01", tz=UTC), pd.Timestamp("2026-08-01", tz=UTC)),
}
HOLDOUT = (pd.Timestamp("2026-08-01", tz=UTC), pd.Timestamp("2026-09-10", tz=UTC))


def run_symbol(symbol: str) -> tuple[list[dict], dict[str, pd.DataFrame]]:
    strategy = json.loads(replay.STRATEGY_FILES[symbol].read_text())
    minutes = int(strategy["market"]["signal_timeframe"].removesuffix("m"))
    rows, ledgers = [], {}
    datasets = [("history", False)]
    if any(replay.HOLDOUT_DIR.glob(f"{symbol}-1m-*.zip")):
        datasets.append(("holdout", True))
    for dataset, include_holdout in datasets:
        raw = replay.load_raw(symbol, include_holdout=include_holdout)
        averages = replay.daily_averages(raw)
        candles = replay.signal_candles(raw, minutes, averages)
        signals, diagnostics = replay.generate_signals(strategy, candles)
        periods = PERIODS if dataset == "history" else {"holdout": HOLDOUT}
        for period, (start, end) in periods.items():
            result = replay.replay_execution(strategy, raw, signals, start, end)
            summary = replay.summarize(result)
            rows.append({"symbol": symbol, "strategy_id": strategy["strategy_id"],
                         "period": period, **summary,
                         **({f"diag_{k}": v for k, v in diagnostics.items()} if period == "full" else {})})
            ledgers[period] = result.trades
            print(f"{symbol} {period}: {summary['trades']} trades, "
                  f"${summary['final_equity_usd']:.2f}, DD {summary['max_drawdown_pct']:.2f}%", flush=True)
    return rows, ledgers


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for symbol in replay.STRATEGY_FILES:
        symbol_rows, ledgers = run_symbol(symbol)
        rows.extend(symbol_rows)
        for period, ledger in ledgers.items():
            ledger.to_csv(DATA_DIR / f"{symbol}_{period}_trades.csv", index=False)
    summary = pd.DataFrame(rows)
    summary.to_csv(RESULT_DIR / "baseline_summary.csv", index=False)
    (RESULT_DIR / "baseline_summary.json").write_text(
        json.dumps(rows, indent=2, default=str) + "\n"
    )
    (RESULT_DIR / "REPORT.md").write_text(build_report(summary))


def build_report(summary: pd.DataFrame) -> str:
    def table(period: str) -> str:
        lines = [
            "| Coin | Trades | Wins / losses | Win rate | Final $100 | Return | Profit factor "
            "| Avg win / loss | Max drawdown | Trail / stop / time exits | Fees + slippage |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in summary[summary.period == period].itertuples(index=False):
            lines.append(
                f"| {row.symbol} | {row.trades} | {row.wins} / {row.losses} | {row.win_rate_pct:.1f}% "
                f"| ${row.final_equity_usd:.2f} | {row.return_pct:+.2f}% | {row.profit_factor:.2f} "
                f"| {row.average_winner_pct:+.2f}% / {row.average_loser_pct:+.2f}% "
                f"| {row.max_drawdown_pct:.2f}% | {row.trailing_exits} / {row.stop_exits} / {row.time_exits} "
                f"| ${row.fees_usd + row.slippage_usd:.2f} |"
            )
        return "\n".join(lines)

    return f"""# Stage 3 Baseline — Live Strategies Replayed on History

## What this is

The benchmark every new strategy must beat. It replays the three live paper strategies exactly as
`live_bot/*_frozen_strategy.json` define them, using Stage 3's own signal engine and exit
code (imported, not re-implemented): 2 lots × 25% of equity, −4% stop, trail from +4% with 10%
giveback, 24-hour maximum hold, 10 bps fee + 2 bps slippage per side, $100 per coin.

Validation: replaying the live database candles reproduces every live paper trade (times, prices,
exit reasons, PnL) and the SOL account value to the cent; the SOL history reproduces the Stage 2
frozen result ($108.33, −12.16% drawdown).

Periods start 2024-10-01, the first day all 7/15/30-day completed-close averages exist. Earlier and
later each restart at $100. Lots still open at a period end are marked at the last close.

## Full history (2024-10-01 → 2026-07-31)

{table("full")}

## Earlier (2024-10-01 → 2025-08-31)

{table("earlier")}

## Later (2025-09-01 → 2026-07-31)

{table("later")}

## Unseen holdout (2026-08-01 → 2026-09-09, SOL only — ETH/BTC not downloaded)

{table("holdout")}

## How to compare a new strategy

Load a Stage 3 JSON, change fields, and call `stage3_replay.generate_signals` +
`replay_execution` + `summarize` over the same periods. A candidate should be chosen using the
earlier period only, then judged once on later + holdout against the rows above.
"""


if __name__ == "__main__":
    main()
