"""Redesign for the single SOL fixed-$100 strategy with a BNB fee wallet.

Deletes all previous paper-trading history (SOL, ETH, BTC) and ETH/BTC market
data, keeps SOL one-minute candles, and recreates the paper ledger with fee
assets, account control requests and flow-aware account snapshots.

Revision ID: 0010
Revises: 0009
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("paper_trades", "paper_orders", "paper_positions", "signals", "touch_episodes",
                  "account_snapshots", "strategy_configurations", "candles_3m"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DELETE FROM monitoring_alerts")
    op.execute("DELETE FROM system_events")
    op.execute("DELETE FROM engine_state")
    op.execute("DELETE FROM candles_1m WHERE symbol <> 'SOLUSDT'")
    op.execute("DELETE FROM daily_averages")
    op.add_column("daily_averages", sa.Column("signal_average_days", sa.SmallInteger(), nullable=True))
    op.add_column("daily_averages", sa.Column("signal_average", sa.Numeric(24, 12), nullable=True))

    op.create_table(
        "touch_episodes",
        sa.Column("episode_id", sa.String(120), primary_key=True),
        sa.Column("strategy_id", sa.String(80), nullable=False),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("touch_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("average_value", sa.Numeric(24, 12), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_touch_episodes_touch_time", "touch_episodes", ["touch_time"])
    op.create_table(
        "signals",
        sa.Column("signal_id", sa.String(120), primary_key=True),
        sa.Column("episode_id", sa.String(120), sa.ForeignKey("touch_episodes.episode_id"), nullable=False, unique=True),
        sa.Column("strategy_id", sa.String(80), nullable=False),
        sa.Column("signal_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(100), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_signals_entry_time", "signals", ["entry_time"])
    op.create_table(
        "paper_positions",
        sa.Column("position_id", sa.String(120), primary_key=True),
        sa.Column("signal_id", sa.String(120), sa.ForeignKey("signals.signal_id"), nullable=True, unique=True),
        sa.Column("entry_source", sa.String(16), nullable=False),
        sa.Column("lot_number", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_entry_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("entry_fill_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("allocation_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_fee_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_fee_asset", sa.String(8), nullable=False),
        sa.Column("entry_fee_bnb", sa.Numeric(28, 12), nullable=False, server_default="0"),
        sa.Column("bars_held", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trailing_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("peak_price", sa.Numeric(24, 10), nullable=True),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_exit_price", sa.Numeric(24, 10), nullable=True),
        sa.Column("exit_fill_price", sa.Numeric(24, 10), nullable=True),
        sa.Column("exit_fee_usd", sa.Numeric(20, 8), nullable=True),
        sa.Column("exit_fee_asset", sa.String(8), nullable=True),
        sa.Column("exit_fee_bnb", sa.Numeric(28, 12), nullable=True),
        sa.Column("exit_cash_usd", sa.Numeric(20, 8), nullable=True),
        sa.Column("exit_reason", sa.String(40), nullable=True),
        sa.Column("realized_pnl_usd", sa.Numeric(20, 8), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0 AND allocation_usd > 0", name="ck_positions_positive"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_positions_status"),
    )
    op.create_table(
        "paper_orders",
        sa.Column("order_id", sa.String(140), primary_key=True),
        sa.Column("position_id", sa.String(120), sa.ForeignKey("paper_positions.position_id"), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("fill_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("notional_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("fee_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("fee_asset", sa.String(8), nullable=False),
        sa.Column("fee_bnb", sa.Numeric(28, 12), nullable=False, server_default="0"),
        sa.Column("slippage_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("position_id", "side", name="uq_orders_position_side"),
    )
    op.create_table(
        "paper_trades",
        sa.Column("trade_id", sa.String(140), primary_key=True),
        sa.Column("position_id", sa.String(120), sa.ForeignKey("paper_positions.position_id"), nullable=False, unique=True),
        sa.Column("entry_source", sa.String(16), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("allocation_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_fill_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("exit_fill_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("entry_fee_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("exit_fee_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("bnb_fees_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("slippage_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("exit_reason", sa.String(40), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("net_return_pct", sa.Numeric(16, 8), nullable=False),
        sa.Column("net_pnl_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_paper_trades_exit_time", "paper_trades", ["exit_time"])
    op.create_table(
        "control_requests",
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("amount_usd", sa.Numeric(20, 8), nullable=True),
        sa.Column("position_id", sa.String(120), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "kind IN ('initial_deposit','deposit','withdrawal','bnb_purchase','manual_buy','close_position')",
            name="ck_control_requests_kind",
        ),
        sa.CheckConstraint("status IN ('pending','applied','rejected')", name="ck_control_requests_status"),
    )
    op.create_index("ix_control_requests_status", "control_requests", ["status", "requested_at"])
    op.create_table(
        "account_snapshots",
        sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("cash_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("open_position_value_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("open_position_cost_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("open_positions", sa.SmallInteger(), nullable=False),
        sa.Column("bnb_balance", sa.Numeric(28, 12), nullable=False),
        sa.Column("bnb_price_usd", sa.Numeric(24, 10), nullable=True),
        sa.Column("bnb_value_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("total_value_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("net_deposits_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("realized_pnl_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("unrealized_pnl_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("strategy_pnl_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("performance_equity_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("performance_peak_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("drawdown_pct", sa.Numeric(16, 8), nullable=False),
        sa.Column("return_pct", sa.Numeric(16, 8), nullable=False),
        sa.Column("usdt_fees_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("bnb_fees_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("slippage_usd", sa.Numeric(20, 8), nullable=False),
        sa.CheckConstraint("cash_usd >= 0 AND bnb_balance >= 0 AND open_positions >= 0", name="ck_snapshot_spot_limits"),
    )


def downgrade() -> None:
    raise RuntimeError("The SOL fixed-$100 redesign deletes previous history and cannot be downgraded")
