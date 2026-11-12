# How it works

Z-Bot is one program that runs on your own computer or server. It watches Binance prices minute by minute, decides
when each coin is worth buying, and manages every position until it is sold.

## The loop, every minute

1. **Prices come in.** The bot keeps a month of 1-minute prices for each coin, straight from Binance's public data.
   No account is needed for this.
2. **Each coin checks its rules.** A coin has a few ways in (the dip, the quiet-band breakout, and on some coins a
   pullback or add-ons). Each one looks for its own signal. See [Strategies](STRATEGIES.md).
3. **A signal buys one lot.** If a lot is free in the shared pot and nothing blocks the buy (the coin is switched on,
   the daily loss limit is not reached, the time window is open), the bot buys one lot.
4. **A stop-loss is parked straight away.** In live mode it is a real stop order on Binance, so the position is
   protected even if the bot or the server goes down.
5. **The lot is sold** by its stop-loss, its trailing stop, or, in a clean uptrend, when the price closes below the
   trend line. How it will sell is fixed when it is bought.

The dashboard shows each step as it happens: what every coin is waiting for, the open lots, and every closed trade.

## Shadow mode and live mode

| | Shadow (default) | Live |
|---|---|---|
| Prices and signals | real | real |
| Orders | worked out and recorded, **nothing sent** | sent to your Binance account |
| Money | a pretend starting amount you choose | your Binance spot wallet |
| Needs a Binance account | no | yes, with an API key that can trade but not withdraw |

Shadow mode is the way to learn how the bot behaves before risking anything. Switching to live needs an attached
Binance account and an explicit **Go live**.

## The shared pot

All coins share one pot of equal **lots** (for example 5 lots). Whichever coin signals first takes the next free lot,
so money never sits idle waiting for one coin. When every lot is open, new signals are skipped until one closes.

Until you size the pot yourself, it follows a growth plan for the money you have: 3 equal lots for small amounts,
up to 5 lots, then bigger lots as the money grows. You can change it at any time with **Edit pot**.

## What runs where

| Part | What it does |
|---|---|
| Worker | Downloads prices, runs every coin's rules once a minute, places and manages orders |
| API | Serves the dashboard and takes your actions (Buy now, Close, switches) |
| Database | Keeps prices, signals, lots, trades and settings (PostgreSQL) |
| Dashboard | The web page you use to watch and control the bot |

All four start together with `docker compose up`. Technical detail: [engine/ARCHITECTURE.md](../../engine/ARCHITECTURE.md).
