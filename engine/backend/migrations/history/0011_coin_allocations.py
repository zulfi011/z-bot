"""Per-coin money allocation (lot size × lots), unallocated cash and trailing-start times.

Revision ID: 0011
Revises: 0010
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coin_allocations",
        sa.Column("symbol", sa.String(24), primary_key=True),
        sa.Column("lot_size_usd", sa.Numeric(20, 2), nullable=False),
        sa.Column("lots", sa.SmallInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("lot_size_usd > 0 AND lots > 0", name="ck_coin_allocations_positive"),
    )
    op.add_column("account_snapshots", sa.Column("unallocated_usd", sa.Numeric(20, 8), nullable=False, server_default="0"))
    op.add_column("account_snapshots", sa.Column("coin_cash_usd", sa.Numeric(20, 8), nullable=False, server_default="0"))
    op.execute("UPDATE account_snapshots SET coin_cash_usd = cash_usd")
    op.create_check_constraint("ck_snapshot_cash_split", "account_snapshots",
                               "unallocated_usd >= 0 AND coin_cash_usd >= 0")
    op.add_column("paper_positions", sa.Column("trailing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("ck_control_requests_kind", "control_requests", type_="check")
    op.create_check_constraint(
        "ck_control_requests_kind", "control_requests",
        "kind IN ('initial_deposit','deposit','withdrawal','bnb_purchase','manual_buy','close_position','allocation')",
    )
    # Existing accounts: everything already in the ledger belongs to SOL at the default 3 × $100.
    op.execute(
        """
        INSERT INTO control_requests (request_id, kind, amount_usd, status, requested_at, processed_at, details)
        SELECT 'initial-allocation', 'allocation', flows.net, 'applied', flows.first_at, flows.first_at,
               jsonb_build_object('symbol', 'SOLUSDT', 'lot_size_usd', '100.00', 'lots', 3,
                                  'transfer_usd', flows.net::text, 'note', 'Existing SOL capital at migration')
        FROM (
            SELECT COALESCE(sum(CASE WHEN kind IN ('initial_deposit','deposit') THEN amount_usd
                                     WHEN kind IN ('withdrawal','bnb_purchase') THEN -amount_usd END), 0) AS net,
                   min(requested_at) AS first_at
            FROM control_requests WHERE status='applied'
        ) AS flows
        WHERE EXISTS (SELECT 1 FROM account_snapshots)
        """
    )
    op.execute(
        """
        INSERT INTO coin_allocations (symbol, lot_size_usd, lots, request_id, updated_at)
        SELECT 'SOLUSDT', 100, 3, 'initial-allocation', now() WHERE EXISTS (SELECT 1 FROM account_snapshots)
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM control_requests WHERE kind='allocation'")
    op.drop_constraint("ck_control_requests_kind", "control_requests", type_="check")
    op.create_check_constraint(
        "ck_control_requests_kind", "control_requests",
        "kind IN ('initial_deposit','deposit','withdrawal','bnb_purchase','manual_buy','close_position')",
    )
    op.drop_column("paper_positions", "trailing_started_at")
    op.drop_constraint("ck_snapshot_cash_split", "account_snapshots", type_="check")
    op.drop_column("account_snapshots", "coin_cash_usd")
    op.drop_column("account_snapshots", "unallocated_usd")
    op.drop_table("coin_allocations")
