"""Per-coin trading switch: a paused coin opens no new lots until resumed.

Revision ID: 0013
Revises: 0012
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KINDS = "'initial_deposit','deposit','withdrawal','bnb_purchase','manual_buy','close_position','allocation'"


def upgrade() -> None:
    op.add_column("coin_allocations", sa.Column("trading_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.drop_constraint("ck_control_requests_kind", "control_requests", type_="check")
    op.create_check_constraint("ck_control_requests_kind", "control_requests",
                               f"kind IN ({KINDS},'coin_pause','coin_resume')")


def downgrade() -> None:
    op.execute("DELETE FROM control_requests WHERE kind IN ('coin_pause','coin_resume')")
    op.drop_constraint("ck_control_requests_kind", "control_requests", type_="check")
    op.create_check_constraint("ck_control_requests_kind", "control_requests", f"kind IN ({KINDS})")
    op.drop_column("coin_allocations", "trading_enabled")
