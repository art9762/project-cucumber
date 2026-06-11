---
name: release-v1-deploy-done
description: "v1.0.0 released (tag, GH Release, GHCR images 1.0.0) + deploy/ Compose stack built & smoke-tested locally; VPS deploy pending (needs user's IP/SSH)"
metadata: 
  node_type: memory
  type: project
  originSessionId: acfc49fa-a3ae-4421-a99e-da568835c2eb
---

2026-06-10/11: релиз v1.0.0 выполнен по плану `docs/superpowers/plans/2026-06-10-release-v1-deploy.md` (Tasks 1–8 done, swarm из ruflo-агентов: implementer + spec/quality reviewers).

- main запушен (eb41795), CI + Docker зелёные; тег `v1.0.0` → GitHub Release создан (release.yml), GHCR-образы `analysis`/`search-engine`/`ui` с тегом `1.0.0` подтверждены через `docker manifest inspect`.
- Новое: `deploy/` (docker-compose.prod.yml, nginx/proxy.conf, init/01-roles.sh, .env.example, deploy.sh), `CHANGELOG.md`, `.github/workflows/release.yml`, `docs/deploy-compose.md`; версии 1.0.0, бейджи в README.
- Smoke прод-стека локально прошёл полностью (health/login/me/UI/categories/tierlist через nginx-прокси). Найдено и исправлено в `init/01-roles.sh`: (1) роли analysis нужны default privileges SELECT+REFERENCES на таблицы движка (FK на items в миграциях анализа); (2) pgvector extension надо создавать суперпользователем до миграций анализа. Плюс ревью-фиксы deploy.sh: admin-креды через stdin, rsync --delete --exclude='.env', :? на пароли в DSN, SQL-эскейп паролей ролей.
- НЕ сделано: Task 9 — деплой на VPS (интерактивный: нужен IP, SSH-доступ, заполнение deploy/.env реальными секретами, `./deploy.sh --init`). Runbook: `docs/deploy-compose.md`; **handoff-инструкция для следующей сессии/модели: `docs/deploy-vps-handoff.md`** (коммит b34be64) — начинать с неё.
- Связано: [[phase-5-6-ui-auth-done]], [[trinity-gateway-config]]
