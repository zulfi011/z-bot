"""A new install (migrations/schema.sql) and an upgraded one (migrations/history/) must end with the same schema.

Two throwaway databases are built: one the way a fresh install is, one through every historical step. Tables,
columns, defaults, keys, checks, indexes and the recorded revision are compared. Needs PostgreSQL; skips without it.
"""

import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, text

BASE_URL = os.environ.get("INTEGRATION_DATABASE_URL", "postgresql+psycopg://zbot:zbot_local@db:5432/zbot")
BACKEND = "/app" if os.path.isdir("/app/migrations") else "."

DESCRIBE = {
    # Column order by rank, not raw position: a dropped column leaves a gap in the numbering on upgraded databases.
    "columns": """SELECT table_name, row_number() OVER (PARTITION BY table_name ORDER BY ordinal_position),
                         column_name, data_type, character_maximum_length, numeric_precision, numeric_scale,
                         is_nullable, column_default
                  FROM information_schema.columns WHERE table_schema = 'public' ORDER BY 1, 2""",
    "constraints": """SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
                      FROM pg_constraint WHERE connamespace = 'public'::regnamespace ORDER BY 1, 2""",
    "indexes": "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1, 2",
    "revision": "SELECT version_num FROM alembic_version",
}


def build(admin, extra: list[str]) -> dict:
    name = f"zbot_schema_{uuid.uuid4().hex[:8]}"
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = BASE_URL.rsplit("/", 1)[0] + f"/{name}"
    try:
        built = subprocess.run(["alembic", *extra, "upgrade", "head"], cwd=BACKEND,
                               env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True)
        assert built.returncode == 0, built.stderr
        engine = create_engine(url)
        with engine.connect() as connection:
            schema = {key: [tuple(row) for row in connection.execute(text(sql))] for key, sql in DESCRIBE.items()}
        engine.dispose()
        return schema
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))


def test_a_fresh_install_and_an_upgraded_database_have_the_same_schema():
    admin = create_engine(BASE_URL.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect():
            pass
    except Exception as error:  # no database around: this check is optional
        pytest.skip(f"no PostgreSQL for the schema check ({error})")
    fresh = build(admin, [])
    upgraded = build(admin, ["-x", "history=1"])
    admin.dispose()
    assert len(fresh["columns"]) > 100 and fresh["revision"]
    for key in DESCRIBE:
        assert fresh[key] == upgraded[key], f"schema.sql and migrations/history/ differ in {key}"
