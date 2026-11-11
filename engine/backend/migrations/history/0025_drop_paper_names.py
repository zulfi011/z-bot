"""The bot trades real money, so its tables lose the "paper" prefix: positions, trades, orders.

Indexes and constraints are renamed with them (paper_trades_pkey -> trades_pkey, ix_paper_orders_... -> ix_orders_...),
so the schema reads the same as the code. An existing database is renamed in place; no rows move.

Revision ID: 0025
Revises: 0024
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("positions", "trades", "orders")

# Every constraint (primary keys, unique, foreign and check constraints; renaming a key also renames its index)
# and every remaining index whose name still says "paper", with "paper_" taken out of the name.
RENAME_OBJECTS = """
DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT con.conname AS name, rel.relname AS tbl FROM pg_constraint con
              JOIN pg_class rel ON rel.oid = con.conrelid
              WHERE con.conname LIKE '%{old}%' AND rel.relnamespace = 'public'::regnamespace LOOP
    EXECUTE format('ALTER TABLE %I RENAME CONSTRAINT %I TO %I', item.tbl, item.name, replace(item.name, '{old}', '{new}'));
  END LOOP;
  FOR item IN SELECT relname AS name FROM pg_class
              WHERE relkind = 'i' AND relname LIKE '%{old}%' AND relnamespace = 'public'::regnamespace LOOP
    EXECUTE format('ALTER INDEX %I RENAME TO %I', item.name, replace(item.name, '{old}', '{new}'));
  END LOOP;
END $$;
"""


def upgrade() -> None:
    for table in TABLES:
        op.rename_table(f"paper_{table}", table)
    op.execute(RENAME_OBJECTS.format(old="paper_", new=""))


def downgrade() -> None:
    for table in TABLES:
        op.rename_table(table, f"paper_{table}")
    # Only the objects this migration renamed: the names of these three tables' own keys and indexes.
    for table in TABLES:
        op.execute(RENAME_OBJECTS.format(old=f"{table}_", new=f"paper_{table}_")
                   .replace("LIKE '%", "LIKE '").replace(f"LIKE '{table}_%'", f"LIKE '{table}\\_%'"))
        op.execute(RENAME_OBJECTS.format(old=f"ix_{table}_", new=f"ix_paper_{table}_"))
