"""Each extra way in can be switched off, share the coin's lots, or hold lots of its own - and adds know their parent.

The core (the dip and Mode C) always runs on the coin's `lots`. The pullback and the pyramid add-on each carry a
mode - 'off', 'shared' or 'own' - and, when 'own', a number of lots only they may fill. `parent_position_id` ties a
pyramid add to the lot it was added to.

Revision ID: 0019
Revises: 0018
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODES = "'off','shared','own'"


def upgrade() -> None:
    for module, default in (("pullback", "shared"), ("pyramid", "off")):
        op.add_column("coin_allocations",
                      sa.Column(f"{module}_mode", sa.String(8), nullable=False, server_default=default))
        op.add_column("coin_allocations",
                      sa.Column(f"{module}_lots", sa.Integer(), nullable=False, server_default="0"))
        op.create_check_constraint(f"ck_coin_allocations_{module}_mode", "coin_allocations",
                                   f"{module}_mode IN ({MODES})")
        op.create_check_constraint(f"ck_coin_allocations_{module}_lots", "coin_allocations",
                                   f"{module}_lots >= 0")
    op.add_column("paper_positions", sa.Column("parent_position_id", sa.String(120), nullable=True))
    op.create_index("ix_paper_positions_parent", "paper_positions", ["parent_position_id"])


def downgrade() -> None:
    op.drop_index("ix_paper_positions_parent", "paper_positions")
    op.drop_column("paper_positions", "parent_position_id")
    for module in ("pullback", "pyramid"):
        op.drop_constraint(f"ck_coin_allocations_{module}_lots", "coin_allocations", type_="check")
        op.drop_constraint(f"ck_coin_allocations_{module}_mode", "coin_allocations", type_="check")
        op.drop_column("coin_allocations", f"{module}_lots")
        op.drop_column("coin_allocations", f"{module}_mode")
