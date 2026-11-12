"""One shared pot for every coin: a row per coin so each has an on/off switch.

The pot itself (number of lots and lot size) lives in the account settings. Coins no longer own money or lots, so
coin_allocations keeps only the switch and the extra-entry toggles; its lot columns are left in place but unused.
A coin that had money assigned keeps its switch as it was; a coin that never had any starts switched off.

Revision ID: 0022
Revises: 0021
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COINS = ("SOLUSDT", "ETHUSDT", "BTCUSDT", "AAVEUSDT", "TRXUSDT")


def upgrade() -> None:
    for symbol in COINS:
        op.execute(f"""
            INSERT INTO coin_allocations (symbol, lot_size_usd, lots, trading_enabled, updated_at)
            VALUES ('{symbol}', 100, 1, false, now())
            ON CONFLICT (symbol) DO NOTHING
        """)


def downgrade() -> None:
    pass
