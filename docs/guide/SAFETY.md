# Safety

Z-Bot handles real money only when you attach a Binance account and press **Go live**. These are the safeguards.

## Your Binance key

- **Trade only, never withdraw.** When you attach a key, the bot asks Binance what the key may do and refuses it if
  withdrawals are enabled, or if it cannot trade spot.
- **Checked before it is kept.** A key Binance rejects is not saved.
- **Kept on your machine only.** The key is written to one small file readable only by the bot, in its own Docker
  volume. It is never put in the database, so database backups and the public stats export can never contain it.
- **Never shown again.** The dashboard shows only the first and last four characters. Error messages never repeat
  what you typed.
- **On a server, lock it to the server's IP.** Binance then refuses the key from anywhere else.

## Every position is protected

- The moment a lot is bought in live mode, its **stop-loss is parked on Binance** as a real order. If the bot, the
  server or the internet connection goes down, Binance still sells at the stop.
- If parking the stop ever fails, the lot is recorded anyway and the dashboard shows a red alert that it is
  unprotected; the bot still sells it at its own stop while it runs.

## Limits you set

- **Daily loss limit:** when the day's closed trades have lost this much, no new lot opens until the next UTC day.
- **Most in trades:** a ceiling on the money in open lots at once.
- **Shared pot:** the number and size of lots caps how much is ever in the market.
- **Stop all trading:** buys nothing new; open lots keep their stops and can still be sold.

## Keeping the dashboard private

- By default the dashboard **only listens on the computer it runs on** (`127.0.0.1`). Nobody else on your network or
  the internet can open it.
- On a server, reach it through an SSH tunnel or a private network such as Tailscale. **Do not open its port to the
  internet.**
- On a server, also set a control key (`STRATEGY_EDIT_TOKEN` in `engine/.env`). The dashboard then asks for it once per
  device before any button that trades or changes money works.

## What the bot does not do

No leverage, no short selling, no futures, no withdrawals, no transfers. Spot buys and sells only.

## Reporting a problem

If you find a security problem, please open a private report through GitHub's "Report a vulnerability" on the
repository rather than a public issue.
