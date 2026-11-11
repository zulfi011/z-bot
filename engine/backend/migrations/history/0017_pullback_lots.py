"""Pullback lots: a coin's allocation can reserve slots for the pullback entry, apart from its core lots.

`lots` stays the core's slots (dip + Mode C + buy-now). `pullback_lots` are separate slots only the pullback entry
may fill, so neither can take the other's place. Both are the same lot size and draw on the one Binance wallet;
the coin's allowance is lot size x (lots + pullback_lots).

Revision ID: 0017
Revises: 0016
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("coin_allocations",
                  sa.Column("pullback_lots", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_coin_allocations_pullback_lots", "coin_allocations", "pullback_lots >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_coin_allocations_pullback_lots", "coin_allocations", type_="check")
    op.drop_column("coin_allocations", "pullback_lots")
