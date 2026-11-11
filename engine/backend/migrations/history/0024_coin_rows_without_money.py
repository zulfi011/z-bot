"""A coin's row no longer holds money: its old lot size and lot count go.

Since the shared pot (0022) every coin draws on the pot's lots, so `coin_allocations.lot_size_usd` and `lots` were
written but never read. The row keeps only the coin's on/off switch and its ways-in switches.

Revision ID: 0024
Revises: 0023
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_coin_allocations_positive", "coin_allocations", type_="check")
    op.drop_column("coin_allocations", "lot_size_usd")
    op.drop_column("coin_allocations", "lots")


def downgrade() -> None:
    # Placeholders only: nothing reads these since the shared pot.
    op.add_column("coin_allocations", sa.Column("lot_size_usd", sa.Numeric(20, 2), nullable=False, server_default="10"))
    op.add_column("coin_allocations", sa.Column("lots", sa.SmallInteger(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_coin_allocations_positive", "coin_allocations", "lot_size_usd > 0 AND lots > 0")
