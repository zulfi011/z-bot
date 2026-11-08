# Live Bot — SOL, ETH, BTC, AAVE, TRX

Trades five coin strategies on your own Binance spot account. The money never leaves Binance: this app decides,
places the orders, parks a stop-loss on Binance for every lot, and shows what it did. Coins are listed in
`backend/app/core/strategy.py` (`COIN_CONFIGS`).

**Three modes** (Main page, control key required):

| Mode | What happens |
|---|---|
| **Stop all** (`off`) | No new lots. Open lots keep their stop-loss on Binance and are still closed by the rules. |
| **Shadow** | Every order is worked out and written to the ledger, but nothing is sent to Binance. This is how a change is rehearsed. |
| **Live** | Orders go to Binance: market buy, protective stop, market sell. |

## Strategies

| | SOL | ETH | BTC | AAVE | TRX |
|---|---|---|---|---|---|
| Candles | 3-minute | 5-minute | 5-minute | 3-minute | 1-minute |
| Average | 12-day (completed UTC daily closes) | 7-day | 5-day | 10-day | 12-day |
| Entry zone | ±0.5% | ±0.5% | ±0.2% | ±0.1% | ±0.1% |
| Entry | rises into the zone from below, green candle confirms within 30 min | same | same, and the green candle must close above the 30-day average | same as SOL | same as BTC, but no more than 10% above the 30-day average |
| Skips | strong downtrends (7 < 15 < 30-day), entries 06:00–12:00 UTC | same | same | same | strong downtrends only (trades all hours) |
| Stop | −2% | −3.5% | −3% | −4% | −4% |
| Trailing stop | starts at +1.251%, gives back 12% of peak profit | starts at +1.315%, gives back 30% | starts at +1.257%, gives back 14% | starts at +1.75%, gives back 20% | starts at +1.245%, gives back 10% |
| Backtest (Oct 2024 – Jul 2026, $100 lots) | 225 trades, +$47.14 USDT fees / ~+$64 BNB | 246 trades, +$134.05 / +$145.95 | 189 trades, +$71.92 / +$81.41 (fragile: unseen −$13, walk-forward −$20) | 250 trades, +$77.23 / +$96.70 (only 10-day works) | 148 trades, +$147.41 / +$154.88 (weakening: earlier +$109, later +$38, unseen −$1.58; walk-forward +$25.64) |

- **One shared pot.** On the Main page you set the number of lots and the money per lot once, and switch each coin
  on or off. Every coin that is on shares those lots, first come first served, so money never sits idle waiting for
  one coin. If losses leave less than a full lot, the last buy uses whatever USDT is left. A coin that is off is
  skipped. Tested growth plan: start 3 × $100, add a lot per +$100 of wallet up to 5, then +$20 per lot per +$100
  (`stage2_backtesting/results/compounding_full_v1/REPORT.md`); you change it by hand.
- **The break-even floor.** The moment a Mode A lot arms (reaches its trail level), its protective stop is lifted to
  the buy price plus 0.19% — both sides' fee and slippage — and the order parked on Binance is moved with it. A lot
  that has proved itself and then comes all the way back exits level (`break_even`) instead of slightly negative.
  It never caps a winner: a trending lot does not return to its entry. Measured on ETH: win rate 76.9% → 85.0%,
  walk-forward +$12 on $300, better in 6 of 6 windows (`stage2_backtesting/scripts/eth_line_gap.py`, which also
  rejects the two variants people reach for first — arming earlier, and selling before the line is touched).
- **Every way in shares the coin's lots, first come first served.** There are no reserved lots: the dip, Mode C,
  the pullback and any pyramid adds all take whichever lot is free. Each extra way in is simply **on or off**, set
  from the coin page's *Ways in* card. The core (the dip and Mode C) is always on. Research on all five coins found
  reserved lots lose to the same money spread across shared ones.
- **SOL** has a **pyramid add-on**: while a lot is winning, another lot is added at +0.5% steps above its buy
  price, up to two, as long as price is above the trend line and the hour is not blocked. An add has no exit of
  its own: it parks the *parent's* stop price and is sold in the same minute the parent is (`parent_exit`). SOL
  turns quickly, and an add left behind gave the profit back in the research. It starts switched **off** and
  shares SOL's lots when switched on.
- ETH had one too (+1% steps, up to three) and it was **removed**, not just switched off. Over Oct 2024 – Jul 2026
  on 5 × $100 shared lots it added $73 across 172 adds at a 54.1% win rate, while pulling the whole strategy's
  win rate from 85.4% to 76.6%, deepening the worst mark-to-market dip from −9.66% to −14.06%, and taking 28 lots
  the dip would otherwise have used.
- ETH has a third way in, the pullback entry: in an uptrend (7 > 15 > 30-day), at least 3 hours of 1-minute closes
  under the 24-hour EMA, then the first close back above it. It shares ETH's lots with the dip and Mode C, first come
  first served, like every other entry. (Reserved pullback lots were built and removed: they only pay once the core
  is full at 5 lots.) The live rule matches the backtest entry for entry
  (`stage2_backtesting/scripts/verify_pullback_parity.py`).
