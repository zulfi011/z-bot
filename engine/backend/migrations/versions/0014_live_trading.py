"""Switch from simulated money to the real Binance spot wallet.

Money now lives in Binance: there is no internal cash ledger, no deposits, withdrawals or simulated BNB purchases.
Positions keep the Binance order ids so the bot can find, protect and reconcile them. Paper history is removed
because it measured play money.

Revision ID: 0014
Revises: 0013
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Paper history goes; market data and daily averages stay.
    for table in ("paper_trades", "paper_orders", "paper_positions", "signals", "touch_episodes",
                  "control_requests", "coin_allocations", "account_snapshots"):
        op.execute(f"DELETE FROM {table}")
    op.execute("DELETE FROM monitoring_alerts")
    op.execute("DELETE FROM system_events")
    op.execute("DELETE FROM engine_state WHERE key <> 'account_settings' AND key NOT LIKE 'market_data:%'")

    # 2. Orders the bot placed on Binance.
    op.add_column("paper_positions", sa.Column("entry_order_id", sa.String(64), nullable=True))
    op.add_column("paper_positions", sa.Column("stop_order_id", sa.String(64), nullable=True))
    op.add_column("paper_positions", sa.Column("stop_price", sa.Numeric(24, 10), nullable=True))
    op.add_column("paper_positions", sa.Column("exit_order_id", sa.String(64), nullable=True))
    op.add_column("paper_positions", sa.Column("quantity_sold", sa.Numeric(28, 12), nullable=True))
    op.add_column("paper_orders", sa.Column("exchange_order_id", sa.String(64), nullable=True))
    op.add_column("paper_orders", sa.Column("client_order_id", sa.String(64), nullable=True))
    op.add_column("paper_orders", sa.Column("order_type", sa.String(24), nullable=True))
    op.add_column("paper_orders", sa.Column("fee_asset_quantity", sa.Numeric(28, 12), nullable=True))
    op.create_index("ix_paper_orders_client_order_id", "paper_orders", ["client_order_id"], unique=True,
                    postgresql_where=sa.text("client_order_id IS NOT NULL"))

    # 3. Requests: money moves are gone; a global trading switch arrives.
    op.drop_constraint("ck_control_requests_kind", "control_requests", type_="check")
    op.create_check_constraint(
        "ck_control_requests_kind", "control_requests",
        "kind IN ('allocation','manual_buy','close_position','coin_pause','coin_resume','trading_mode')")

    # 4. Snapshots describe the real wallet instead of a simulated cash box.
    for column in ("cash_usd", "unallocated_usd", "coin_cash_usd", "net_deposits_usd", "performance_equity_usd",
                   "performance_peak_usd", "return_pct", "bnb_price_usd", "bnb_balance", "bnb_value_usd"):
        op.execute(f"ALTER TABLE account_snapshots DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE account_snapshots DROP CONSTRAINT IF EXISTS ck_snapshot_spot_limits")
    op.execute("ALTER TABLE account_snapshots DROP CONSTRAINT IF EXISTS ck_snapshot_cash_split")
    op.add_column("account_snapshots", sa.Column("usdt_free", sa.Numeric(20, 8), nullable=False, server_default="0"))
    op.add_column("account_snapshots", sa.Column("usdt_locked", sa.Numeric(20, 8), nullable=False, server_default="0"))
    op.add_column("account_snapshots", sa.Column("bnb_free", sa.Numeric(28, 12), nullable=False, server_default="0"))
    op.add_column("account_snapshots", sa.Column("bnb_value_usd", sa.Numeric(20, 8), nullable=False, server_default="0"))
    op.add_column("account_snapshots", sa.Column("allocated_usd", sa.Numeric(20, 8), nullable=False, server_default="0"))
    op.add_column("account_snapshots", sa.Column("wallet_value_usd", sa.Numeric(20, 8), nullable=False, server_default="0"))
    op.add_column("account_snapshots", sa.Column("trading_mode", sa.String(12), nullable=False, server_default="shadow"))
    op.add_column("account_snapshots", sa.Column("fees_usd", sa.Numeric(20, 8), nullable=False, server_default="0"))

    # 5. Every order the bot places, as Binance reported it (audit trail).
    op.create_table(
        "exchange_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("position_id", sa.String(120), nullable=True),
        sa.Column("client_order_id", sa.String(64), nullable=True),
        sa.Column("exchange_order_id", sa.String(64), nullable=True),
        sa.Column("request", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("response", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_exchange_events_timestamp", "exchange_events", ["timestamp"])


def downgrade() -> None:
    raise RuntimeError("The live-trading switch removes the simulated cash ledger and cannot be undone")
