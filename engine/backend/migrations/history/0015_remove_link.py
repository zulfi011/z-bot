"""LINK is no longer traded: remove its allocation so its share returns to the shared pot.

Refuses to run while a LINK lot is still open. Once LINK leaves the strategy list the bot stops managing its lots,
so an open one would be left with only its stop order on Binance. Close it first, then deploy. LINK's closed trades
stay in the history.

Revision ID: 0015
Revises: 0014
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    open_lots = connection.execute(
        sa.text("SELECT count(*) FROM paper_positions WHERE symbol='LINKUSDT' AND status='open'")
    ).scalar_one()
    if open_lots:
        raise RuntimeError(f"LINK still has {open_lots} open lot(s). Close them on the dashboard, then deploy again.")
    op.execute("DELETE FROM control_requests WHERE symbol='LINKUSDT' AND status='pending'")
    op.execute("DELETE FROM coin_allocations WHERE symbol='LINKUSDT'")
    op.execute("DELETE FROM monitoring_alerts WHERE alert_key LIKE '%LINKUSDT%'")


def downgrade() -> None:
    # Nothing to restore: an allocation can be set again from the dashboard if LINK ever comes back.
    pass
