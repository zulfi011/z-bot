# Security

Z-Bot can hold a Binance API key and trade with real money, so security reports are taken seriously.

## Reporting a vulnerability

Please **do not open a public issue.** Use GitHub's private reporting instead: on the repository, open the
**Security** tab and choose **Report a vulnerability**. Only the maintainer sees the report.

Please include what you found, how to reproduce it, and what an attacker could do with it. You will get a reply as
soon as possible; a fix comes before any public detail.

## In scope

- Anything that could expose a user's Binance key or secret: storage, logs, error messages, API responses, backups,
  the public stats export.
- Anything that could place, change or cancel an order without the user's intent, or trade in shadow mode.
- Anything that lets someone else reach or control a dashboard that is set up as documented (bound to the local
  machine, control key on servers).
- A way to make the bot accept a key that can withdraw, or to leave a live lot without its stop on Binance unnoticed.

Out of scope: setups that ignore the documented safety steps (for example a dashboard port opened to the internet
without a control key), and problems in Binance itself.

## How the bot is built to be safe

The design is described in the guide's [Safety page](docs/guide/SAFETY.md):

- keys that can withdraw are refused
- keys are kept in an owner-only file and never in the database
- every live lot parks its stop-loss on Binance
- the dashboard is private by default
- spot only: no leverage, no withdrawals

## Supported versions

Only the latest version on `main` gets security fixes. Update with `git pull` and
`docker compose up -d --build` (see [Run it on a server](docs/guide/DEPLOY.md#updating)).
