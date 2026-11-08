"""Multiple coins (SOL + ETH) in one account.

Every position, trade and coin-scoped request carries its symbol; snapshots keep
per-coin cash and results in a `coins` JSON column. Existing rows belong to SOL.

Revision ID: 0012
Revises: 0011
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paper_positions", sa.Column("symbol", sa.String(24), nullable=False, server_default="SOLUSDT"))
    op.alter_column("paper_positions", "symbol", server_default=None)
    op.create_index("ix_paper_positions_symbol_status", "paper_positions", ["symbol", "status"])
    op.add_column("paper_trades", sa.Column("symbol", sa.String(24), nullable=False, server_default="SOLUSDT"))
    op.alter_column("paper_trades", "symbol", server_default=None)
    op.add_column("control_requests", sa.Column("symbol", sa.String(24), nullable=True))
    op.execute(
        """
        UPDATE control_requests SET symbol = COALESCE(details->>'symbol', 'SOLUSDT'),
            details = details || jsonb_build_object('symbol', COALESCE(details->>'symbol', 'SOLUSDT'))
        WHERE kind IN ('manual_buy','close_position','allocation')
        """
    )
    # The first initial deposit funded SOL.
    op.execute(
        """
        UPDATE control_requests SET symbol='SOLUSDT', details = details || '{"symbol":"SOLUSDT"}'::jsonb
        WHERE kind='initial_deposit'
        """
    )
    op.add_column("account_snapshots", sa.Column("coins", postgresql.JSONB(), nullable=False,
                                                 server_default=sa.text("'{}'::jsonb")))
    op.execute(
        """
        UPDATE account_snapshots SET coins = jsonb_build_object('SOLUSDT', jsonb_build_object(
            'cash_usd', coin_cash_usd::text, 'open_positions', open_positions,
            'open_position_value_usd', open_position_value_usd::text,
            'open_position_cost_usd', open_position_cost_usd::text,
            'realized_pnl_usd', realized_pnl_usd::text, 'unrealized_pnl_usd', unrealized_pnl_usd::text))
        """
    )


def downgrade() -> None:
    op.drop_column("account_snapshots", "coins")
    op.drop_column("control_requests", "symbol")
    op.drop_column("paper_trades", "symbol")
    op.drop_index("ix_paper_positions_symbol_status", "paper_positions")
    op.drop_column("paper_positions", "symbol")
