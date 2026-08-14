# Desenvolvimento

## Setup

Pré-requisito único: Docker com Compose v2. No WSL, ativar em *Docker Desktop → Settings →
Resources → WSL Integration*.

```bash
cp .env.example .env
make up
make migrate
```

Tudo roda em container — não é preciso Python, Node, Postgres ou Redis instalados na máquina.
Os diretórios `backend/` e `frontend/` são montados como volume, então o código recarrega sozinho.

## Rotina

```bash
make logs                    # todos os serviços
docker compose logs -f backend
make bash                    # shell dentro do container backend
make shell                   # shell do Django
```

Ao alterar dependências:

```bash
docker compose build backend    # após mexer em pyproject.toml
docker compose build frontend   # após mexer em package.json
```

## Convenções de código

**Python** — `ruff` (lint + import sort), `black` (formatação), `mypy` (tipos), `pytest` (testes).
Configuração toda em `backend/pyproject.toml`.

- Todo model herda de `core.models.BaseModel`.
- Regra de negócio em `services/`, não na view. View só traduz HTTP.
- Lógica pura e testável sem banco vai para `domain/` ou `rules/`.
- Task Celery é casca fina: recebe IDs, chama o service, é idempotente.
- Sem `except Exception: pass` — o lint bloqueia.
- Docstring quando o *porquê* não é óbvio; nome bom dispensa comentário do *o quê*.

**TypeScript** — ESLint + Prettier, `strict` ligado. `any` não é solução habitual; se for
inevitável, `unknown` com narrowing.

**Commits** — conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.

## Migrations

```bash
make makemigrations
make migrate
```

- Toda mudança de schema passa por migration. Nunca alterar banco à mão.
- Revisar o arquivo gerado antes de commitar — principalmente índices e constraints.
- Migration de dado em arquivo separado da de schema.
- Índice em tabela grande: `AddIndexConcurrently` com `atomic = False`.
- Migration precisa ser reproduzível: `migrate` do zero tem que funcionar.

## Testes

```bash
make test           # backend + frontend
make test-backend
make test-frontend
docker compose exec backend pytest apps/core -v
docker compose exec backend pytest -k uuid7
docker compose exec backend pytest --cov=apps --cov-report=term-missing
```

Prioridade de cobertura (na ordem): autenticação, autorização, isolamento de tenant,
deduplicação, scoring, providers, CRM, proteção contra SSRF.

Regras:

- Teste nunca depende de rede nem de API paga — use o `MockProvider`.
- Nada de centenas de testes triviais; cubra fluxo crítico e caso de borda real.
- Teste que falha não vira teste removido.

## Qualidade

```bash
make lint      # ruff + black --check + mypy + eslint + tsc --noEmit
make format    # ruff --fix + black + prettier
```

`pre-commit` roda o mesmo conjunto localmente. Para instalar (opcional, requer Python no host):

```bash
pip install pre-commit && pre-commit install
```

## Variáveis de ambiente

Todas em `.env.example`, com defaults que funcionam em desenvolvimento. `.env` **nunca** é
versionado. Segredo novo entra no `.env.example` com valor de exemplo, nunca com o valor real.

## Dados de desenvolvimento

```bash
make seed
```

Cria empresas fictícias, categorias e regras iniciais. Não depende de API externa.

## Debug

```bash
docker compose exec backend python manage.py shell_plus   # se django-extensions estiver instalado
docker compose exec db psql -U leads -d leads
docker compose exec redis redis-cli
docker compose exec backend celery -A config inspect active
```

Para inspecionar SQL de uma query: `print(qs.query)` ou `qs.explain()`.

## Antes de abrir PR

1. `make lint` limpo.
2. `make test` verde.
3. Migration revisada.
4. Sem segredo no diff.
5. Decisão arquitetural relevante documentada em `docs/adr/`.
6. `CLAUDE.md` atualizado se mudou regra, comando ou fronteira.
