-- Read-only database login for the public stats job (deploy/public_stats).
-- It can only SELECT four tables, every transaction is read-only, and every query stops after 20 seconds.
-- It has no password, so it can only log in from inside the db container (local socket), never over the network.
--
-- Run once on the server, from /opt/z-bot:
--   docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < deploy/public_stats/create_readonly_role.sql

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'zbot_stats') THEN
        CREATE ROLE zbot_stats LOGIN;
    END IF;
END
$$;

ALTER ROLE zbot_stats NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 2;
ALTER ROLE zbot_stats SET default_transaction_read_only = on;
ALTER ROLE zbot_stats SET statement_timeout = '20s';

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM zbot_stats;
SELECT format('GRANT CONNECT ON DATABASE %I TO zbot_stats', current_database()) \gexec
GRANT USAGE ON SCHEMA public TO zbot_stats;
GRANT SELECT ON paper_trades, paper_positions, account_snapshots, candles_1m TO zbot_stats;
