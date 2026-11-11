"""Add durable derived candles and daily averages for signal generation.

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_averages",
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_through", sa.Date(), nullable=False),
        sa.Column("average_7d", sa.Numeric(24, 10), nullable=True),
        sa.Column("average_15d", sa.Numeric(24, 10), nullable=True),
        sa.Column("average_30d", sa.Numeric(24, 10), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "effective_at"),
    )
    op.create_table(
        "candles_3m",
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(24, 10), nullable=False),
        sa.Column("high", sa.Numeric(24, 10), nullable=False),
        sa.Column("low", sa.Numeric(24, 10), nullable=False),
        sa.Column("close", sa.Numeric(24, 10), nullable=False),
        sa.Column("volume", sa.Numeric(32, 12), nullable=False),
        sa.Column("average_7d", sa.Numeric(24, 10), nullable=True),
        sa.Column("average_15d", sa.Numeric(24, 10), nullable=True),
        sa.Column("average_30d", sa.Numeric(24, 10), nullable=True),
        sa.Column("derived_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "open_time"),
        sa.CheckConstraint("low <= open AND low <= close AND high >= open AND high >= close", name="ck_candles_3m_ohlc"),
        sa.CheckConstraint("volume >= 0", name="ck_candles_3m_volume"),
    )
    op.create_index("ix_candles_3m_open_time", "candles_3m", ["open_time"])


def downgrade() -> None:
    op.drop_table("candles_3m")
    op.drop_table("daily_averages")
