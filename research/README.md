# Z-Bot research

How every rule the bot trades with was found, tested and, much more often, rejected. For the short version in
plain words, read the guide's [Research page](../docs/guide/RESEARCH.md). This folder is the full record: the code,
every experiment's report and its tables.

| Path | What is in it |
|---|---|
| [`INDEX.md`](INDEX.md) | One line per experiment, grouped by coin, with its verdict |
| `foundations/` | Price data: downloading, resampling, daily averages, and the first touch-and-bounce studies |
| `backtests/src/backtesting/` | The shared backtest engine: entries, exits, fees, slippage, several lots |
| `backtests/scripts/` | One script per experiment |
| `backtests/results/<experiment>/` | Its `REPORT.md` and tables |
| `backtests/experiments/` | Larger experiments with their own engine, e.g. the canonical ETH baseline |
| `download_data.py` | Gets the price data the scripts need |
| `build_index.py` | Rebuilds `INDEX.md` |

Older reports call these two folders "stage 1" and "stage 2", the names they had while the research was done.

## The honest test

A rule that looks good on the history it was tuned on proves little: try enough rules and one fits the noise. So
every idea also had to pass a walk-forward test: choose its setting on the previous 6 months only, use it unchanged
on the next 3, repeat over six quarters, and compare with simply not using the idea. Ideas found on one coin were
re-run unchanged on the others, and an idea that needs more money is always compared with bigger lots for the same
money. Most ideas failed; their reports are kept here on purpose.

## About the numbers

- **Dollar figures are backtest units, not anyone's money.** Most experiments simulate one account of $300 in
  3 lots of $100 (some use 5 lots, or a growing account, as each report says), so that results are comparable
  across coins and ideas. Read them as relative: "+$30 on $300" is +10%.
- Fees, slippage and the BNB fee discount are included. Averages only use completed daily closes, so no backtest sees
  a price it could not have known.
- The history runs from September 2024 to September 2026. It is two years of one market; a rule that passed can still
  stop working. Not financial advice.

## Reproduce a result

You need Python 3.11+ and about 1 GB of disk.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r research/backtests/requirements.txt
python research/download_data.py            # Binance's public 1-minute archives, checksum-verified (~1 min per coin)
```

Then, from `research/backtests/`:

```bash
python -m pytest                            # the backtest engine's tests, incl. rebuilding the frozen ETH baseline
python scripts/<experiment>.py              # re-run one experiment; it writes to results/<experiment>/
```

Each report names the script that made it. Without the price data the tests that need it are skipped, and the
reports and tables can still be read as they are.

Some scripts replay history through the trading engine itself (`../engine/backend`), so research and the live bot
share one implementation of every rule. `backtests/scripts/stage3_legacy/` is a frozen copy of the first engine, kept so
the earliest results can still be reproduced exactly.
