from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.core.settings import get_settings


config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = None

# A new install loads the whole schema in one go and starts at this revision; an older database upgrades through
# migrations/history/ instead. Both end with the same schema (tests/test_schema_baseline.py).
SCHEMA = Path(__file__).with_name("schema.sql")
BASELINE_REVISION = "0025"


def _is_empty(connection) -> bool:
    found = connection.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema())"
    )).scalar_one()
    connection.rollback()  # end the read's own transaction before the migration opens one
    return not found


def _load_baseline(connection) -> None:
    """Build an empty database from schema.sql and mark it as being at BASELINE_REVISION."""
    with connection.begin():
        connection.exec_driver_sql(SCHEMA.read_text())
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, "
                                   "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))")
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                           {"revision": BASELINE_REVISION})


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # `alembic -x history=1 upgrade head` builds an empty database through every step instead (used by the test).
    through_history = context.get_x_argument(as_dictionary=True).get("history") == "1"
    with connectable.connect() as connection:
        if not through_history and _is_empty(connection):
            _load_baseline(connection)
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
