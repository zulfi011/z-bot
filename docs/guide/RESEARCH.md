# Research

Every rule Z-Bot trades with had to survive the same test, and most ideas did not. This page explains the test and
lists what was tried. Each experiment has its own report in
[`research/backtests/results/<experiment>/REPORT.md`](../../research/backtests/results/) with the full numbers and caveats:
see the [index of every experiment](../../research/INDEX.md), and the [research README](../../research/README.md) to
reproduce one.

## The data

- Binance spot, **1-minute candles**, October 2024 to September 2026, for every coin studied.
- Fees, slippage and the BNB fee discount are included in every result.
- Only completed daily closes are used for averages, so a backtest never sees a price it could not have known.

## The honest test

Finding a rule that looks good on past data is easy: try enough rules and one will fit the noise. So a good-looking
result is not enough. Every idea also had to pass an **honest walk-forward test**:

1. Pick the best setting using only the previous **6 months**.
2. Use it, unchanged and unseen, on the **next 3 months**.
3. Repeat across **six quarters**, and compare with simply not using the idea.

An idea is kept only if it beats "doing nothing" this way, in most quarters, and not because of one lucky episode.
Ideas found on one coin were also re-run **unchanged** on the other coins. And an idea that needs more money (more
lots, extra lots for itself) is always compared with simply using **bigger lots for the same money**.

## What survived

| Idea | Where | What it does |
|---|---|---|
| Dip into the average, confirmed by a green candle | every coin | The core way in |
| Skip buying in a strong downtrend | every coin | Avoids catching falling prices |
| Each coin's own average length, zone, stop and trail | SOL, BTC, AAVE, TRX re-checked | Every deployed setting was best or within noise |
| Quiet-band breakout | SOL, ETH, AAVE, TRX | Catches moves that never return to the average |
| Pullback in an uptrend | ETH only | Passed on ETH with a small edge; failed on the other four coins |
| Trend ride with a break-even floor | SOL, ETH | Lets a big move run; the floor won in 6 of 6 walk-forward windows on ETH |
| A later profit-taking start on AAVE | AAVE | The first AAVE change to pass the honest test |
| One shared pot of lots | all coins | Shared lots beat reserving money per coin or per idea |

## What did not survive

| Idea | Tried on | Why it was dropped |
|---|---|---|
| Volume filters (skip busy or quiet hours) | all five | No rule reliably beat trading without it in the walk-forward test |
| Fear & Greed index | all five | Lost on every coin; good-looking rules were single episodes |
| Futures data (funding, open interest, long/short) | all five | Lost or noise on every coin |
| Market breadth (how many coins are rising) | all five | Lost; one coin's lead failed on the others |
| Volatility-sized (ATR) stops | all five | Fixed percentages did as well or better |
| Bitcoin-based filters | ETH, SOL, TRX, AAVE | Raised win rates by buying late, and earned less |
| Selling half early (scale-out) | all five | Less profit, and no smaller drawdowns |
| Holding through the regime / catching up to Bitcoin | ETH, SOL | Lost to doing nothing |
| Buying the capitulation | all five | Never beat the same money in ordinary lots |
| A ladder of buys lower down | all five | Much deeper drawdowns |
| Adaptive averages (length changes with the market) | all five | None beat each coin's fixed average |
| Donchian breakouts | ETH, SOL | The gain came from one window only |
| Pyramiding (add-ons) | all five | Not better than bigger lots for the same money; kept only as an optional switch on SOL, off by default |
| Separate money for the breakout | ETH, TRX, AAVE | Lost to sharing the same lots |
| Compounding plan (more and bigger lots as the wallet grows) | portfolio | Its gain was just bigger bets; used only as a sizing suggestion |
| Cooldowns, streak and daily-loss caps, equal-risk sizing | ETH | Failed the honest test |

## What the data says

- **The average losing trade never changes.** On every coin, whatever the market mood, futures positioning, breadth or
  volume, the average loss is the same size (ETH about −4.5%, SOL −2.2%, TRX −3.3%, BTC −3.1%, AAVE −4.1%). That is
  the stop-loss doing its job. Filters change how *often* a coin loses a little, never how *much*.
- **Coins behave differently.** BTC buys best when the market is hot; SOL buys worst then. That is why a rule found on
  one coin almost never worked on another.
- **Single-coin "wins" are usually one episode.** A rule that looks great on the full history often owes it all to one
  stretch of a few weeks. The walk-forward test is what catches that.

Source of these three points: [five_coin_data_filters_summary](../../research/backtests/results/five_coin_data_filters_summary/REPORT.md).

## Caveats

Backtests are history. The test periods are about two years, the walk-forward windows are short, and a strategy
that passed can still stop working. The live results page shows how the surviving rules do with real money, losing
months included. Not financial advice.
