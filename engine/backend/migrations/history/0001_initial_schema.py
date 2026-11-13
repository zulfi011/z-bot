"""Create the first database schema (from when the bot only paper-traded).

Revision ID: 0001
Revises: None
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candles_1m",
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(24, 10), nullable=False),
        sa.Column("high", sa.Numeric(24, 10), nullable=False),
        sa.Column("low", sa.Numeric(24, 10), nullable=False),
        sa.Column("close", sa.Numeric(24, 10), nullable=False),
        sa.Column("volume", sa.Numeric(32, 12), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "open_time"),
        sa.CheckConstraint("open > 0 AND high > 0 AND low > 0 AND close > 0", name="ck_candles_positive"),
        sa.CheckConstraint("low <= open AND low <= close AND high >= open AND high >= close", name="ck_candles_ohlc"),
    )
    op.create_index("ix_candles_1m_open_time", "candles_1m", ["open_time"])

    op.create_table(
        "touch_episodes",
        sa.Column("episode_id", sa.String(100), primary_key=True),
        sa.Column("strategy_id", sa.String(80), nullable=False),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("touch_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("average_value", sa.Numeric(24, 10), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("strategy_id", "symbol", "touch_time", name="uq_touch_episode"),
    )

    op.create_table(
        "signals",
        sa.Column("signal_id", sa.String(120), primary_key=True),
        sa.Column("episode_id", sa.String(100), sa.ForeignKey("touch_episodes.episode_id"), nullable=False),
        sa.Column("strategy_id", sa.String(80), nullable=False),
        sa.Column("signal_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(100), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("strategy_id", "episode_id", name="uq_signal_episode"),
    )
    op.create_index("ix_signals_signal_time", "signals", ["signal_time"])

    op.create_table(
        "paper_orders",
        sa.Column("order_id", sa.String(120), primary_key=True),
        sa.Column("signal_id", sa.String(120), sa.ForeignKey("signals.signal_id"), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("fill_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("notional_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("fee_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("slippage_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0 AND notional_usd > 0", name="ck_paper_orders_positive"),
    )

    op.create_table(
        "paper_positions",
        sa.Column("position_id", sa.String(120), primary_key=True),
        sa.Column("signal_id", sa.String(120), sa.ForeignKey("signals.signal_id"), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_fill_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("allocation_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("trailing_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("peak_price", sa.Numeric(24, 10), nullable=True),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_fill_price", sa.Numeric(24, 10), nullable=True),
        sa.Column("exit_reason", sa.String(40), nullable=True),
        sa.Column("realized_pnl_usd", sa.Numeric(20, 8), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0 AND allocation_usd > 0", name="ck_paper_positions_positive"),
    )
    op.create_index(
        "uq_paper_positions_open_signal", "paper_positions", ["signal_id"],
        unique=True, postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "paper_trades",
        sa.Column("trade_id", sa.String(120), primary_key=True),
        sa.Column("position_id", sa.String(120), sa.ForeignKey("paper_positions.position_id"), nullable=False, unique=True),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("allocation_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_fill_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("exit_fill_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("entry_fee_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("exit_fee_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("slippage_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("exit_reason", sa.String(40), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("net_return_pct", sa.Numeric(16, 8), nullable=False),
        sa.Column("net_pnl_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("exit_time > entry_time", name="ck_paper_trades_time_order"),
    )
    op.create_index("ix_paper_trades_exit_time", "paper_trades", ["exit_time"])

    op.create_table(
        "account_snapshots",
        sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("cash_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("open_position_value_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("realized_pnl_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("unrealized_pnl_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("total_equity_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("drawdown_pct", sa.Numeric(16, 8), nullable=False),
        sa.Column("open_positions", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("cash_usd >= 0 AND open_positions BETWEEN 0 AND 2", name="ck_account_spot_limits"),
    )

    op.create_table(
        "engine_state",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "system_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("component", sa.String(40), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_system_events_timestamp", "system_events", ["timestamp"])


def downgrade() -> None:
    op.drop_table("system_events")
    op.drop_table("engine_state")
    op.drop_table("account_snapshots")
    op.drop_table("paper_trades")
    op.drop_table("paper_positions")
    op.drop_table("paper_orders")
    op.drop_table("signals")
    op.drop_table("touch_episodes")
    op.drop_table("candles_1m")

