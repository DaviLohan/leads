# CLAUDE.md — memória operacional

> Leia este arquivo **antes de qualquer mudança relevante**. Ele resume o que o projeto é,
> como está organizado, e o que é proibido. Regras aqui vencem preferências pessoais.

## O que é

Plataforma de inteligência comercial e prospecção B2B no Brasil — um **radar nacional de
oportunidades digitais**. Encontra empresas brasileiras, coleta dados comerciais públicos,
analisa presença digital, identifica oportunidades (site, agendamento, e-commerce, sistemas),
pontua leads e acompanha a prospecção em CRM.

Produto de longo prazo, não protótipo. Pode chegar a milhões de empresas.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, Django 5.1, Django REST Framework |
| Banco | PostgreSQL 16 + PostGIS 3.4 (`django.contrib.gis`) |
| Fila / cache | Celery 5 + Redis 7 |
| Frontend | Next.js 15 (App Router), React 19, TypeScript strict, Tailwind |
| Infra | Docker Compose (dev), containers em qualquer host (prod) |

## Arquitetura em uma frase

**Monólito modular Django** com fronteiras de domínio explícitas por app, preparado para
extrair workers (discovery, scanner, IA) no futuro — mas **não separado agora**.

Camadas: `HTTP (views/serializers)` → `services (regra de negócio)` → `domain` →
`persistence (models)` → `integrations (providers)`. Regra de negócio relevante **nunca**
mora na view.

## Apps

| App | Responsabilidade | Existe? |
|---|---|---|
| `core` | BaseModel, TenantModel, uuid7, AuditLog, health, middleware, logging, viewsets, audit | ✅ |
| `accounts` | User, Organization, Membership, Invitation, RBAC, autenticação por sessão | ✅ |
| `geography` | State, City (IBGE), geometrias | ✅ |
| `companies` | Company + endereços, contatos, sites, categorias, normalização | ✅ (dedup: Etapa 6) |
| `providers` | BaseProvider, Overpass, Mock, CompanySource, uso, rate limit | ✅ |
| `discovery` | Search, SearchJob, particionamento, tasks | Etapa 8 |
| `analysis` | WebsiteScan/Finding, SSRF guard, Opportunity, Score | Etapas 9–11 |
| `crm` | Lead, Pipeline, Stage, Interaction, Note, Task, Suppression | Etapa 12 |

**Não crie um app antes da etapa que o usa.** Pacotes vazios são dívida, não preparo.

Regra de dependência: apps de domínio superior importam os inferiores, nunca o contrário.
`core` ← `accounts` ← `geography` ← `companies` ← `providers` ← `discovery` ← `analysis` ← `crm`.
`companies` **não** importa `crm`.

## Decisões travadas (mudar exige ADR novo)

| # | Decisão | ADR |
|---|---|---|
| 1 | Monólito modular. Sem microserviços, Kafka, K8s, CQRS, event sourcing. | [0001](docs/adr/0001-modular-monolith.md) |
| 2 | PostgreSQL + PostGIS é a única fonte de verdade. Redis nunca é. | [0002](docs/adr/0002-postgresql-postgis.md) |
| 3 | Provider nunca escreve no banco. Pipeline: Raw → Validate → Normalize → Dedup → Resolve → Persist. | [0003](docs/adr/0003-provider-abstraction.md) |
| 4 | OSM/Overpass é o provider primário. Google Places **não** pode ter seus dados armazenados. | [0004](docs/adr/0004-osm-primary-provider.md) |
| 5 | Auth por sessão em cookie HTTPOnly + CSRF. Sem JWT, sem token em localStorage. | [0005](docs/adr/0005-session-cookie-auth.md) |
| 6 | PK é UUIDv7 (`core.ids.uuid7`), nunca uuid4, nunca int sequencial exposto. | [0006](docs/adr/0006-uuidv7-primary-keys.md) |
| 7 | Dado público é global; dado comercial pertence à Organization. | [0007](docs/adr/0007-tenancy-boundary.md) |
| 8 | Regras de score/oportunidade são predicados registrados em código, parametrizados no banco. Nunca `eval`. | [0008](docs/adr/0008-declarative-rules.md) |

## Regras de código

- Todo model herda de `core.models.BaseModel` (PK uuid7 + `created_at`/`updated_at`).
- Integridade no **banco**: `UniqueConstraint`, `CheckConstraint`, FK. Não só na aplicação.
- Toda listagem tem paginação. Nunca retornar milhares de linhas.
- Dinheiro é `DecimalField`. Nunca `float`.
- Datas em UTC no banco (`USE_TZ=True`); conversão só na apresentação (`America/Sao_Paulo`).
- Operações críticas (merge, dedup, importação, mudança de estágio) rodam em `transaction.atomic`.
- Idempotência vem de constraint no banco + `get_or_create`, não de `if exists` em Python.
- Erros externos: timeout + retry limitado + backoff exponencial com jitter. Nunca retry infinito.
- Strings de UI em pt-BR.

## Proibido

- `except Exception: pass` ou engolir erro sem log. (lint bloqueia)
- Segredo no código ou no Git. Só variável de ambiente. `.env` nunca é versionado.
- SQL por concatenação de string. ORM ou query parametrizada.
- `dangerouslySetInnerHTML` com conteúdo não sanitizado.
- `any` como solução habitual no TypeScript.
- Desabilitar CSRF, CORS aberto com `*`, ou baixar segurança para "resolver" um bug.
- Remover ou pular teste para o pipeline passar.
- Requisição HTTP a URL fornecida pelo usuário sem passar pelo guard de SSRF.
- Scraping agressivo, burlar CAPTCHA, contornar bloqueio técnico ou ToS de qualquer fonte.
- Coletar dado pessoal privado. A plataforma é B2B e usa dado comercial legitimamente público.
- Afirmar "empresa não tem site". O correto é "Site oficial não identificado nas fontes analisadas".

