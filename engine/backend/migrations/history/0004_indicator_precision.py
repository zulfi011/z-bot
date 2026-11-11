"""Preserve full PostgreSQL numeric precision for strategy averages.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AVERAGE_COLUMNS = ("average_7d", "average_15d", "average_30d")


def upgrade() -> None:
    for table in ("daily_averages", "candles_3m"):
        for column in AVERAGE_COLUMNS:
            op.alter_column(table, column, type_=sa.Numeric(), existing_nullable=True)
    op.alter_column("touch_episodes", "average_value", type_=sa.Numeric(), existing_nullable=False)


def downgrade() -> None:
    for table in ("daily_averages", "candles_3m"):
        for column in AVERAGE_COLUMNS:
            op.alter_column(table, column, type_=sa.Numeric(24, 10), existing_nullable=True)
    op.alter_column(
        "touch_episodes", "average_value", type_=sa.Numeric(24, 10), existing_nullable=False
    )
