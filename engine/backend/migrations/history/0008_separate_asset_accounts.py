"""Split paper account snapshots and recovery state by asset.

Revision ID: 0008
Revises: 0007
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_snapshots",
        sa.Column("symbol", sa.String(24), nullable=True),
    )
    # All snapshots predating ETH paper trading belong to the original SOL account.
    op.execute("UPDATE account_snapshots SET symbol='SOLUSDT' WHERE symbol IS NULL")
    op.alter_column("account_snapshots", "symbol", nullable=False)
    op.drop_constraint("account_snapshots_pkey", "account_snapshots", type_="primary")
    op.create_primary_key(
        "pk_account_snapshots_symbol_timestamp",
        "account_snapshots",
        ["symbol", "timestamp"],
    )
    op.execute(
        """
        INSERT INTO engine_state (key, value, updated_at)
        SELECT 'paper_execution:SOLUSDT', value || '{"symbol":"SOLUSDT"}'::jsonb, updated_at
        FROM engine_state WHERE key='paper_execution'
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute("DELETE FROM engine_state WHERE key='paper_execution'")


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO engine_state (key, value, updated_at)
        SELECT 'paper_execution', value - 'symbol', updated_at
        FROM engine_state WHERE key='paper_execution:SOLUSDT'
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute("DELETE FROM engine_state WHERE key LIKE 'paper_execution:%'")
    op.execute("DELETE FROM account_snapshots WHERE symbol != 'SOLUSDT'")
    op.drop_constraint("pk_account_snapshots_symbol_timestamp", "account_snapshots", type_="primary")
    op.create_primary_key("account_snapshots_pkey", "account_snapshots", ["timestamp"])
    op.drop_column("account_snapshots", "symbol")
