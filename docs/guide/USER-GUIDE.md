# Using the dashboard

The dashboard has a **Main** page and one page per coin; the coin bar under the top bar switches
between them. Every card has an **(i)**: hover or tap it for a one- or two-sentence explanation. Everything works on
a phone too.

## Top bar

| Item | What it does |
|---|---|
| Status dot | Green when prices are arriving. Red if the dashboard cannot reach the bot. |
| ↻ | Refresh now. The page also refreshes itself every 15 seconds. |
| ☀ / ☾ | Light or dark theme. |
| **Results ↗** | Opens the public results: every trade of a simulated account at Binance prices, after fees, updated daily. The guide is in the same site's menu, and cards on the coin pages link to the matching part of it. |
| Padlock | Only on a server with a control key: shows whether this device can use the buttons. See [The control key](#the-control-key). |
| **Attach Binance account** | Connects your own Binance account (see [Attaching Binance](#attaching-binance)). After that it shows a small "Binance" chip. |

Scrolling down hides the top bar; the coin bar stays. Scrolling up brings it back.

## Main page

| Card | What it shows | What you can do |
|---|---|---|
| **Shadow wallet** (or **Binance wallet** when live) | The money the bot trades with, and its profit | **Set starting amount** / **Change** (shadow mode) |
| **Trading switch** | The mode (Shadow, Live, Stopped), the daily loss limit, the most allowed in trades | **Go live**, **Shadow mode**, **Stop all trading**, **Edit** each limit |
| **Shared pot** | Lots × lot size, lots in use, the next buy, and each coin with its on/off switch | **Edit pot**, switch coins on or off |
| **Coin leaderboard** | Coins ranked by what they made in the chosen period | Change the period; tap a coin to open its page |
| **Open lots** | One small card per open lot: profit, prices, its stop and where profit-taking starts | **Close** a lot (shows what closing would return first) |
| **Wallet over time** | The wallet's history | Hover or touch to read any moment; zoom with the + / − buttons |
| **Recent trades** | Closed trades: how it was bought → how it was sold, and the result | |
| **Your requests** | Every Buy now and Close you asked for, and what happened | Cancel a request that is still waiting |
| **System health** | Prices, signals, Binance account, Binance's trading API, trading mode | |

## Coin page

| Card | What it shows |
|---|---|
| **Main card** | Price, 24-hour change, the coin's profit, its average and entry zone. A **Switch on** button if the coin is off. |
| **What the strategy sees now** | One verdict line ("Watching", "Paused until 12:00 UTC", "About to buy"), the checks every buy needs, and one card per way in showing its steps: ✓ done, ✕ blocking, ○ not yet, ● happening now. |
| **Price chart** | Candles or a line with the average, entry zone and other lines. Trades show as a solid line where a lot was bought and a dashed line where it was sold (green win, red loss): hover or tap one for the details. Chips under the chart switch each layer on or off; the strip under the chart moves and zooms. |
| **Open lots** | Each open lot of this coin in full detail. |
| **Shared pot** | This coin's view of the pot: which lots are in use and by whom. **Buy now**, **Edit pot**, **Switch off**. |
| **How it buys** | Every way in with its own switch. |
| **How it sells** | How the next lot would take profit and limit a loss, as a small ladder. |
| **Activity** | Every signal and what was decided, plus trades and orders. |
| **Performance** | This coin's closed trades: win rate, best, worst, costs. |
| **This coin's rules** | The exact rules this bot runs for the coin, read from its strategy file, with a link to the coin's section on the [Strategies](STRATEGIES.md) page. |

## The tested defaults

Each coin starts with the setup it was tested with:

- The **Dip** and the **Quiet-band breakout** are **on**. You can switch either off in **How it buys**, but the bot
  asks first and explains why: the coin's tested results assume they are on, and with one off it trades less and
  its results are no longer the tested ones.
- The **Pullback** (ETH) is on and **Add-ons** (SOL) are off. These two are optional and switch straight away.
- Coins themselves start **off**: switch on the ones you want in the **Shared pot** card.

## The control key

**On your own computer you can skip this section.** There is no control key, no lock and nothing to type: every
button works, because only your computer can open the dashboard.

**On a server you need one.** A server is a computer other people could reach, so the dashboard needs a password
before anyone can trade with your Binance account. That password is the control key.

| | Own computer | Server |
|---|---|---|
| Control key | none | one long random key |
| Lock icon in the top bar | not shown | shown |
| Viewing the dashboard | works | works, no key needed |
| Buttons that trade or change money | work | work once this device is unlocked |

### Where the key comes from

- **With the server setup script** (`engine/deploy/vps/setup.sh`, see [Deploy](DEPLOY.md)): the script creates the
  key for you, saves it in the server's settings file `engine/.env` as `STRATEGY_EDIT_TOKEN=...`, and prints it once
  at the end as "Your dashboard control key". Save it in your password manager.
- **Setting up a server another way:** add it yourself. In `engine/.env` write a long random value, for example the
  output of `openssl rand -hex 16`, after `STRATEGY_EDIT_TOKEN=`, then run `docker compose up -d` in the `engine`
  folder.

Attaching a Binance account does **not** create a control key. They are separate: the Binance key lets the bot trade,
the control key decides who may press the buttons.

### Using it

1. Press the padlock in the top bar, or any button that needs it (such as **Buy now** or **Go live**).
2. Type the control key and press **Unlock this device**.
3. That device stays unlocked for 30 days. The key itself is not saved in the browser.
4. To lock a device again (for example a shared computer), press the open padlock and choose **Lock this device**.

After 5 wrong keys in 15 minutes the dashboard makes you wait before trying again.

### Lost it, or want a new one

On the server:

1. Print the current key: `grep STRATEGY_EDIT_TOKEN /opt/z-bot/engine/.env`
2. Or set a new one: edit that line in `engine/.env`, then run `cd /opt/z-bot/engine && docker compose up -d`.
   (`docker compose restart` does not read the new value; `up -d` does.)

A new key locks **every** device at once; unlock each one again with the new key. This is also how to shut out a
device you no longer trust.

To remove the lock completely, leave `STRATEGY_EDIT_TOKEN=` empty and run `docker compose up -d`. Only do that if the
dashboard cannot be reached by anyone but you.

## Attaching Binance

1. Press **Attach Binance account** in the top bar.
2. Follow the steps in the popup: create an API key on Binance, give it **reading and spot trading only** (never
   withdrawals), and, on a server, restrict it to the server's fixed IP address. The popup shows your IP and checks
   that Binance's trading API can be reached from where the bot runs.
3. Paste the API key and secret. The bot checks the key with Binance and **refuses keys that can withdraw**.
4. Trading stays in **Shadow** until you press **Go live**.

The key is kept only on that machine, never in the database, and is never shown again. See [Safety](SAFETY.md).

### Optional: pay fees with BNB

Binance charges 0.1% of each buy and sell. If you switch on **Use BNB to pay for fees** in your Binance account and
keep a few dollars of BNB there, Binance takes the fee in BNB at a discount (0.075% instead of 0.1%). Z-Bot supports
this: it records each fee in the coin Binance charged it in, and counts the BNB as part of your account's value. Top
the BNB up now and then, or Binance falls back to the normal fee. Shadow mode always uses the normal 0.1% fee, so it
never needs BNB.