- Coins share one pot. A lot is bought at its full size when the pot can cover it; otherwise the coin that buys
  next uses whatever free USDT is left (Binance's own ~$5 minimum order still applies).
- No time limit on trades. Fees are whatever Binance charges (0.10% per side, 0.075% if you let Binance take them
  from BNB); every trade records them separately.
- The decision code reproduces the Stage 2 replay to the cent
  (`stage2_backtesting/scripts/verify_stage3_v2_parity.py <SYMBOL>`). Ranking of all researched coins:
  `stage2_backtesting/results/coin_comparison_v2/REPORT.md`.

The Main page ranks the coins in a live **leaderboard** (return on each coin's money or dollar profit, over
24 h / 7 d / 30 d / all) with a P&L sparkline per coin. The top card shows the wallet value, trading profit, today's
result, free USDT, open lots, win rate and trades won and lost.

## Connecting Binance

1. Binance → API Management → create a key with **Reading** and **Spot & Margin Trading** only. Never enable
   withdrawals.
2. Restrict it to trusted IPs and enter your server's fixed IP, and whitelist the five symbols.
3. Put the key in the server's `.env` — never in git, never in chat:

   ```
   BINANCE_API_KEY=...
   BINANCE_API_SECRET=...
   ```

4. Restart (`docker compose up -d`), then open the Main page. **System health** shows "Binance connected" and the
   top card shows your real wallet value and free USDT.
5. Leave it in **Shadow** for a while and read the ledger. Switch to **Live** when it looks right.

## Start locally

Docker Desktop must be running. From this directory:

```bash
cp .env.example .env
docker compose up --build
```

- Dashboard: <http://localhost:3000> (Main plus one page per coin; works on phones)
- API docs: <http://localhost:8000/docs>
- Readiness: <http://localhost:8000/api/v1/health/ready>

Without Binance keys everything still runs: prices, signals and shadow orders. `docker compose down` keeps the
database; `docker compose down -v` deletes it.

### Try it with a pretend wallet

`devtools/fake_binance.py` stands in for Binance with real prices and a pretend $300 wallet, so every screen - money,
buying, stops, closing, profit - can be tried with money in the account and none at risk. Local machine only:

```bash
docker compose -f docker-compose.yml -f devtools/docker-compose.fake-binance.yml up -d --build
```

Go back to the normal setup with `docker compose up -d --build --remove-orphans`.

## Controls

Viewing is open; anything that trades or changes money needs the device **unlocked**. Tap the padlock in the header
(or any control) and enter the control key (`STRATEGY_EDIT_TOKEN`; locally `z-bot-local-edit`) once. The server
gives that browser a signed, HTTP-only session cookie valid for 30 days; the key is never stored in the browser. The
padlock also locks the device again. Changing `STRATEGY_EDIT_TOKEN` on the server locks every device at once. Five
wrong keys from one address lock unlocking for 15 minutes. Scripts can still send the key in an `X-Control-Key`
header.

| Control | What it does |
|---|---|
| Mode | Stop all / Shadow / Live (above). Stop all takes effect on the next minute. |
| Shared pot | Number of lots × money per lot, shared by every coin that is on. Applies immediately; lots already open keep their size. |
| Coin on/off | Each coin's switch on the Main page. Off skips its signals (and can close its open lots); applies immediately. |
| Daily loss limit | When today's closed trades add up to a loss this big, no new lots open until tomorrow (UTC). |
| Maximum open value | A ceiling on the total value of open lots across all coins. |
| Buy now (per coin) | Opens that coin's next lot on the next minute, outside the strategy's timing. |
| Close | On the Main page and every coin page. A popup shows what selling now would return with Close / Cancel; Close cancels the parked stop and sells at market. |
| Pause / Resume (per coin) | Pausing stops new lots (signals and Buy now are skipped). If it has open lots you choose: keep them running until their stop, or close them all now. |

## Safety

- A stop-loss order sits on Binance for every open lot, so a crash still sells if this app is offline. The trailing
  stop is managed by the bot; if it triggers, the bot cancels the parked stop and sells at market.
- The bot only ever sells what it bought: quantities are clamped to the real free balance for that coin.
- Binance's own rules are checked before anything is sent (minimum order value, quantity step, price tick).
- Every request and reply is written to `exchange_events`, so you can see exactly what was sent.
- Alerts cover stale prices and gaps per coin, execution lag, the daily loss limit, a lot with no stop order on
  Binance, low BNB, and shadow/off mode (so you are never surprised that nothing trades).

## Tests

```bash
docker build --target test -t z-bot-backend-test -f backend/Dockerfile .
docker run --rm z-bot-backend-test
```

The end-to-end test walks a whole lot through buy → stop parked on Binance → trailing stop → sell, plus the case
where Binance's own stop fills, against a throwaway database built by the real migrations (Binance itself is faked
at the HTTP layer). It needs the compose database running, and skips itself when there is none:

```bash
docker compose run --rm -u root -v "$PWD/backend:/src" -v "$PWD:/app/config" -w /src -e HOME=/tmp api \
  sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q tests/test_live_integration.py"
```

## Deployment

Your own small server with a fixed IP (AWS Lightsail, Frankfurt): see [`deploy/vps/README.md`](deploy/vps/README.md).
Updates: `git pull && docker compose up -d --build` on the server; migrations run automatically before the API starts.
