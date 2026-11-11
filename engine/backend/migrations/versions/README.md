# New migrations

Add new migration files here (`alembic revision -m "..."`). Each one runs on top of the current schema for every
install: fresh installs (built from `../schema.sql`) and older databases (upgraded through `../history/`).

After adding one, regenerate `../schema.sql` and update `BASELINE_REVISION` in `../env.py`, or leave both as they
are: a fresh install loads the schema at `BASELINE_REVISION` and then runs every newer migration on top.
