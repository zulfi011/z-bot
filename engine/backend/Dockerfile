FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system zbot && useradd --system --gid zbot zbot

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY sol_strategy.json ./config/sol_strategy.json
COPY eth_strategy.json ./config/eth_strategy.json
COPY btc_strategy.json ./config/btc_strategy.json
COPY aave_strategy.json ./config/aave_strategy.json
COPY trx_strategy.json ./config/trx_strategy.json

RUN mkdir -p /app/secrets && chown -R zbot:zbot /app

EXPOSE 8000


FROM base AS test

COPY backend/requirements-dev.txt ./requirements-dev.txt
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY backend/tests ./tests

USER zbot
CMD ["python", "-m", "pytest", "-q"]


FROM base AS runtime

USER zbot
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
