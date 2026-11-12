# Stage 3 Baseline — Live Strategies Replayed on History

## What this is

The benchmark every new strategy must beat. It replays the three live paper strategies exactly as
`stage3_papertrading/*_frozen_strategy.json` define them, using Stage 3's own signal engine and exit
code (imported, not re-implemented): 2 lots × 25% of equity, −4% stop, trail from +4% with 10%
giveback, 24-hour maximum hold, 10 bps fee + 2 bps slippage per side, $100 per coin.

Validation: replaying the live database candles reproduces every live paper trade (times, prices,
exit reasons, PnL) and the SOL account value to the cent; the SOL history reproduces the Stage 2
frozen result ($108.33, −12.16% drawdown).

Periods start 2024-10-01, the first day all 7/15/30-day completed-close averages exist. Earlier and
later each restart at $100. Lots still open at a period end are marked at the last close.

## Full history (2024-10-01 → 2026-07-31)

| Coin | Trades | Wins / losses | Win rate | Final $100 | Return | Profit factor | Avg win / loss | Max drawdown | Trail / stop / time exits | Fees + slippage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SOLUSDT | 152 | 82 / 70 | 53.9% | $108.33 | +8.33% | 1.18 | +2.64% / -2.59% | -12.16% | 42 / 30 / 80 | $9.26 |
| ETHUSDT | 121 | 58 / 63 | 47.9% | $88.45 | -11.55% | 0.70 | +1.90% / -2.45% | -15.20% | 18 / 26 / 77 | $6.77 |
| BTCUSDT | 77 | 42 / 35 | 54.5% | $97.41 | -2.59% | 0.85 | +1.41% / -1.97% | -10.93% | 8 / 9 / 60 | $4.54 |

## Earlier (2024-10-01 → 2025-08-31)

| Coin | Trades | Wins / losses | Win rate | Final $100 | Return | Profit factor | Avg win / loss | Max drawdown | Trail / stop / time exits | Fees + slippage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SOLUSDT | 82 | 41 / 41 | 50.0% | $103.76 | +3.76% | 1.15 | +3.03% / -2.62% | -12.16% | 27 / 19 / 36 | $4.71 |
| ETHUSDT | 71 | 29 / 42 | 40.8% | $90.49 | -9.51% | 0.66 | +2.72% / -2.79% | -12.64% | 16 / 22 / 33 | $4.07 |
| BTCUSDT | 37 | 18 / 19 | 48.6% | $99.91 | -0.09% | 0.99 | +1.91% / -1.80% | -7.14% | 6 / 4 / 27 | $2.23 |

## Later (2025-09-01 → 2026-07-31)

| Coin | Trades | Wins / losses | Win rate | Final $100 | Return | Profit factor | Avg win / loss | Max drawdown | Trail / stop / time exits | Fees + slippage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SOLUSDT | 70 | 41 / 29 | 58.6% | $104.41 | +4.41% | 1.23 | +2.24% / -2.53% | -5.83% | 15 / 11 / 44 | $4.38 |
| ETHUSDT | 50 | 29 / 21 | 58.0% | $97.74 | -2.26% | 0.85 | +1.09% / -1.75% | -6.62% | 2 / 4 / 44 | $2.98 |
| BTCUSDT | 40 | 24 / 16 | 60.0% | $97.49 | -2.51% | 0.70 | +1.04% / -2.17% | -7.04% | 2 / 5 / 33 | $2.31 |

## Unseen holdout (2026-08-01 → 2026-09-09, SOL only — ETH/BTC not downloaded)

| Coin | Trades | Wins / losses | Win rate | Final $100 | Return | Profit factor | Avg win / loss | Max drawdown | Trail / stop / time exits | Fees + slippage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SOLUSDT | 1 | 1 / 0 | 100.0% | $99.64 | -0.36% | nan | +0.91% / +nan% | -1.25% | 0 / 0 / 1 | $0.12 |

## How to compare a new strategy

Load a Stage 3 JSON, change fields, and call `stage3_replay.generate_signals` +
`replay_execution` + `summarize` over the same periods. A candidate should be chosen using the
earlier period only, then judged once on later + holdout against the rows above.
