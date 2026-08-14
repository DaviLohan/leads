# Leads — Radar Nacional de Oportunidades Digitais

Plataforma de inteligência comercial e prospecção B2B no Brasil. Encontra empresas brasileiras,
analisa sua presença digital, identifica oportunidades de venda de soluções digitais, pontua os
melhores potenciais clientes e acompanha a prospecção em CRM.

> **Estado:** Etapas 1 a 3 concluídas — fundação, autenticação, organizações, RBAC e isolamento
> de tenant. Próxima: geografia (IBGE). Roteiro em [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md).

## Stack

Django 5 + DRF · PostgreSQL 16 + PostGIS · Celery + Redis · Next.js 15 + TypeScript + Tailwind · Docker

## Subindo o ambiente

Pré-requisito: Docker com Compose v2. No WSL, é preciso ativar a integração em
*Docker Desktop → Settings → Resources → WSL Integration*.

```bash
cp .env.example .env      # ajuste se quiser; os defaults funcionam em dev
make up                   # sobe postgres, redis, backend, celery worker/beat e frontend
make migrate              # aplica as migrations
make seed                 # cria a organização de desenvolvimento e o usuário admin
```

Se alguma porta já estiver ocupada na máquina (outro Postgres, por exemplo), ajuste
`POSTGRES_PORT`, `REDIS_PORT`, `BACKEND_PORT` ou `FRONTEND_PORT` no `.env`.

**Primeiro acesso:** o `make seed` imprime o login de desenvolvimento. Não existe cadastro
público — em produção a primeira organização nasce de:

```bash
docker compose exec backend python manage.py create_organization \
  --name "Minha Empresa" --owner-email voce@exemplo.com
```

Os demais usuários entram por convite (`POST /api/v1/organizations/invitations/`).

Os atalhos `make` são opcionais (`sudo apt install make`); os comandos equivalentes de
`docker compose` estão no [`Makefile`](Makefile). Para conferir a fundação inteira de uma vez:

```bash
./scripts/verify-foundation.sh
```

- Frontend: <http://localhost:3000>
- API: <http://localhost:8000/api/v1/>
- Documentação OpenAPI: <http://localhost:8000/api/v1/docs/>
- Health: <http://localhost:8000/health/live> e <http://localhost:8000/health/ready>

## Comandos

```bash
make up            # sobe todos os serviços
make down          # derruba (mantém os volumes)
make logs          # logs de todos os serviços
make ps            # status dos serviços
make migrate       # aplica migrations
make makemigrations
make test          # pytest (backend) + vitest (frontend)
make test-backend
make test-frontend
make lint          # ruff + black --check + mypy + eslint + tsc
make format        # ruff --fix + black + prettier
make shell         # shell do Django
make bash          # shell do container backend
make seed          # dados fictícios de desenvolvimento
make check-deploy  # checagem de segurança com settings de produção
make clean         # derruba e remove os volumes (apaga o banco)
```

## Estrutura

```
backend/     Django + DRF + Celery
  config/    settings por ambiente, urls, celery
  apps/      apps de domínio (core, e os demais conforme as etapas)
frontend/    Next.js (App Router) + TypeScript + Tailwind
docs/        plano, ERD e ADRs
```

## Documentação

| Arquivo | Conteúdo |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Memória operacional: regras, proibições, decisões travadas |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Camadas, apps, fronteiras, fluxos |
| [`SECURITY.md`](SECURITY.md) | SSRF, tenancy, LGPD, segredos, headers |
| [`DEVELOPMENT.md`](DEVELOPMENT.md) | Setup, workflow, convenções, testes |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Ambientes, variáveis, deploy, backup/restore |
| [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) | Plano, conflitos resolvidos, roteiro, riscos |
| [`docs/ERD.md`](docs/ERD.md) | Modelo de dados |
| [`docs/adr/`](docs/adr/) | Decisões arquiteturais |

## Uso de dados

Ferramenta de prospecção **B2B**, baseada em informações comerciais legitimamente públicas. Não
faz — e não vai fazer — descoberta de dado pessoal oculto, quebra de privacidade, contorno de
autenticação, CAPTCHA ou bloqueio técnico, nem violação de Terms of Service. Cada dado guarda
fonte, data de coleta e confiabilidade. Empresas marcadas como `DO_NOT_CONTACT` são respeitadas
em toda a plataforma. Ver [`SECURITY.md`](SECURITY.md).

Dados de descoberta provenientes do OpenStreetMap: © colaboradores do OpenStreetMap, sob ODbL.
