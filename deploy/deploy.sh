#!/usr/bin/env bash
# Деплой стека Project cucumber на VPS по SSH. Идемпотентен: повторный запуск
# просто обновляет файлы и перекатывает контейнеры (pull + up -d).
#
#   ./deploy.sh          — синк файлов, pull образов, up -d, smoke-check
#   ./deploy.sh --init   — то же + миграции БД и создание первого админа
#
# Параметры подключения и секреты — в deploy/.env (см. .env.example).
# Локальный .env по умолчанию НЕ копируется — спросим подтверждение.
set -euo pipefail
cd "$(dirname "$0")"

[[ -f .env ]] || { echo "ERROR: deploy/.env не найден — cp .env.example .env и заполни"; exit 1; }
# shellcheck disable=SC1091
source .env

: "${VPS_HOST:?VPS_HOST не задан в deploy/.env}"
VPS_USER="${VPS_USER:-root}"
REMOTE="${VPS_USER}@${VPS_HOST}"
REMOTE_DIR=/opt/cucumber/deploy
DC="docker compose -f ${REMOTE_DIR}/docker-compose.prod.yml --env-file ${REMOTE_DIR}/.env"

INIT=0
[[ "${1:-}" == "--init" ]] && INIT=1

echo "==> [1/5] Docker на ${REMOTE}"
# get.docker.com идемпотентен не вполне — ставим только если docker отсутствует.
ssh "$REMOTE" 'command -v docker >/dev/null 2>&1 || (curl -fsSL https://get.docker.com | sh)'
ssh "$REMOTE" 'docker compose version >/dev/null'

echo "==> [2/5] Синк deploy-файлов → ${REMOTE_DIR}"
ssh "$REMOTE" "mkdir -p ${REMOTE_DIR}"
rsync -rtv --delete docker-compose.prod.yml nginx init "${REMOTE}:${REMOTE_DIR}/"

if ssh "$REMOTE" "test -f ${REMOTE_DIR}/.env"; then
    echo "    .env уже есть на сервере — не трогаю (перезалить: scp .env ${REMOTE}:${REMOTE_DIR}/)"
else
    read -r -p "    Скопировать локальный deploy/.env (С СЕКРЕТАМИ) на сервер? [y/N] " yn
    [[ "$yn" == y* || "$yn" == Y* ]] || { echo "Без .env стек не стартует. Прервано."; exit 1; }
    scp .env "${REMOTE}:${REMOTE_DIR}/.env"
    ssh "$REMOTE" "chmod 600 ${REMOTE_DIR}/.env"
fi

echo "==> [3/5] Pull образов и запуск"
ssh "$REMOTE" "$DC pull && $DC up -d"

if [[ "$INIT" == 1 ]]; then
    echo "==> [4/5] Инициализация: миграции + первый админ"
    # Схема движка (items, raw_records, jobs) — от имени findengine.
    ssh "$REMOTE" "$DC run --rm collector python -m alembic upgrade head"
    # Схема анализа (0001→0003) — от имени роли analysis.
    ssh "$REMOTE" "$DC run --rm analysis python -m alembic upgrade head"

    read -r -p    "    Логин админа [admin]: " ADMIN_USER
    ADMIN_USER="${ADMIN_USER:-admin}"
    [[ "$ADMIN_USER" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "Недопустимое имя пользователя"; exit 1; }
    read -r -s -p "    Пароль админа (не отображается): " ADMIN_PASS; echo
    [[ -n "$ADMIN_PASS" ]] || { echo "Пустой пароль. Прервано."; exit 1; }
    # Оба значения передаются через stdin → переменные удалённого шелла.
    # Контейнер не наследует пайп (</dev/null).
    printf '%s\n%s\n' "$ADMIN_USER" "$ADMIN_PASS" | ssh "$REMOTE" "read -r AU; read -r AP; \
        $DC run --rm analysis python -m analysis.auth create-admin \
        --username \"\$AU\" --password \"\$AP\" </dev/null"
else
    echo "==> [4/5] --init не задан: миграции/админ пропущены"
fi

echo "==> [5/5] Smoke-check"
ssh "$REMOTE" "curl -fsS http://127.0.0.1/api/health && echo"
ssh "$REMOTE" "$DC ps"
echo "OK: UI — http://${VPS_HOST}/"
