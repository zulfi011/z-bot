from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Z-Bot"
    app_version: str = "3.0.0"
    database_url: str = "postgresql+psycopg://paperbot:paperbot_local@db:5432/papertrading"
    strategy_config_path: Path = Path("/app/config/sol_strategy.json")
    eth_strategy_config_path: Path = Path("/app/config/eth_strategy.json")
    btc_strategy_config_path: Path = Path("/app/config/btc_strategy.json")
    aave_strategy_config_path: Path = Path("/app/config/aave_strategy.json")
    trx_strategy_config_path: Path = Path("/app/config/trx_strategy.json")
    strategy_edit_token: str = ""
    log_level: str = "INFO"
    binance_rest_url: str = "https://data-api.binance.vision"
    # Account and order calls (needs the API key); market data keeps using the public host above.
    binance_api_url: str = "https://api.binance.com"
    binance_api_key: str = ""
    binance_api_secret: str = ""
    # A key attached from the dashboard is kept here (see app/core/credentials.py).
    binance_credentials_path: Path = Path("/app/secrets/binance.json")
    binance_recv_window_ms: int = 5000
    binance_websocket_url: str = "wss://data-stream.binance.vision:443/ws"
    market_data_backfill_days: int = 32
    fee_asset_backfill_days: int = 2
    market_data_reconnect_seconds: int = 5
    market_data_stale_after_seconds: int = 180

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value: object) -> object:
        return normalize_database_url(value) if isinstance(value, str) else value


def normalize_database_url(value: str) -> str:
    """Accept the usual ways a connection URI gets pasted into a hosting panel.

    Strips spaces/quotes, a pasted "DATABASE_URL=" prefix, and maps postgres:// / postgresql:// to the psycopg driver.
    """
    value = value.strip().strip("\"'").strip()
    if value.upper().startswith("DATABASE_URL="):
        value = value.split("=", 1)[1].strip().strip("\"'").strip()
    for scheme in ("postgresql://", "postgres://"):
        if value.startswith(scheme):
            return "postgresql+psycopg://" + value[len(scheme):]
    return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
