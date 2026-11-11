"""Add persistent runtime strategy configurations.

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategy_configurations",
        sa.Column("symbol", sa.String(24), primary_key=True),
        sa.Column("strategy_id", sa.String(120), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_strategy_configuration_revision"),
    )


def downgrade() -> None:
    op.drop_table("strategy_configurations")
