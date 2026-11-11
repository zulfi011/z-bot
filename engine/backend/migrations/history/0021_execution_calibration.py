"""Record decision-to-fill execution quality for continuous backtest calibration.

Revision ID: 0021
Revises: 0020
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_observations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("position_id", sa.String(120), nullable=True),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("best_bid", sa.Numeric(24, 10), nullable=True),
        sa.Column("best_ask", sa.Numeric(24, 10), nullable=True),
        sa.Column("expected_next_open", sa.Numeric(24, 10), nullable=True),
        sa.Column("actual_average_fill", sa.Numeric(24, 10), nullable=True),
        sa.Column("order_latency_ms", sa.Numeric(20, 3), nullable=True),
        sa.Column("fee_asset", sa.String(16), nullable=True),
        sa.Column("fee_usd", sa.Numeric(20, 8), nullable=True),
        sa.Column("fee_rate_bps", sa.Numeric(16, 6), nullable=True),
        sa.Column("price_impact_bps", sa.Numeric(16, 6), nullable=True),
        sa.Column("next_open_slippage_bps", sa.Numeric(16, 6), nullable=True),
        sa.Column("exchange_order_id", sa.String(64), nullable=True),
        sa.Column("client_order_id", sa.String(64), nullable=True),
        sa.Column("recovered_retry", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("side IN ('buy','sell')", name="ck_execution_observations_side"),
    )
    op.create_index("ix_execution_observations_symbol_completed", "execution_observations",
                    ["symbol", "completed_at"])
    op.create_index("ix_execution_observations_client_order", "execution_observations", ["client_order_id"])


def downgrade() -> None:
    op.drop_table("execution_observations")
