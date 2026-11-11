"""Add fields needed to validate Binance market data.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candles_1m", sa.Column("close_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("candles_1m", sa.Column("quote_volume", sa.Numeric(32, 12), nullable=True))
    op.add_column("candles_1m", sa.Column("trade_count", sa.Integer(), nullable=True))
    op.add_column("candles_1m", sa.Column("source_event_time", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_candles_volume_nonnegative", "candles_1m", "volume >= 0")
    op.create_check_constraint(
        "ck_candles_quote_volume_nonnegative", "candles_1m", "quote_volume IS NULL OR quote_volume >= 0"
    )
    op.create_check_constraint(
        "ck_candles_trade_count_nonnegative", "candles_1m", "trade_count IS NULL OR trade_count >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_candles_trade_count_nonnegative", "candles_1m", type_="check")
    op.drop_constraint("ck_candles_quote_volume_nonnegative", "candles_1m", type_="check")
    op.drop_constraint("ck_candles_volume_nonnegative", "candles_1m", type_="check")
    op.drop_column("candles_1m", "source_event_time")
    op.drop_column("candles_1m", "trade_count")
    op.drop_column("candles_1m", "quote_volume")
    op.drop_column("candles_1m", "close_time")
