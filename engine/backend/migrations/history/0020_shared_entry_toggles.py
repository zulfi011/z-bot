"""Every way in shares the coin's lots again: the extras are simply on or off.

The 'off / shared / own' modes and their reserved lot counts are gone. Research showed reserved lots lose to the
same money spread across shared lots on every coin, so `pullback_mode/lots` and `pyramid_mode/lots` collapse to
`pullback_enabled` and `pyramid_enabled`. Anything that was not 'off' becomes enabled, and any lots a module held
of its own are folded back into the coin's lots so no money silently disappears from a live allocation.

Revision ID: 0020
Revises: 0019
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for module, default in (("pullback", sa.true()), ("pyramid", sa.false())):
        op.add_column("coin_allocations",
                      sa.Column(f"{module}_enabled", sa.Boolean(), nullable=False, server_default=default))
    op.execute("""
        UPDATE coin_allocations
           SET pullback_enabled = (pullback_mode <> 'off'),
               pyramid_enabled  = (pyramid_mode  <> 'off'),
               lots = least(100, lots
                                 + CASE WHEN pullback_mode = 'own' THEN pullback_lots ELSE 0 END
                                 + CASE WHEN pyramid_mode  = 'own' THEN pyramid_lots  ELSE 0 END)
    """)
    # How the lot was being held when it was sold, so the trade list can say Mode A or Mode B rather than
    # leaving it to be guessed from the exit reason.
    op.add_column("paper_trades", sa.Column("exit_mode", sa.String(10), nullable=True))
    op.execute("UPDATE paper_trades SET exit_mode = CASE WHEN exit_reason = 'trend_exit' THEN 'trend' END")
    for module in ("pullback", "pyramid"):
        op.drop_constraint(f"ck_coin_allocations_{module}_lots", "coin_allocations", type_="check")
        op.drop_constraint(f"ck_coin_allocations_{module}_mode", "coin_allocations", type_="check")
        op.drop_column("coin_allocations", f"{module}_lots")
        op.drop_column("coin_allocations", f"{module}_mode")


def downgrade() -> None:
    for module, default in (("pullback", "shared"), ("pyramid", "off")):
        op.add_column("coin_allocations",
                      sa.Column(f"{module}_mode", sa.String(8), nullable=False, server_default=default))
        op.add_column("coin_allocations",
                      sa.Column(f"{module}_lots", sa.Integer(), nullable=False, server_default="0"))
        op.create_check_constraint(f"ck_coin_allocations_{module}_mode", "coin_allocations",
                                   f"{module}_mode IN ('off','shared','own')")
        op.create_check_constraint(f"ck_coin_allocations_{module}_lots", "coin_allocations",
                                   f"{module}_lots >= 0")
    op.execute("""
        UPDATE coin_allocations
           SET pullback_mode = CASE WHEN pullback_enabled THEN 'shared' ELSE 'off' END,
               pyramid_mode  = CASE WHEN pyramid_enabled  THEN 'shared' ELSE 'off' END
    """)
    op.drop_column("paper_trades", "exit_mode")
    for module in ("pullback", "pyramid"):
        op.drop_column("coin_allocations", f"{module}_enabled")
