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
PUBLISH_PORT="${PUBLISH_PORT:-443}"
REMOTE="${VPS_USER}@${VPS_HOST}"
# Каталог на сервере. /opt принадлежит root; под non-root деплой-юзером
# (без sudo) кладём в его HOME. Переопределяется REMOTE_DIR в deploy/.env.
REMOTE_DIR="${REMOTE_DIR:-/opt/cucumber/deploy}"
DC="docker compose -f ${REMOTE_DIR}/docker-compose.prod.yml --env-file ${REMOTE_DIR}/.env"

INIT=0
[[ "${1:-}" == "--init" ]] && INIT=1

echo "==> [1/6] Docker на ${REMOTE}"
# get.docker.com идемпотентен не вполне — ставим только если docker отсутствует.
ssh "$REMOTE" 'command -v docker >/dev/null 2>&1 || (curl -fsSL https://get.docker.com | sh)'
ssh "$REMOTE" 'docker compose version >/dev/null'

echo "==> [2/6] Синк deploy-файлов → ${REMOTE_DIR}"
ssh "$REMOTE" "mkdir -p ${REMOTE_DIR}"
if ssh "$REMOTE" 'command -v rsync >/dev/null 2>&1' && command -v rsync >/dev/null 2>&1; then
    rsync -rtv --delete --exclude='.env' docker-compose.prod.yml nginx init "${REMOTE}:${REMOTE_DIR}/"
else
    # rsync может отсутствовать (на сервере без sudo не поставить) — синкаем
    # через tar по ssh. .env не входит в набор (как и при rsync --exclude).
    echo "    rsync недоступен — синк через tar"
    tar czf - docker-compose.prod.yml nginx init | ssh "$REMOTE" "tar xzf - -C ${REMOTE_DIR}"
fi

if ssh "$REMOTE" "test -f ${REMOTE_DIR}/.env"; then
    echo "    .env уже есть на сервере — не трогаю (перезалить: scp .env ${REMOTE}:${REMOTE_DIR}/)"
else
    read -r -p "    Скопировать локальный deploy/.env (С СЕКРЕТАМИ) на сервер? [y/N] " yn
    [[ "$yn" == y* || "$yn" == Y* ]] || { echo "Без .env стек не стартует. Прервано."; exit 1; }
    scp .env "${REMOTE}:${REMOTE_DIR}/.env"
    ssh "$REMOTE" "chmod 600 ${REMOTE_DIR}/.env"
fi

echo "==> [3/6] TLS-сертификат прокси"
# Без домена — self-signed cert (доступ по IP). Генерируем на сервере ОДИН раз;
# существующий (в т.ч. доверенный, подложенный вручную) не трогаем. Прокси
# монтирует ${REMOTE_DIR}/certs:ro и ждёт fullchain.pem + privkey.pem.
ssh "$REMOTE" "set -e; CERTS=${REMOTE_DIR}/certs; \
    if [ ! -f \"\$CERTS/fullchain.pem\" ] || [ ! -f \"\$CERTS/privkey.pem\" ]; then \
        echo '    генерирую self-signed cert (CN=${VPS_HOST}, 825 дней)'; \
        mkdir -p \"\$CERTS\"; \
        openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
            -keyout \"\$CERTS/privkey.pem\" -out \"\$CERTS/fullchain.pem\" \
            -subj \"/CN=${VPS_HOST}\" \
            -addext \"subjectAltName=IP:${VPS_HOST}\" >/dev/null 2>&1; \
        chmod 600 \"\$CERTS/privkey.pem\"; \
    else echo '    cert уже есть — не трогаю'; fi"

echo "==> [4/6] Pull образов и запуск"
ssh "$REMOTE" "$DC pull && $DC up -d"
# nginx резолвит upstream'ы (analysis/ui) по имени ОДИН раз при старте и кеширует
# IP. При up -d контейнеры пересоздаются с новыми IP → proxy упирается в старый
# адрес и отдаёт 502. Рестарт proxy после up -d заставляет перечитать DNS.
ssh "$REMOTE" "$DC restart proxy"

if [[ "$INIT" == 1 ]]; then
    echo "==> [5/6] Инициализация: миграции + первый админ"
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
    echo "==> [5/6] --init не задан: миграции/админ пропущены"
fi

echo "==> [6/6] Smoke-check"
# -k: self-signed cert не проходит верификацию — для smoke это ожидаемо.
ssh "$REMOTE" "curl -fsSk https://127.0.0.1:${PUBLISH_PORT}/api/health && echo"
ssh "$REMOTE" "$DC ps"
echo "OK: UI — https://${VPS_HOST}:${PUBLISH_PORT}/  (self-signed cert → разовое предупреждение браузера)"
