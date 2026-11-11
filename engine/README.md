# Z-Bot engine

The bot itself: a worker that trades, an API, a PostgreSQL database and the React dashboard, run together with
Docker Compose. For what it does and how to use it, start with the [main README](../README.md) and the
[guide](../docs/guide/).

## Run

```bash
docker compose up -d --build
```

The dashboard is on port 3000. Without a Binance account everything runs in shadow mode. For the API docs (port 8000, `/docs`) and direct database access, add `-f devtools/docker-compose.dev.yml`. `docker compose down` keeps the database; `docker compose down -v` deletes it.

To try the order flow against a pretend Binance wallet (real prices, fake money):

```bash
docker compose -f docker-compose.yml -f devtools/docker-compose.fake-binance.yml up -d --build
```

## Layout

| Path | What it is |
|---|---|
| `backend/app/worker.py` | The loop: prices in, signals, orders, health checks |
| `backend/app/domain/` | Strategy logic without I/O: signals, exits, breakout, pullback, add-ons |
| `backend/app/services/` | Binance client and exchange, execution, monitoring, market data |
| `backend/app/api/routes.py` | The dashboard's API and controls |
| `backend/migrations/` | Database schema (Alembic); runs automatically on start |
| `frontend/src/` | The dashboard (React + Vite) |
| `*_strategy.json` | One strategy file per coin: the rules and settings the bot runs |
| `devtools/` | Fake Binance and the strategies-page generator |
| `deploy/` | Server setup and the optional public-stats exporter |

More detail: [ARCHITECTURE.md](ARCHITECTURE.md).

## Tests

```bash
docker build --target test -t z-bot-backend-test -f backend/Dockerfile .
docker run --rm z-bot-backend-test
```

The database tests (a whole lot walked through buy → stop on Binance → trailing stop → sell, against a throwaway
database built by the real migrations) need the compose database running and skip themselves without it. Start it
with the dev file (`-f devtools/docker-compose.dev.yml`), then:

```bash
docker compose run --rm -u root -v "$PWD/backend:/src" -v "$PWD:/app/config" -w /src -e HOME=/tmp api \
  sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

## After changing a strategy file

Regenerate the strategies page so the docs match the bot:

```bash
python devtools/build_strategies_doc.py
```

(run from the repository root as `python engine/devtools/build_strategies_doc.py`).
