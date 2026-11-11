"""Persist complete account and execution-cost attribution.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_snapshots",
        sa.Column("open_position_cost_usd", sa.Numeric(20, 8), nullable=False, server_default="0"),
    )
    op.add_column(
        "account_snapshots",
        sa.Column("fees_paid_usd", sa.Numeric(20, 8), nullable=False, server_default="0"),
    )
    op.add_column(
        "account_snapshots",
        sa.Column("slippage_paid_usd", sa.Numeric(20, 8), nullable=False, server_default="0"),
    )
    op.add_column(
        "account_snapshots",
        sa.Column("total_pnl_usd", sa.Numeric(20, 8), nullable=False, server_default="0"),
    )
    op.add_column(
        "account_snapshots",
        sa.Column("return_pct", sa.Numeric(16, 8), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE account_snapshots AS snapshot SET
            open_position_cost_usd = COALESCE((
                SELECT sum(position.allocation_usd)
                FROM paper_positions AS position
                WHERE position.entry_time < snapshot.timestamp
                  AND (position.exit_time IS NULL OR position.exit_time > snapshot.timestamp)
            ), 0),
            fees_paid_usd = COALESCE((
                SELECT sum(paper_orders.fee_usd)
                FROM paper_orders WHERE requested_at <= snapshot.timestamp
            ), 0),
            slippage_paid_usd = COALESCE((
                SELECT sum(paper_orders.slippage_usd)
                FROM paper_orders WHERE requested_at <= snapshot.timestamp
            ), 0),
            total_pnl_usd = total_equity_usd - 100,
            return_pct = (total_equity_usd / 100 - 1) * 100
        """
    )
    op.create_check_constraint(
        "ck_account_costs_nonnegative",
        "account_snapshots",
        "open_position_cost_usd >= 0 AND fees_paid_usd >= 0 AND slippage_paid_usd >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_account_costs_nonnegative", "account_snapshots", type_="check")
    op.drop_column("account_snapshots", "return_pct")
    op.drop_column("account_snapshots", "total_pnl_usd")
    op.drop_column("account_snapshots", "slippage_paid_usd")
    op.drop_column("account_snapshots", "fees_paid_usd")
    op.drop_column("account_snapshots", "open_position_cost_usd")
