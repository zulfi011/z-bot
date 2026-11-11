"""The dip and the quiet-band breakout get their own on/off switch, like the pullback and the add-ons.

Both start on for every coin (and for coins added later), so nothing changes until someone switches one off.

Revision ID: 0023
Revises: 0022
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for module in ("dip", "breakout"):
        op.add_column("coin_allocations",
                      sa.Column(f"{module}_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    for module in ("dip", "breakout"):
        op.drop_column("coin_allocations", f"{module}_enabled")
