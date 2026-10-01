#!/bin/bash
# Runs ONCE, at first database initialization (docker-entrypoint-initdb.d).
#
# Creates:
#   1. the pgvector extension
#   2. a least-privilege application role (NOSUPERUSER) that is SUBJECT to
#      Row-Level Security — unlike the superuser used for migrations.
#
# Secrets come from the container environment (APP_DB_USER / APP_DB_PASSWORD),
# never from committed SQL.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;

    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_DB_USER}') THEN
            CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}'
                NOSUPERUSER NOCREATEDB NOCREATEROLE;
        END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${APP_DB_USER};
    GRANT USAGE ON SCHEMA public TO ${APP_DB_USER};

    -- Tables/sequences created LATER by the superuser (Alembic) become usable
    -- by the app role automatically.
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_DB_USER};
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO ${APP_DB_USER};
EOSQL

echo "Kompilo: pgvector + app role '${APP_DB_USER}' initialized."
