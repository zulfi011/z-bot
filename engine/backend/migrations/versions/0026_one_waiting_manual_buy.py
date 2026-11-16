"""Only one waiting Buy now per coin, enforced by the database.

The API checked for a waiting request and then added one. Two taps arriving together could both pass the check and
queue two buys, and the engine would then buy two lots. A unique index on waiting manual buys makes the second insert
fail, which the API answers with the same 409 as before. Any duplicates already waiting are rejected first (the
oldest one per coin is kept), so the index can be built.

Revision ID: 0026
Revises: 0025
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "uq_control_requests_one_waiting_manual_buy"


def upgrade() -> None:
    op.execute("""
        UPDATE control_requests SET status='rejected', reason='Duplicate buy-now request', processed_at=now()
        WHERE kind='manual_buy' AND status='pending' AND request_id NOT IN (
            SELECT DISTINCT ON (symbol) request_id FROM control_requests
            WHERE kind='manual_buy' AND status='pending' ORDER BY symbol, requested_at
        )
    """)
    op.execute(f"CREATE UNIQUE INDEX {INDEX} ON control_requests (symbol) WHERE kind='manual_buy' AND status='pending'")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
