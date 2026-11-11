"""Every entry shares one set of lots again: the dip, Mode C and the pullback all draw on the coin's `lots`.

0017 gave the pullback entry slots of its own. That only pays once the core is full (5 lots on ETH); below that
the reserved slots sit idle while the dip waits, so the column goes and the pullback competes for the same lots
as everything else. The split is in the git history if a bigger account ever wants it back.

Revision ID: 0018
Revises: 0017
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The lots stay assigned to the coin; only the reservation for one entry goes.
    op.execute("UPDATE coin_allocations SET lots = lots + pullback_lots WHERE pullback_lots > 0")
    op.drop_constraint("ck_coin_allocations_pullback_lots", "coin_allocations", type_="check")
    op.drop_column("coin_allocations", "pullback_lots")


def downgrade() -> None:
    op.add_column("coin_allocations",
                  sa.Column("pullback_lots", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_coin_allocations_pullback_lots", "coin_allocations", "pullback_lots >= 0")
