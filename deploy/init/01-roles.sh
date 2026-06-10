#!/bin/bash
# Выполняется официальным entrypoint'ом Postgres ОДИН раз — при первой
# инициализации тома pgdata (docker-entrypoint-initdb.d). Создаёт роли
# приложения с минимальными правами; пароли приходят из env compose-сервиса
# (deploy/.env), в файле ничего не захардкожено.
#
# Роли (см. docs/phase-6-deploy-hardening.md §3.3):
#   analysis    — RW: свои таблицы анализа + alembic (нужен CREATE на schema)
#   analysis_ro — read-only к таблицам движка (DB_URL_READ)
set -euo pipefail

# Экранируем одинарные кавычки для безопасной вставки в SQL-литерал.
sq=$'\''
AP_SQL="${ANALYSIS_PASSWORD//$sq/$sq$sq}"
ARO_SQL="${ANALYSIS_RO_PASSWORD//$sq/$sq$sq}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE analysis LOGIN PASSWORD '${AP_SQL}';
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO analysis;
    GRANT USAGE, CREATE ON SCHEMA public TO analysis;

    CREATE ROLE analysis_ro LOGIN PASSWORD '${ARO_SQL}';
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO analysis_ro;
    GRANT USAGE ON SCHEMA public TO analysis_ro;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO analysis_ro;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analysis_ro;
EOSQL