## Comandos

```bash
make up          # sobe tudo (docker compose)
make down        # derruba
make logs        # logs de todos os serviços
make migrate     # aplica migrations
make makemigrations
make test        # pytest (backend) + vitest (frontend)
make lint        # ruff + black --check + mypy + eslint + tsc
make format      # ruff --fix + black + prettier
make shell       # shell do Django
make seed        # dados fictícios de desenvolvimento
```

## Antes de uma mudança grande

1. Reler este arquivo e o ADR relacionado.
2. Ver o que já existe — não duplicar helper/serviço.
3. Checar impacto: segurança, tenancy, índices, N+1, custo de API externa.
4. Implementar na camada certa (service, não view).
5. `make test` e `make lint` — e reportar a saída real, nunca "deve funcionar".
6. Migration revisada (nada de editar banco à mão).
7. Documentar decisão relevante em `docs/adr/`.

## Prioridade quando houver conflito

Segurança → Integridade dos dados → Manutenibilidade → Clareza → Testabilidade → Performance → Conveniência.

## Tenancy na prática

- Model de dado comercial herda de `core.models.TenantModel` (FK `organization`, `PROTECT`).
- A view expõe por `core.viewsets.TenantViewSet` — é o **único** ponto que aplica o filtro por
  organização. Não filtre à mão em cada view.
- O filtro é explícito (`for_organization`), nunca automático: manager que se filtra sozinho
  pelo request quebra em task Celery e esconde a falha onde ela custa mais caro.
- `request.organization` e `request.membership` vêm do `OrganizationMiddleware`, revalidados a
  cada requisição. Nunca aceite organização vinda do payload.
- Recurso de outra organização responde **404, não 403**.
- Papel mínimo: `permission_classes = [MinRole.at_least(Role.ADMIN)]`. Hierarquia
  `OWNER > ADMIN > MANAGER > SALES > VIEWER`.
- Ação relevante grava auditoria por `core.audit.record_audit`.

## Estado atual

Etapas 1 a 7 concluídas: arquitetura, fundação, autenticação, organizações, RBAC, isolamento
de tenant, geografia, empresas com normalização, deduplicação e as fontes de dados.
Próxima: **Etapa 8 — motor de busca (Search, SearchJob, tasks, progresso)**.
Roadmap completo em `docs/PROJECT_PLAN.md`.

Não existe cadastro público: a primeira organização nasce de
`python manage.py create_organization`, e os demais usuários entram por convite.

A base geográfica não vem do `seed`: rode `python manage.py import_ibge` (27 estados,
5.571 municípios). É idempotente — reimportar atualiza nomes e não duplica. Sem rede, use
`--file` com um JSON `{"estados": [...], "municipios": [...]}`.

`City.centroid` está nulo de propósito até a Etapa 8, quando o particionamento geográfico
das buscas passar a precisar dele. `City.boundary` não existe.

Normalização de identificador mora em `apps/companies/normalization.py` (CNPJ, telefone
E.164 e domínio) e em `apps/core/text.py` (`normalize_name`). Não escreva outra: `providers`
(Etapa 7) e a supressão do `crm` (Etapa 12) importam dessas. Toda função devolve `None` para
entrada inaproveitável — nunca o valor cru, que entraria meio normalizado e furaria a
unicidade em silêncio.

`CompanySource` não fica em `companies`: tem FK para `Provider` e nasce no app `providers`,
na Etapa 7 (ver nota em `docs/ERD.md`).

## Deduplicação

`companies/dedup.py` **só lê** e devolve uma `Resolution`; quem grava é o pipeline de
ingestão (ADR-0003). Sinais em ordem de força: CNPJ (`EXACT`) → domínio → telefone+cidade →
similaridade de nome. `POSSIBLE` **nunca** funde sozinho — a assimetria é deliberada: não
fundir custa uma duplicata, fundir errado destrói dois históricos.

O recorte por município antes de qualquer comparação de nome não é otimização, é o que
torna o problema tratável (PROJECT_PLAN §3.5). Candidato sem cidade não entra na comparação
por nome. Nunca compare nome em Python sobre a tabela: o cálculo é do Postgres, no índice GIN.

Merge é `companies/services.merge_companies` — atômico, com `select_for_update` **antes** de
validar (validar objeto em memória deixa fundir duas vezes), satélite colidente descartado
em vez de derrubar a transação, e auditoria por `record_audit`. A duplicata não é apagada:
vira `status=MERGED` com `merged_into` apontando para a sobrevivente.

## Fontes de dados

Provider **não escreve no banco** e não importa model (ADR-0003). Devolve `RawResult`; quem
valida, deduplica e persiste é `providers/ingestion.py`, o único módulo do pacote que grava.
`if provider == "x"` fora de `apps/providers` significa que a abstração vazou.

Busca no Overpass recorta por `IBGE:GEOCODIGO`, a mesma chave da Etapa 4, e usa
`map_to_area` — `area["tag"=...]` responde **504**, o índice de áreas não serve para filtro
por tag arbitrária. O endpoint público é instável: medido, uma busca levou dois 504 antes de
responder, por isso `OVERPASS_MAX_ATTEMPTS=5`.

`MockProvider` é obrigatório e determinístico: nenhum teste sai para a rede. Ele imita as
imperfeições do OSM de propósito (tag faltando, `contact:` misturado com a grafia antiga,
telefone inválido) — mock limpo demais esconde o bug que deveria pegar.

Antes de usar qualquer fonte: `python manage.py seed_providers`.
