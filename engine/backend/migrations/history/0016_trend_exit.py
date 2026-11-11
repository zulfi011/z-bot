"""Mode A exits: remember which lots ride the trend line and which are waiting to sell on it.

`trend_exit_active` is decided once, when the lot is opened: true when the market was in a clean uptrend
(7-day > 15-day > 30-day) and the strategy asks for the trend exit. `trend_exit_pending` marks a lot whose
minute closed below the EMA, so the sale lands on the next minute's open.

Revision ID: 0016
Revises: 0015
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paper_positions",
                  sa.Column("trend_exit_active", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("paper_positions",
                  sa.Column("trend_exit_pending", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("paper_positions", "trend_exit_pending")
    op.drop_column("paper_positions", "trend_exit_active")
