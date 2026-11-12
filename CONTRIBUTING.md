# Contributing to Z-Bot

Thanks for helping. Z-Bot trades real money for some of its users, so changes are held to a few firm rules. They are
all below; please read them before opening a pull request.

## Set up

You need Docker, and for the tests Python 3.12 and Node 22.

```bash
git clone https://github.com/zulfi011/z-bot.git
cd z-bot/engine
docker compose -f docker-compose.yml -f devtools/docker-compose.dev.yml up -d --build
```

The dashboard is on port 3000, the API docs on port 8000 (`/docs`), and the database on port 5432, all on your own
computer only. Everything runs in shadow mode: real prices, pretend money, nothing sent to Binance.

- **Try the order flow** without real money: add `-f devtools/docker-compose.fake-binance.yml` and set the pretend
  balances, e.g. `FAKE_USDT=1000 FAKE_BNB=0.1`. Then attach any made-up key in the dashboard.
- **Dashboard changes:** rebuild the web container (`docker compose ... up -d --build web`).
- **Never** point a development setup at a real Binance key you care about.

## Run the tests

These are the same checks CI runs on every pull request. Each block starts from the repository root.

```bash
# Engine: unit tests and database tests (needs the dev database above, on port 5432)
cd engine/backend
pip install -r requirements-dev.txt
INTEGRATION_DATABASE_URL=postgresql+psycopg://zbot:zbot_local@127.0.0.1:5432/zbot \
STRATEGY_CONFIG_PATH=$PWD/../sol_strategy.json ETH_STRATEGY_CONFIG_PATH=$PWD/../eth_strategy.json \
BTC_STRATEGY_CONFIG_PATH=$PWD/../btc_strategy.json AAVE_STRATEGY_CONFIG_PATH=$PWD/../aave_strategy.json \
TRX_STRATEGY_CONFIG_PATH=$PWD/../trx_strategy.json python -m pytest

```

```bash
# Dashboard: type check and build
cd engine/frontend && npm ci && npm run build
```

```bash
# Research (tests that need price data skip without it; see research/README.md)
pip install -r research/requirements-test.txt
(cd research/stage1 && python -m pytest) && (cd research/stage2 && python -m pytest)
```

## Project rules

### 1. Results are honest, or they are not published

- **Never claim or imply returns.** No "earn X%", no "profitable bot".
- **Every number comes from a report.** It must come from a research report in `research/stage2/results/` or from
  the live ledger, and it is quoted with its caveats: walk-forward or not, unseen period, sample size.
- **Public numbers are percentages,** never the dollar size of anyone's account.
- **A rule that changes trading must pass the honest walk-forward test**, not just look good on history:
  - choose its setting on the previous 6 months only
  - use it unchanged on the next 3
  - repeat over six quarters
  - beat simply not using it, in most quarters and not because of one lucky episode
- **Ideas found on one coin are re-run unchanged on the others.**
- **An idea that needs more money is compared with bigger lots for the same money.** Extra lots, or lots of its own,
  usually win only because they are bigger bets.
- **Failed ideas keep their reports.** Publishing what did not work is part of the project.

### 2. No built-in money

- **No dollar amounts are assumed anywhere:** not in defaults, strategy files, examples in the dashboard or preset
  buttons.
  - A new install starts with an empty pot, no daily loss limit, and no pretend balance until the user sets one.
  - The pot suggestion is computed from the user's own amount.
- **Strategy files hold rules, never money.**
  - Backtest notes in them are written as percentages of the money the test started with.
  - Lot sizes live in the user's settings.
- **The dashboard shows no backtest results.** Backtest numbers live in the research reports with their caveats, where
  they cannot be read as a promise.

### 3. Safety comes first

- **Shadow mode is the default.** Real orders need an attached Binance key and an explicit **Go live**.
- **Keys:**
  - Keys that can withdraw, or cannot trade spot, are refused.
  - A key is stored only in its own owner-only file, never in the database, logs, error messages or API responses.
    The dashboard shows only its first and last four characters.
- **Every live lot parks its stop-loss on Binance** the moment it is bought. If parking fails, the dashboard shows a
  red alert.
- **The dashboard listens only on the machine it runs on** (`127.0.0.1`). On a server it is reached through a tunnel
  or private network, never an open port, and a control key protects every button that trades or changes money.
