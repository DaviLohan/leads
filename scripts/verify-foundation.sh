#!/usr/bin/env bash
# Verificação da fundação (Etapa 2). Roda a checagem completa em containers.
# Uso: ./scripts/verify-foundation.sh
set -euo pipefail

cd "$(dirname "$0")/.."

falhou=0
etapa() { printf "\n\033[1m▶ %s\033[0m\n" "$1"; }
ok()    { printf "  \033[32m✓\033[0m %s\n" "$1"; }
erro()  { printf "  \033[31m✗\033[0m %s\n" "$1"; falhou=1; }

[ -f .env ] || { echo "Crie o .env primeiro: cp .env.example .env"; exit 1; }

etapa "Subindo os serviços"
docker compose up -d --build

etapa "Aguardando os health checks"
# celery_beat não tem healthcheck (não expõe porta); os demais precisam ficar healthy.
for servico in db redis backend; do
  for _ in $(seq 1 60); do
    estado=$(docker compose ps --format '{{.Service}} {{.Health}}' | awk -v s="$servico" '$1==s{print $2}')
    [ "$estado" = "healthy" ] && break
    sleep 5
  done
  [ "$estado" = "healthy" ] && ok "$servico healthy" || erro "$servico não ficou healthy"
done
docker compose ps

etapa "Migrations"
docker compose exec -T backend python manage.py migrate --noinput && ok "aplicadas" || erro "migrate falhou"
docker compose exec -T backend python manage.py makemigrations --check --dry-run \
  && ok "sem migrations pendentes" || erro "há mudanças de model sem migration"

etapa "GeoDjango (GEOS/GDAL)"
docker compose exec -T backend python -c \
  "from django.contrib.gis.geos import Point; print(Point(-51.16, -23.31))" \
  && ok "GEOS/GDAL carregados" || erro "GeoDjango não carregou"

etapa "Health checks"
curl -fsS localhost:8000/health/live >/dev/null && ok "/health/live" || erro "/health/live"
curl -fsS localhost:8000/health/ready | grep -q '"status": "ok"' \
  && ok "/health/ready (banco + cache)" || erro "/health/ready"

etapa "Rewrite do frontend para o backend (ADR-0005)"
curl -fsS localhost:3000/api/v1/health/ | grep -q '"status": "ok"' \
  && ok "mesma origem funcionando" || erro "rewrite /api não alcançou o backend"

etapa "Documentação OpenAPI"
curl -fsS -o /dev/null localhost:8000/api/v1/schema/ && ok "schema" || erro "schema"
curl -fsS -o /dev/null localhost:8000/api/v1/docs/ && ok "docs" || erro "docs"

etapa "API não é pública"
test "$(curl -s -o /dev/null -w '%{http_code}' localhost:3000/api/v1/auth/me/)" != "200" \
  && ok "/auth/me/ exige sessão" || erro "/auth/me/ respondeu sem autenticação"

etapa "Celery"
docker compose exec -T backend python -c \
  "from config.celery import debug_task; print(debug_task.delay().get(timeout=30))" \
  && ok "worker processou a task" || erro "worker não respondeu"

etapa "Testes e lint do backend"
docker compose exec -T backend pytest -q && ok "pytest" || erro "pytest"
docker compose exec -T backend ruff check . && ok "ruff" || erro "ruff"
docker compose exec -T backend black --check -q . && ok "black" || erro "black"
docker compose exec -T backend mypy . && ok "mypy" || erro "mypy"

etapa "Testes e lint do frontend"
docker compose exec -T frontend npm run lint && ok "eslint" || erro "eslint"
docker compose exec -T frontend npx tsc --noEmit && ok "tsc" || erro "tsc"
docker compose exec -T frontend npm run test && ok "vitest" || erro "vitest"

etapa "Segurança do settings de produção"
docker compose exec -T \
  -e DJANGO_SETTINGS_MODULE=config.settings.production \
  -e DJANGO_SECRET_KEY=verificacao-com-mais-de-cinquenta-caracteres-para-passar-na-validacao \
  -e DJANGO_ALLOWED_HOSTS=example.com \
  -e CORS_ALLOWED_ORIGINS=https://example.com \
  -e CSRF_TRUSTED_ORIGINS=https://example.com \
  backend python manage.py check --deploy --fail-level WARNING \
  && ok "check --deploy limpo" || erro "check --deploy acusou problema"

if [ "$falhou" -eq 0 ]; then
  printf "\n\033[32mFundação verificada.\033[0m\n"
else
  printf "\n\033[31mHá falhas acima.\033[0m\n"; exit 1
fi
