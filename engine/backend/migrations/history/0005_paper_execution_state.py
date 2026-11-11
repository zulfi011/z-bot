"""Add restart-safe paper execution state.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paper_positions", sa.Column("raw_entry_price", sa.Numeric(24, 10), nullable=True))
    op.add_column("paper_positions", sa.Column("entry_fee_usd", sa.Numeric(20, 8), nullable=True))
    op.add_column(
        "paper_positions",
        sa.Column("bars_held", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("paper_positions", sa.Column("raw_exit_price", sa.Numeric(24, 10), nullable=True))
    op.add_column("paper_positions", sa.Column("exit_fee_usd", sa.Numeric(20, 8), nullable=True))

    # The execution engine is introduced before any paper positions can exist.
    # Keeping these nullable during the additive migration makes upgrades safe,
    # then the live engine always writes them for new rows.
    op.create_check_constraint(
        "ck_paper_positions_bars_held",
        "paper_positions",
        "bars_held >= 0",
    )
    op.create_index("ix_paper_orders_requested_at", "paper_orders", ["requested_at"])
    op.create_index("ix_account_snapshots_timestamp", "account_snapshots", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_account_snapshots_timestamp", table_name="account_snapshots")
    op.drop_index("ix_paper_orders_requested_at", table_name="paper_orders")
    op.drop_constraint("ck_paper_positions_bars_held", "paper_positions", type_="check")
    op.drop_column("paper_positions", "exit_fee_usd")
    op.drop_column("paper_positions", "raw_exit_price")
    op.drop_column("paper_positions", "bars_held")
    op.drop_column("paper_positions", "entry_fee_usd")
    op.drop_column("paper_positions", "raw_entry_price")