- **Spot only.** No leverage, short selling, futures, withdrawals or transfers. Pull requests adding any of these will
  be declined.

### 4. Each coin starts with the setup it was tested with

- **Coins start switched off;** the user switches on the ones they want.
- **The tested core is on by default:** the Dip and the Quiet-band breakout.
  - Switching either off asks first and explains why: the coin's tested results assume both are on.
- **Optional ways in switch straight away, without a warning:** the Pullback (ETH) and Add-ons (SOL).
- **A new way in or option ships off** unless it passed the walk-forward test as part of that coin's default setup.
- **Default settings come from the strategy files and the research behind them,** not from preference.
- The full list for users is in [Using the dashboard](docs/guide/USER-GUIDE.md#the-tested-defaults).

### 5. One plain vocabulary

Use the same words in code, comments, tests, docs and the dashboard:

| Ways in | Ways out |
|---|---|
| Dip, Quiet-band breakout (or "breakout"), Pullback, Add-ons, Buy now | Stop-loss, Trailing stop, Trend ride, Break-even floor |

Other terms:
- **Shared pot:** one set of lots shared by every coin that is on.
- **Lot:** one buy from the pot.
- **Shadow mode / Live:** the two trading modes.

Internal codes and history names (old mode letters, "paper") do not appear in new code or text.

### 6. The dashboard

- **Every card has an (i)** that explains it in one or two plain sentences.
- **No sample or dummy data ships in the app.** A new install shows empty states that say what will appear, and when.
- **Zero is neutral:** `$0.00` is never shown in red or green.
- **Warnings appear only when they apply to the user's setup.** For example, Binance fee (BNB) warnings show only once
  a Binance account is attached.
- **Anything that trades or changes money confirms first,** and says what will happen: what a close would return,
  what switching a coin off does to its open lots.
- **Explanations link to the guide** ("Learn more") instead of growing long inside the app.
- **It works on a phone,** and it shows no personal details.

### 7. Docs

- **The guide in `docs/guide/` is the only copy.** GitHub and the website both show these files.
- **`docs/guide/STRATEGIES.md` is generated** from the strategy files: regenerate it, never edit it by hand.
- **Nothing private in any public file:** no keys, `.env` contents, server addresses, personal paths or local machine
  links.

## Changing a strategy

A coin's strategy is one file, `engine/<coin>_strategy.json`. It holds:
- the ways in (the average and zone, the confirmation, the breakout and pullback rules)
- the ways out (stop-loss, trailing stop, trend ride, break-even floor)
- blocked hours
- the fee and slippage model
- notes on where each number came from

The bot reads it at start; changing it changes how that coin trades.

1. **Research it first.**
   - Add a script under `research/stage2/scripts/` that tests the change.
   - Write its report to `research/stage2/results/<idea>_v1/REPORT.md`: the full-history result, the honest
     walk-forward result (rule 1), the other coins re-run unchanged, and the bigger-lots comparison if it needs more
     money.
   - State the verdict plainly, including "rejected".
   - Get the data with `python research/download_data.py`.
2. **Only if it passes, edit the strategy file.** Change the numbers and update the note beside them so it points to
   your report, in percentages.
3. **Regenerate the strategies page:** `python engine/devtools/build_strategies_doc.py`
4. **Update the tests.** `engine/backend/tests/test_strategy.py` pins every deployed value on purpose, so a change
   there is visible in review. Change the pinned value and say why in the pull request.
5. **Run all the tests,** and run the bot in shadow mode with the change.
6. **Open a pull request** that links the report and quotes its walk-forward result.

**A new coin** cannot be added by a strategy file alone yet: the engine has a fixed list of coins. Making coins
plug-ins is planned. Until then, please open an issue first to discuss it.

**Database changes** go in a new migration in `engine/backend/migrations/versions/`. See the README there; existing
installs upgrade through it, and fresh installs load `schema.sql` and then run it.

## Pull requests

- **Keep each pull request to one change,** and describe what it changes and why.
- **CI must pass:** engine tests including database tests, dashboard build, research tests, Docker build.
- **For anything that touches trading:** say how you tested it in shadow mode, and link the research.
- **Bugs and ideas** go to GitHub Issues. Security problems do not; see [SECURITY.md](SECURITY.md).

By contributing you agree that your contribution is licensed under the project's [AGPL-3.0](LICENSE) licence.
