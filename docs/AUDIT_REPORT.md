# Relatório de auditoria — plataforma `leads`

Auditoria de estado real do código, executada em 2026-08-14.

**Método:** leitura integral do código-fonte, documentação, infraestrutura e CI. Toda afirmação
de status tem `arquivo:linha` ou o comando que a produziu. O que não pôde ser executado está
marcado ❓ e não é apresentado como verificado.

**Escopo lido:** 40 arquivos Python (`backend/apps/`, `backend/config/`, `conftest.py`),
9 arquivos do frontend (`frontend/src/`), 3 arquivos Compose, `Makefile`, `.github/workflows/ci.yml`,
`.pre-commit-config.yaml`, `scripts/verify-foundation.sh`, 2 `Dockerfile`, e os 15 documentos
(`README.md`, `ARCHITECTURE.md`, `SECURITY.md`, `DEVELOPMENT.md`, `DEPLOYMENT.md`, `CLAUDE.md`,
`docs/PROJECT_PLAN.md`, `docs/ERD.md`, `docs/adr/0001`–`0008`).

---

## Executive Summary

### A pergunta central

> "Se eu colocar esse sistema para funcionar hoje, consigo pesquisar empresas reais, obter
> contatos comerciais públicos, identificar oportunidades, transformar essas empresas em leads e
> gerenciar a prospecção de ponta a ponta de forma segura?"

**Não. Nenhuma dessas capacidades existe.**

O que existe hoje é a **fundação**: autenticação por sessão, organizações, RBAC, isolamento de
tenant, auditoria append-only, health checks, logging estruturado, Docker Compose e um pipeline
de CI. O produto — radar, empresas, providers, busca, deduplicação, scanner de site,
oportunidades, score e CRM — **não tem uma única linha de código**.

Isto **não é uma falha de execução**. `docs/PROJECT_PLAN.md:128-143` declara um roteiro de 14
etapas e marca apenas as etapas 1, 2 e 3 como concluídas. A documentação é honesta sobre o estado.
O que esta auditoria acrescenta é o número real e os defeitos que a documentação não menciona.

### Estado real em números

| Medida | Real | Fonte |
|---|---|---|
| Etapas do roteiro concluídas | **3 de 14** | `docs/PROJECT_PLAN.md:128-143` |
| Entidades do ERD implementadas | **4 de 33** | `docs/ERD.md` vs `grep "^class .*Model" apps/*/models.py` |
| Apps de domínio existentes | **2 de 8** | `settings/base.py:43-44` |
| Endpoints de domínio do produto | **0** | `config/urls.py`, `apps/accounts/urls.py` |
| Tasks Celery de negócio | **0** | `grep -rn "shared_task\|@app.task" backend/` |
| Telas do produto | **0** | `frontend/src/app/` |
| Linhas de código (backend, com testes) | 3.528 | `wc -l` |
| Linhas de código (frontend) | 389 | `wc -l` |
| Linhas de documentação | 1.831 | `wc -l *.md docs/*.md docs/adr/*.md` |
| **MVP funcional ponta a ponta** | **~5%** | fundação pronta, produto não iniciado |

As 4 entidades do ERD que existem: `User`, `Organization`, `Membership`, `AuditLog`. Existe ainda
`Invitation`, que não consta do ERD. As 29 ausentes cobrem geografia, empresas, contatos,
categorias, providers, descoberta, análise, oportunidades, score e todo o CRM.

### Veredito por severidade

| Severidade | Quantidade | Natureza |
|---|---|---|
| 🔴 CRÍTICO | 2 | Ambos de processo (versionamento e CI), nenhum de segurança de aplicação |
| 🟠 BLOQUEADOR | 10 etapas | Ausência total das etapas 4–13 |
| 🟡 IMPORTANTE | 12 | 4 defeitos de código verificados + 8 de infra/processo |
| 🔵 MELHORIA | 6 | Qualidade e manutenção |

**Não foi encontrado:** vazamento entre organizações, IDOR/BOLA, segredo versionado, CORS aberto,
SQL por concatenação, `dangerouslySetInnerHTML`, `except Exception: pass`, dado mockado servido
como real, ou qualquer implementação falsamente completa.

---

## Architecture Observed

A arquitetura **encontrada no código** corresponde à documentada, com a ressalva de que 6 dos 8
apps descritos em `ARCHITECTURE.md` não existem.

```
Browser
  │
  ├─ Next.js 15 (App Router)                    frontend/src/
  │    rewrite /api/* → backend                 next.config.ts:18-27
  │    2 rotas: / e /login                      app/page.tsx, app/login/page.tsx
  │    sessão por cookie HTTPOnly, sem token    lib/api.ts:52, lib/auth.ts
  │
  └─ Django 5.1 + DRF                           backend/
       │
       ├─ Middleware (ordem verificada)         settings/base.py:47-59
       │    RequestIDMiddleware                 core/middleware.py:17-42
       │    SecurityMiddleware, CORS, Session, CSRF, Auth
       │    OrganizationMiddleware              accounts/middleware.py:19-34
       │    SecurityHeadersMiddleware (CSP)     core/middleware.py:45-56
       │
       ├─ HTTP: views + serializers             accounts/views.py (383 linhas)
       ├─ Services: regra de negócio            accounts/services.py (131 linhas)
       ├─ Domain / rules                        ⚫ não existe (nenhum app precisa ainda)
       ├─ Persistence: models                   core/models.py, accounts/models.py
       ├─ Integrations: providers               ⚫ não existe
       └─ Tasks: Celery                         config/celery.py — só debug_task
                │
                ├─ PostgreSQL 16 + PostGIS 3.4  settings/base.py:78-84
                │    extensões postgis + pg_trgm criadas por migration
                │    core/migrations/0002_extensions.py:19-22
                └─ Redis 7 (cache + broker)     settings/base.py:88-99
```

### Apps: documentado vs. real

| # | App | `ARCHITECTURE.md` descreve | Existe no código |
|---|---|---|---|
| 1 | `core` | BaseModel, ids, audit, health, middleware, logging | ✅ sim |
| 2 | `accounts` | User, Organization, Membership, Role, auth, sessões | ✅ sim |
| 3 | `geography` | State, City (IBGE), geometrias, importador | ⚫ **não** |
| 4 | `companies` | Company, Address, Contact, Website, Source, Category, CompanyResolver | ⚫ **não** |
| 5 | `providers` | BaseProvider, Overpass, Mock, Credential, Usage | ⚫ **não** |
| 6 | `discovery` | Search, SearchJob, SearchResult, particionamento | ⚫ **não** |
| 7 | `analysis` | WebsiteScan, Finding, guard SSRF, Opportunity, Score | ⚫ **não** |
| 8 | `crm` | Lead, Pipeline, Stage, Interaction, Note, Task, Suppression | ⚫ **não** |

`ARCHITECTURE.md` descreve os 8 apps no tempo presente. Seis não existem. `settings/base.py:43-44`
lista apenas `apps.core` e `apps.accounts` em `INSTALLED_APPS`.

### Regra de dependência

Íntegra, por vacuidade — só existem dois apps, e `accounts` importa `core`
(`accounts/models.py:20-21`), nunca o contrário. Nenhuma dependência circular. Nenhum código
duplicado, nenhuma implementação alternativa da mesma coisa, nenhum arquivo abandonado. Não há
código morto **executável**, mas há **andaime morto** (ver Technical Debt).

---

## Implemented

O que existe e tem evidência de funcionar (ressalvado que a suíte não pôde ser executada —
ver Test Results).

### Fundação (`core`)

| Item | Status | Evidência |
|---|---|---|
| `BaseModel` com PK UUIDv7 + timestamps UTC | ✅ | `core/models.py:12-20` |
| `uuid7()` — implementação real de RFC 9562 | ✅ | `core/ids.py:18-24`: 48 bits de timestamp big-endian, `os.urandom(10)`, byte 6 mascarado para versão 7 (`& 0x0F \| 0x70`), byte 8 para variante (`& 0x3F \| 0x80`). Não é uuid4 disfarçado. `test_ids.py:17` prova ordenação temporal após sleep de 5 ms |
| `timestamp_from_uuid7()` com round-trip | ✅ | `core/ids.py:27-31`, `test_ids.py:31` |
| `AuditLog` append-only | ✅ | `core/models.py:71-122`. Bloqueia em **duas** camadas: instância (`save()` levanta se `not self._state.adding`, `:116-119`; `delete()` sempre levanta, `:121-122`) e queryset (`AppendOnlyQuerySet.delete()/update()`, `:64-68`). Admin read-only (`core/admin.py:15-22`). 5 testes cobrindo os 5 caminhos |
| `record_audit()` — ponto único de auditoria | ✅ | `core/audit.py:30-49`, com `client_ip` (primeiro hop do `X-Forwarded-For`) e guarda contra ator anônimo (`:44`) |
| `RequestIDMiddleware` com sanitização | ✅ | `core/middleware.py:17-42`. Sanitiza para alnum+`-_` e trunca em 64 chars **antes** de chegar em qualquer log. `ContextVar` resetado em `finally` (`:31-35`). `test_middleware.py:18` testa entrada maliciosa |
| Logging JSON com redação de segredos | ✅ | `core/logging.py`. `_SECRET_PATTERN` (`:23-28`) cobre password/senha/token/secret/api_key/authorization/cookie **incluindo o prefixo do esquema** (`Bearer\|Basic\|token\|jwt`), então o valor após o esquema também é mascarado. Redação no filtro, não no call site — a camada certa. 6 testes |
| Health checks | ✅ | `core/health.py`. `live` sem dependências, `ready` com `SELECT 1` + round-trip de cache, 503 em falha, corpo sem host/credencial/traceback. 5 testes |
| Paginação padrão | ✅ | `core/pagination.py`, page_size 25, max 200, aplicada globalmente (`settings/base.py:149-150`) |

### Autenticação e organizações (`accounts`)

| Item | Status | Evidência |
|---|---|---|
| Login por e-mail, sessão em cookie HTTPOnly | ✅ | `views.py:72-104`, `settings/base.py:110-114`. Rotação de sessão testada (`test_auth.py:72`) |
| Mensagem de erro não distingue e-mail inexistente de senha errada | ✅ | `test_auth.py:60` |
| Throttle no login (10/min) e no reset (5/hora) | ✅ | `views.py:74,187,223`, rates em `settings/base.py:156-161`. `test_auth.py:87` verifica 429 |
| Logout encerra sessão no servidor | ✅ | `views.py:108-113`, `test_auth.py:117` |
| Troca de senha derruba outras sessões e mantém a atual | ✅ | `test_auth.py:200` |
| Reset de senha: 204 idêntico para e-mail conhecido e desconhecido | ✅ | `views.py:198`, `test_auth.py:216`. Token nunca no corpo da resposta (`:224`), uso único (`:246`) |
| Convites: token de 256 bits, só o hash SHA-256 no banco | ✅ | `models.py:186,208-227`. Token cru existe uma vez, na resposta da criação. `test_invitations.py:40` verifica que o cru não está em `__dict__` |
| Convite não sobrescreve senha de usuário existente | ✅ | `services.py:73-78` — fecha um caminho de tomada de conta. Regressão testada (`test_invitations.py:140`) |
| Aceite de convite sem corrida de duplo-aceite | ✅ | `services.py:62-66` — `select_for_update()` + re-checagem de `is_usable` |
| RBAC com hierarquia `OWNER > ADMIN > MANAGER > SALES > VIEWER` | ✅ | `models.py:79-100`, `permissions.py:30-49`. `MinRole.at_least()` constrói subclasse dinâmica. 12 testes |
| Guarda do último OWNER (não rebaixa, não remove) | ✅ | `views.py:317-335`, `test_rbac.py:106,118,127` |
| Remoção de membro desativa em vez de apagar | ✅ | `views.py:302-315`, `test_rbac.py:90` |
| Comando `create_organization` como único bootstrap | ✅ | `management/commands/create_organization.py`, `services.py:22-42`. Não existe cadastro público |

### Isolamento de tenant

| Item | Status | Evidência |
|---|---|---|
| Ponto único de imposição | ✅ | `core/viewsets.py:26-30` — `TenantViewSet.get_queryset` filtra por `for_organization()` |
| Responde **404, não 403**, para recurso de outra organização | ✅ | O filtro precede `get_object()`, logo `Http404`. Doutrina documentada (`viewsets.py:16-18`), verificada em GET/PATCH/DELETE (`test_tenancy.py:45,51,61`) |
| `request.organization` vem da sessão, revalidado a cada requisição | ✅ | `accounts/middleware.py:47-67`. Inicializa `None` a cada request (fail-closed, `:24-25`); revalida a escolha da sessão contra a membership ativa (`:57`); descarta escolha inválida (`:61`) |
| Organização **nunca** vem do payload | ✅ | Três barreiras: middleware só lê a sessão (`:54`); `perform_create` sobrescreve (`viewsets.py:29-30`); `InvitationCreateSerializer` não tem o campo (`serializers.py:114-116`). Testado com payload hostil (`test_tenancy.py:86`) e sessão forjada (`:101`) |
| Vínculo revogado perde acesso na requisição seguinte | ✅ | `test_auth.py:153` |
| `for_organization(None)` devolve vazio, nunca tudo | ✅ | `core/models.py:26-29`, `test_tenancy.py:143` — fail-closed |

### Infraestrutura

| Item | Status | Evidência |
|---|---|---|
| Docker Compose completo | ✅ | `docker-compose.yml` — 6 serviços: `db` (postgis/postgis:16-3.4), `redis`, `backend`, `celery_worker`, `celery_beat`, `frontend`. Healthchecks em db/redis/backend, `depends_on: service_healthy` |
| Separação dev/prod sem vazamento | ✅ | Portas de banco e bind-mounts só no `docker-compose.override.yml`; prod usa `-f` explícito |
| Settings de produção com falha na partida | ✅ | `settings/production.py:10-23` — `SECRET_KEY` obrigatória, rejeitada se igual à de dev ou `< 50` chars; `ALLOWED_HOSTS` vazia levanta; CORS com `*` levanta |
| HTTPS obrigatório em produção | ✅ | `production.py:29-37` — SSL redirect, HSTS 1 ano + subdomains + preload, cookies Secure, `SECURE_PROXY_SSL_HEADER` |
| Extensões PostGIS e pg_trgm por migration | ✅ | `core/migrations/0002_extensions.py:19-22` — preparação real para dedup da Etapa 6 |
| Dockerfile backend não-root | ✅ | `backend/Dockerfile:32-33`, uid 1000 |
| Frontend: mesma origem via rewrite | ✅ | `next.config.ts:18-27` proxia `/api/*`, `/admin/*`, `/static/*` |
| TypeScript estrito acima do padrão | ✅ | `tsconfig.json:7-11` — `strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`, `noUnusedLocals`, `noUnusedParameters`. `no-explicit-any: error` e `react/no-danger: error` (`eslint.config.mjs:13,16`) |
| Lint backend severo | ✅ | `pyproject.toml:10-23` — bandit (`S`), blind-except (`BLE`), print esquecido (`T20`), flake8-django (`DJ`) |

---

## Partial

Itens que existem mas não estão completos ou não estão em uso.

| Item | Estado real | Evidência |
|---|---|---|
| **Celery** | 🟡 Infraestrutura pronta, zero trabalho de negócio. App configurado (`config/celery.py:15-17`), exportado (`config/__init__.py`), settings de robustez corretos (`acks_late`, `reject_on_worker_lost`, `prefetch_multiplier=1`, time limits — `base.py:100-106`). Mas existe **exatamente uma task em todo o backend**: `debug_task` (`celery.py:20-22`), cujo docstring diz "usada só na verificação da fundação". **Zero `@shared_task`, zero `.delay()`, zero `.apply_async()`** | `grep -rn "shared_task\|@app.task\|\.delay(\|apply_async" backend/` |
| **Celery Beat** | 🟡 Dois contêineres rodam `celery beat` (`docker-compose.yml:77-86`, `docker-compose.prod.yml:32-38`) com **schedule vazio**. Não existe `beat_schedule` em lugar nenhum e `django-celery-beat` não é dependência. São processos ociosos consumindo recurso | `grep -rn "beat_schedule" backend/` → nada |
| **`TenantModel`** | 🟡 Definido e correto (`core/models.py:32-54`, FK `PROTECT`, índice, `TenantQuerySet`), mas com **zero subclasses concretas**. `Membership` e `Invitation` herdam de `BaseModel` e declaram a própria FK `organization` com **`CASCADE`, não `PROTECT`** (`accounts/models.py:139,182`). A garantia descrita no docstring do `TenantModel` não vale para nenhuma tabela existente | `grep -rn "TenantModel" backend/apps/` |
| **`TenantViewSet.perform_create`** | 🟡 Inalcançável — nenhum dos dois viewsets expõe POST pelo router (`views.py:286` e `:344` restringem `http_method_names`) | `views.py:286,344` |
| **Filtros de API** | 🟡 `DjangoFilterBackend` é o default global (`base.py:151`), mas **nenhum viewset declara `filterset_fields` ou `filterset_class`**, e não há `SearchFilter`/`OrderingFilter`. Zero filtro por query-param é alcançável hoje | `grep -rn "filterset" backend/` → nada |
| **Throttling de domínio** | 🟡 Escopos `search_create` (30/hora) e `analysis` (60/hora) definidos (`base.py:159-160`), nenhuma view os usa. Correto — as views não existem | `grep -rn "throttle_scope" backend/` |
| **`ReadOnlyOrMinRole`** | 🟡 Implementado (`permissions.py:52-63`) e sem nenhum importador. Declarado como o default futuro dos recursos do produto | `grep -rn "ReadOnlyOrMinRole" backend/` |
| **Frontend** | 🟡 Duas rotas reais e funcionais (`/login`, `/`), zero telas do produto. Sem `components/`, `hooks/`, `types/`, `middleware.ts`. Sem `loading.tsx`, `error.tsx`, `not-found.tsx`. Dependências são literalmente `next`, `react`, `react-dom` — nenhuma biblioteca de tabela, mapa ou gráfico | `frontend/src/` (9 arquivos) |
| **Cobertura de teste do frontend** | 🟡 Os 9 testes cobrem **duas funções puras** (`readCookie`, `errorMessage`). `apiFetch`, `login`, `logout`, `getMe` e as duas páginas têm zero cobertura. `vitest.config.ts:5` usa `environment: "node"` e não há jsdom nem `@testing-library/react` — teste de componente não é possível sem adicionar dependência | `frontend/src/lib/*.test.ts` |
| **Recuperação de senha e convite no frontend** | 🟡 Backend expõe `POST /auth/password/reset/` e `POST /auth/invitations/accept/`; o frontend não tem tela nem link para nenhum dos dois | `accounts/urls.py:45,51` vs `frontend/src/app/` |
| **Troca de organização no frontend** | 🟡 Backend expõe `POST /auth/organization/` e `getMe()` devolve `memberships[]`; não há UI de troca | `accounts/urls.py:43`, `lib/auth.ts:29` |

---

## Missing

O que foi planejado e **não existe**. Ausência total: nenhum model, migration, service, serializer,
endpoint, task, tela ou teste.

### Entidades do ERD ausentes — 29 de 33

| Domínio | Entidades ausentes |
|---|---|
| Geografia | `State`, `City` |
| Empresas | `Company`, `CompanyAddress`, `CompanyContact`, `CompanyWebsite`, `CompanySocialProfile`, `CompanySource`, `Category`, `CompanyCategory` |
| Providers | `Provider`, `ProviderCredential`, `ProviderUsage` |
| Descoberta | `Search`, `SearchJob`, `SearchResult` |
| Análise | `WebsiteScan`, `WebsiteFinding`, `OpportunityType`, `Opportunity`, `Score`, `ScoreComponent` |
| CRM | `Pipeline`, `PipelineStage`, `Lead`, `Interaction`, `Note`, `Task`, `SuppressionEntry` |

Confirmado por grep case-insensitive sobre `backend/apps`, `backend/config` e `backend/conftest.py`:
os únicos acertos são strings de configuração para trabalho ainda não escrito —
`base.py:159-160` (escopos de throttle), `base.py:229-237` (`OVERPASS_*`, `WEBSITE_SCAN_*`) e
o comentário `config/urls.py:20` ("Os demais módulos de domínio entram aqui a partir da Etapa 4").

### Capacidades ausentes

| Capacidade | Consequência |
|---|---|
| Importador IBGE (State/City) | Impossível selecionar localização — o fluxo do produto não começa |
| `BaseProvider`, `MockProvider`, `OverpassProvider` | Impossível consultar qualquer fonte de empresas |
| Pipeline de ingestão (Raw → Validate → Normalize → Suppress → Dedup → Resolve → Persist) | ADR-0003 define 7 estágios; nenhum existe |
| `CompanyResolver` (deduplicação) | Os 7 sinais de dedup de `ARCHITECTURE.md` não existem. Sem isto, redescobrir duplica |
| Normalização de telefone E.164 / DDD / +55 | Não há onde armazenar telefone, nem normalização |
| Guard de SSRF | **Pré-requisito de segurança**: `SECURITY.md` e ADR-0003 exigem que os testes de SSRF existam antes do scanner |
| Scanner de site | Sem descoberta de domínio, HTTP/HTTPS, redirects, limites, parsing, findings |
| Opportunity Engine | Nenhum dos tipos (`NO_WEBSITE`, `NO_HTTPS`, `NO_BOOKING`, …) é detectado |
| Scoring Engine + `ScoreComponent` | Não há score, logo não há como responder "por que 92?" |
| CRM: pipeline, estágios, interações, supressão | Nenhum estágio (`NEW`…`WON`/`LOST`/`DO_NOT_CONTACT`) existe |
| `SuppressionEntry` / LGPD opt-out | `SECURITY.md` exige verificação na ingestão; não há ingestão nem supressão |
| Dashboard, Radar, lista de empresas, detalhe, CRM (UI) | Etapa 13 inteira |
| `TODO.md`, `ROADMAP.md` | Não existem. O roteiro vive só na tabela de `docs/PROJECT_PLAN.md:128-143` |

---

## Broken

O que existe mas não funciona como deveria. **Verificado lendo o código.**

### 🟡 B1 — 500 anônimo no confirm de reset de senha

**Arquivo:** `backend/apps/accounts/views.py:247-253`

```python
@staticmethod
def _user_from_uid(uid: str) -> User | None:
    try:
        pk = force_str(urlsafe_base64_decode(uid))
        return User.objects.filter(pk=pk, is_active=True).first()
    except (ValueError, TypeError, User.DoesNotExist):
        return None
```

Um `uid` que é base64 **válido** mas decodifica para uma string que não é UUID — por exemplo
`"YWJj"` → `"abc"` — chega em `User.objects.filter(pk="abc")`. O `UUIDField.to_python` do Django
levanta `django.core.exceptions.ValidationError`, que **não herda de `ValueError`** e portanto não
é capturada. O `exception_handler` do DRF também não trata `ValidationError` do Django (só a do
próprio DRF), então a exceção propaga → **HTTP 500**.

- Endpoint é `AllowAny` (`views.py:222`) — alcançável por qualquer anônimo.
- O teste existente (`test_auth.py:260`, `test_token_de_reset_invalido_e_recusado`) usa um `uid`
  bem-formado e por isso não pega o caso.

**Impacto:** erro 500 não tratado em endpoint público. Não é vazamento de dado (com `DEBUG=False`
o corpo é genérico), mas é ruído de erro, poluição de log e um caminho de exceção não coberto.

### 🟡 B2 — `PATCH` de membro devolve corpo desatualizado e ignora `is_active` em silêncio

**Arquivos:** `backend/apps/accounts/views.py:288-300`, `backend/apps/accounts/serializers.py:98-104`

```python
def perform_update(self, serializer):
    membership = self.get_object()          # segunda instância, diferente da do DRF
    write = sz.MemberWriteSerializer(data=self.request.data, partial=True)
    write.is_valid(raise_exception=True)
    new_role = write.validated_data.get("role", membership.role)
    self._guard_last_owner(membership, new_role=new_role)
    services.change_member_role(membership=membership, new_role=new_role, ...)
```

Dois defeitos numa função:

1. **Resposta desatualizada.** `serializer.save()` nunca é chamado. O `UpdateModelMixin.update()`
   do DRF serializa `serializer.instance` — o objeto que **ele** buscou, não o que `perform_update`
   mutou. A resposta 200 devolve o papel **antigo**, enquanto o banco tem o novo.
2. **Escrita silenciosamente ignorada.** `MemberSerializer.Meta.read_only_fields` é
   `["id", "user", "joined_at"]` (`serializers.py:104`), então `is_active` é **gravável**. Mas o
   caminho de escrita só lê `role` do `MemberWriteSerializer` (`serializers.py:92-95`). Um
   `PATCH {"is_active": false}` responde **200 OK e não faz absolutamente nada**.

O teste `test_admin_altera_papel_de_membro` (`test_rbac.py:64-73`) só verifica o status e a linha
do banco, então passa apesar dos dois defeitos.

**Impacto:** cliente que confia na resposta do `PATCH` mostra dado errado; escrita aceita e
descartada em silêncio é a pior classe de defeito de API.

### 🟡 B3 — Schema e docs da API públicos em produção

**Arquivo:** `backend/config/settings/base.py:164-170`

`SPECTACULAR_SETTINGS` define `TITLE`, `DESCRIPTION`, `VERSION`, `SERVE_INCLUDE_SCHEMA` e
`SCHEMA_PATH_PREFIX`, mas **nunca define `SERVE_PERMISSIONS`**, cujo default no drf-spectacular é
`['rest_framework.permissions.AllowAny']`. Logo `/api/v1/schema/` e `/api/v1/docs/` respondem sem
autenticação em qualquer ambiente, produção incluída.

**Impacto:** divulgação da superfície completa da API a anônimos. Não é brecha de acesso, é
reconhecimento facilitado.

### 🟡 B4 — Fallback de settings é fail-open

**Arquivos:** `manage.py:7`, `config/wsgi.py:5`, `config/asgi.py:5`, `config/celery.py:13`

Os quatro pontos de entrada fazem:

```python
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
```

E `development.py` é `DEBUG = env_bool("DJANGO_DEBUG", True)` (`:7`) com
`ALLOWED_HOSTS = ["*"]` (`:8`).

Hoje a produção está protegida porque `docker-compose.prod.yml:22,30,38` define
`DJANGO_SETTINGS_MODULE: config.settings.production` explicitamente (e `environment:` vence
`env_file:` no Compose). Mas **qualquer deploy fora desse caminho** — gunicorn direto, systemd,
Kubernetes, um `docker run` manual — que esqueça a variável sobe com `DEBUG=True` e
`ALLOWED_HOSTS=["*"]`.

Isso **contradiz diretamente** a afirmação de `DEPLOYMENT.md`:

> "`DEBUG=True` em produção é impossível por construção: `production.py` fixa `DEBUG = False`."

A afirmação só é verdadeira **se** `production.py` for carregado. O fallback é para
`development`, não para `production` — fail-open, não fail-closed.

**Impacto:** o padrão deveria ser o ambiente mais restrito. Um esquecimento de variável não
deveria abrir `DEBUG` e `ALLOWED_HOSTS`.

### Resumo do que **não** está quebrado

Verifiquei especificamente cada padrão de "falsamente completo" solicitado:

| Padrão procurado | Encontrado? |
|---|---|
| Botão existe → handler vazio | ❌ Não. Os dois botões do frontend são funcionais |
| Endpoint existe → retorna mock | ❌ Não |
| Provider existe → sempre retorna `[]` | ❌ Não — provider não existe |
| Scanner existe → não é chamado | ❌ Não — scanner não existe |
| Score existe → valor fixo | ❌ Não — score não existe |
| Dashboard existe → números hardcoded | ❌ Não — dashboard não existe |
| WhatsApp existe → link com telefone inválido | ❌ Não — não há telefone |
| CRM existe → alteração não persiste | ❌ Não — CRM não existe |
| Busca existe → não executa worker | ❌ Não — busca não existe |
| `TODO`/`FIXME`/`HACK`/`XXX` no código | **0 ocorrências** |
| `NotImplementedError` | **0 ocorrências** |
| `placeholder` no código | **0 ocorrências** |
| Dado mockado servido como real | **0 ocorrências** |
| `except Exception: pass` | **0 ocorrências** |

Os únicos dois `except Exception` do backend estão em `core/health.py:48,59`, ambos seguidos de
`logger.exception(...)` e retorno degradado — o uso correto, e o motivo de passarem na regra `BLE`
do ruff.

O frontend declara a própria incompletude no texto visível: *"Etapa 3 concluída. Geografia e
empresas vêm a seguir."* (`frontend/src/app/page.tsx:68`). **O projeto é honesto sobre seu estado.**

---

## Security Findings

### 🔴 CRÍTICO

| # | Achado | Evidência | Impacto |
|---|---|---|---|
| **C1** | **Nenhum arquivo versionado.** `git log` → *"your current branch 'master' does not have any commits yet"*. `git ls-files` → **0**. As ~3.900 linhas das etapas 1–3 existem apenas no disco | `git log`, `git ls-files \| wc -l` | Perda total e irreversível em falha de disco, `git clean`, ou remoção acidental do diretório. Não há backup, não há histórico, não há como reverter nada |
| **C2** | **CI nunca executou.** O workflow dispara em `push: branches: [main]` e `pull_request`. O branch local é `master`, com zero commits, e não existe branch `main` | `.github/workflows/ci.yml:3-6` | Todos os portões — ruff, black, mypy, `makemigrations --check`, 94 testes, `check --deploy`, pip-audit, npm audit — são teóricos. **Ninguém jamais viu este pipeline passar.** Não há evidência alguma de que a suíte esteja verde |

Nenhum dos dois é falha de segurança de aplicação. Ambos são falhas de garantia: o primeiro na
durabilidade do trabalho, o segundo na verificação.

### 🟡 IMPORTANTE

| # | Achado | Evidência |
|---|---|---|
| **B1** | 500 anônimo no confirm de reset (ver *Broken*) | `views.py:247-253` |
| **B3** | `/api/v1/schema/` e `/api/v1/docs/` públicos em produção | `settings/base.py:164-170` |
| **B4** | Fallback de settings é fail-open para `development` (`DEBUG=True`, `ALLOWED_HOSTS=["*"]`) | `manage.py:7`, `wsgi.py:5`, `asgi.py:5`, `celery.py:13` |
| **I2** | Guarda de `.env` no CI tem falso-negativo. A regex `(^\|/)\.env\.[^e]` exclui **qualquer** nome começando por `.env.e`, não só `.env.example`. `.env.encrypted` e `.env.eu-prod` passariam | `.github/workflows/ci.yml:143` |
| **I3** | `gitleaks` existe apenas no pre-commit local; `pre-commit run --all-files` nunca é passo de CI. Não há SAST nem CodeQL | `.pre-commit-config.yaml:42-44` vs `ci.yml` |
| **I5** | Proteção de rota do frontend é só client-side. Sem `middleware.ts`, a página é baixada e o redirect só acontece após o `getMe()` resolver | `frontend/src/app/page.tsx:20-23` |

### Controles verificados como **corretos**

Cada afirmação de `SECURITY.md` foi auditada contra o código:

| Controle | Situação | Evidência |
|---|---|---|
| Sessão em cookie HTTPOnly, sem JWT, sem token em localStorage | ✅ confere | `base.py:110-114`; `lib/api.ts` não guarda token, só `credentials: "include"` (`:52`) |
| `SameSite=Lax` em sessão e CSRF | ✅ confere | `base.py:113,116` |
| `Secure` em produção | ✅ confere | `production.py:33-34`. Ausente em `base.py` — mas `development.py:13-14` desliga explicitamente com justificativa de localhost |
| `CSRF_COOKIE_HTTPONLY = False` | ✅ intencional e documentado — o SPA precisa ler o token | `base.py:115` |
| CSRF ativo, token no header em requisição que altera estado | ✅ confere | `CsrfViewMiddleware` em `base.py:53`; `lib/api.ts:42-46` envia `X-CSRFToken` |
| CORS restrito, `*` recusado em produção | ✅ confere | `base.py:131-132`; `production.py:21-23` levanta `ConfigurationError` |
| `SECRET_KEY` obrigatória em produção, falha na partida | ✅ confere | `production.py:10-15` — rejeita a de dev e qualquer uma com `< 50` chars |
| HSTS com preload, nosniff, Referrer-Policy, X-Frame-Options, CSP | ✅ confere | `production.py:30-32`, `base.py:191-198`. CSP com `script-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'` |
| Hasher do Django, nunca algoritmo próprio | ✅ confere | `models.py:41` usa `set_password`. `PASSWORD_HASHERS` não sobrescrito → PBKDF2-SHA256. MD5 só em `test.py:9` |
| Validação de senha mínima 10 chars (acima do padrão do Django) | ✅ confere | `base.py:121-124` |
| Throttling em login e reset | ✅ confere | `views.py:74,187,223` |
| Logs nunca vazam senha/token/cookie/authorization | ✅ confere | `core/logging.py:23-46`, filtro aplicado no handler (`base.py:218`). 6 testes |
| `request_id` correlaciona requisição e log | ✅ confere | `core/middleware.py:17-42`, sanitizado antes do log |
| Segredo só em variável de ambiente, `.env` fora do Git | ✅ confere | `.gitignore:2-4` (`.env`, `.env.*`, `!.env.example`); `git ls-files \| grep env` → vazio |
| SQL só por ORM | ✅ confere | Nenhuma concatenação de SQL no código |
| `dangerouslySetInnerHTML` | ✅ ausente, e `react/no-danger: error` no lint | `eslint.config.mjs:16` |
| Auditoria append-only, usuário comum não altera | ✅ confere | `core/models.py:61-122`, admin read-only |
| Recurso de outra organização responde 404 | ✅ confere | `core/viewsets.py:26-30`, 12 testes |
| `pip-audit` e `npm audit` no CI, Dependabot ativo | ✅ configurado (mas nunca executado — C2) | `ci.yml:119-145`, `.github/dependabot.yml` |

### Teste de vazamento entre organizações (IDOR/BOLA)

O cenário está **coberto por teste automatizado existente**, em `apps/accounts/tests/test_tenancy.py`:

| Cenário | Teste | Resultado esperado |
|---|---|---|
| Listagem só traz a organização ativa | `:38` | ✅ |
| Detalhe de recurso de outra org | `:45` | **404** |
| Alteração de recurso de outra org | `:51` | **404**, banco inalterado |
| Exclusão de recurso de outra org | `:61` | **404**, banco inalterado |
| Convites não vazam entre orgs | `:69` | ✅ |
| Detalhe de convite alheio | `:78` | **404** |
| Cliente envia `organization` no payload | `:86` | Ignorado; recurso nasce na org ativa |
| Sessão forjada com org alheia | `:101` | Ignorada |
| Usuário em duas orgs vê só a ativa | `:112` | ✅ |
| `for_organization(None)` | `:143` | Vazio, nunca tudo |

**Nenhum vazamento encontrado por leitura de código.** ⚠️ Ressalva obrigatória: estes testes
**não foram executados** (ver *Test Results*), então a conclusão é de revisão estática, não de
execução. Além disso, o mecanismo hoje é exercitado por apenas dois recursos (`Membership`,
`Invitation`) — ADR-0007 exige um teste de isolamento **por model de tenant**, e os models de
tenant do produto ainda não existem.

### Busca por segredos expostos

Procura por `API_KEY`, `SECRET`, `PASSWORD`, `TOKEN`, `PRIVATE_KEY` em todo o repositório.

- **Nenhum segredo no código.** Todas as ocorrências são nomes de variável de ambiente,
  nomes de campo de model, ou strings de teste.
- `.env` está corretamente ignorado (`.gitignore:2`) e não é rastreado.
- Comparação `.env` × `.env.example`: apenas `POSTGRES_PORT` e `REDIS_PORT` diferem (remapeamento
  local de porta). `DJANGO_SECRET_KEY` ainda é o placeholder de desenvolvimento;
  `SENTRY_DSN`, `ANTHROPIC_API_KEY` e `OPENAI_API_KEY` estão **vazios** (comprimento 0).
- `backend/.dockerignore` e `frontend/.dockerignore` excluem `.env*` do contexto de build.

**Nenhuma credencial viva no repositório.** Valores sensíveis não são reproduzidos neste relatório.

---

## Test Results

### Comandos executados

| Comando | Resultado |
|---|---|
| `git log --oneline -20` | `fatal: your current branch 'master' does not have any commits yet` |
| `git ls-files \| wc -l` | `0` |
| `git ls-files \| grep -i env` | vazio (`.env` não rastreado) |
| `git check-ignore -v .env` | `.gitignore:2:.env` |
| `docker ps` | `The command 'docker' could not be found in this WSL 2 distro.` |
| `python3 -c "import django"` | `ModuleNotFoundError: No module named 'django'` |
| `python3 -c "import pytest"` | `ModuleNotFoundError: No module named 'pytest'` |
| `ls backend/.venv` | não existe |
| `grep -rn "def test_" apps/*/tests/*.py \| wc -l` | **94** |
| `grep -rn "shared_task\|@app.task\|\.delay(\|apply_async" backend/` | 1 acerto: `config/celery.py:20` (`debug_task`) |
| `grep -rnE "TODO\|FIXME\|HACK\|XXX\|NotImplementedError" --include='*.py' --include='*.ts' --include='*.tsx'` | **0** |
| `npx --no-install prettier --check .` (frontend) | passa limpo |

### Suítes de teste

| Suíte | Testes | Executado | Resultado |
|---|---|---|---|
| Backend (`pytest`) | **94 funções** (≈100 casos com `parametrize`) | ❌ **não** | ❓ **desconhecido** |
| Frontend (`vitest`) | **9** | ❌ **não** | ❓ **desconhecido** |
| **TOTAL** | **103** | **0 executados** | **0 passaram, 0 falharam, 103 não executados** |

### Por que a suíte não foi executada

Duas razões independentes, ambas verificadas:

1. **Restrição de escopo.** A auditoria correu em modo de planejamento, que proíbe comandos que
   alterem o sistema.
2. **Impossibilidade técnica nesta máquina.** Mesmo sem a restrição, o backend não roda aqui:
   - `docker` não existe nesta distro WSL (mensagem literal acima). Todo o `Makefile` usa
     `docker compose exec`, então **todos** os alvos (`make test`, `make lint`, `make migrate`)
     falham antes de chegar no teste.
   - Não há venv nem Django/pytest instalados no host.
   - `settings/base.py:78-84` usa `postgis://`; `settings/test.py` herda a mesma `DATABASE_URL`.
     **A suíte exige um PostGIS vivo** — não roda com SQLite.

**Não se afirma que os testes passam.** Ninguém executou esta suíte: o CI nunca rodou (C2) e esta
máquina não consegue rodá-la. O estado real é `❓ NÃO FOI POSSÍVEL VALIDAR`.

### Qualidade dos testes (avaliação estática)

Apesar de não executados, os testes são de qualidade acima da média. Não são testes triviais de
fachada:

| Arquivo | Testes | O que realmente ataca |
|---|---|---|
| `test_auth.py` | 26 | Rotação de sessão, mensagem indistinguível entre e-mail inexistente e senha errada, 429 no throttle, token de reset de uso único, troca de senha derrubando outras sessões mas mantendo a atual, vínculo revogado perdendo acesso na requisição seguinte |
| `test_invitations.py` | 13 | Token cru ausente do `__dict__` e da listagem, uso único, expirado, revogado, forjado, e a regressão de tomada de conta (convite não sobrescreve senha de usuário existente) |
| `test_tenancy.py` | 12 | Payload hostil com `organization`, sessão forjada na mão, 404-não-403, `for_organization(None)` fail-closed |
| `test_rbac.py` | 12 (17 casos) | Matriz de papéis parametrizada, guarda do último OWNER, auditoria de mudança de papel |
| `test_audit_log.py` | 5 | Os 5 caminhos de escrita bloqueados, incluindo `queryset.update()` e `queryset.delete()` |
| `test_logging.py` | 6 | Redação incluindo `Authorization: Bearer …` |
| `test_ids.py` | 5 | Bits de versão/variante, ordenação temporal com sleep real — um uuid4 disfarçado falharia |
| `test_health.py` | 5 | 503 com dependência derrubada por `patch` |
| `test_middleware.py` | 5 | `request_id` malicioso sanitizado |
| `test_user.py` | 5 | Normalização de e-mail, hash de senha, unicidade |

`conftest.py:77-87` autentica **pelo endpoint HTTP real**, não por `force_authenticate` — logo
cada teste exercita a cadeia sessão + middleware. Uma fixture autouse limpa o cache em torno de
cada teste para o histórico de throttle não vazar entre eles (`conftest.py:15-26`). É desenho
cuidadoso.

**Lacuna:** os 9 testes do frontend cobrem duas funções puras. `apiFetch` (lógica de CSRF,
`credentials`, sniffing de JSON, lançamento de `ApiError`), `login`, `logout` e sobretudo o ramo
`401 → null` de `getMe()` — que é a lógica que sustenta todo o redirecionamento — têm **zero
cobertura**. Não há teste de componente algum.

### Ferramentas de qualidade

Configuradas e severas, mas **nunca executadas** (C2):

| Ferramenta | Configuração | Executada |
|---|---|---|
| ruff | `pyproject.toml:10-23` — E, W, F, I, N, UP, B, C4, DJ, **S** (bandit), **BLE**, **T20**, RUF | ❌ |
| black | `pyproject.toml:37-40`, line-length 100 | ❌ |
| mypy | `pyproject.toml:42-53`, plugins django + drf, `strict_optional` | ❌ |
| pytest + coverage | `pyproject.toml:55-64` | ❌ |
| eslint | `eslint.config.mjs`, `no-explicit-any: error`, `react/no-danger: error` | ❌ |
| tsc | `tsconfig.json:7-11`, strict + 4 flags extras | ❌ |
| prettier | `.prettierrc` | ✅ passa (único executado) |

---

## MVP Matrix

Legenda de status: ✅ completo e validado · 🟢 implementado com pequenos ajustes · 🟡 parcial ·
🔴 não funcional · ⚫ não implementado · ❓ não foi possível validar

Coluna **Testes**: número de testes automatizados existentes — nenhum executado (ver *Test Results*).

| Módulo | Status | Backend | Frontend | Testes | Integrado | Bloqueadores |
|---|---|---|---|---|---|---|
| **Auth** | 🟢 | ✅ login, logout, me, csrf, troca de senha, reset | ✅ `/login` funcional | 26 ❓ | ✅ ponta a ponta | B1 (500 anônimo no reset); sem tela de "esqueci a senha" |
| **Organizations** | 🟢 | ✅ model, `create_organization`, troca de org | 🟡 só exibe a org ativa | incl. em auth/tenancy ❓ | 🟡 sem UI de troca | I6 (corrida no slug) |
| **RBAC** | 🟢 | ✅ 5 papéis, `MinRole`, guarda do último OWNER | ⚫ nenhuma UI | 12 ❓ | 🟡 backend só | `ReadOnlyOrMinRole` sem uso |
| **Geography** | ⚫ | ⚫ | ⚫ | 0 | ⚫ | Etapa 4 inteira. **Bloqueia todo o fluxo** |
| **Categories** | ⚫ | ⚫ | ⚫ | 0 | ⚫ | Etapa 5 |
| **Companies** | ⚫ | ⚫ | ⚫ | 0 | ⚫ | Etapa 5 |
| **Contacts** | ⚫ | ⚫ | ⚫ | 0 | ⚫ | Etapa 5. Sem telefone, sem E.164, sem WhatsApp |
| **Providers** | ⚫ | ⚫ (só constantes `OVERPASS_*` em `base.py:229-231`) | ⚫ | 0 | ⚫ | Etapa 7. **Nenhum provider funciona hoje** |
| **Discovery** | ⚫ | ⚫ | ⚫ | 0 | ⚫ | Etapa 8 |
| **Search Jobs** | ⚫ | ⚫ | ⚫ | 0 | ⚫ | Etapa 8 |
| **Celery** | 🟡 | 🟡 app configurado, 1 task de debug | n/a | 0 ❓ | 🔴 nenhuma task de negócio | Zero `.delay()`. Beat com schedule vazio |
| **Redis** | 🟢 | ✅ cache + broker configurados, health check | n/a | 2 (via health) ❓ | ✅ | Nunca exercitado sob carga |
| **Deduplication** | ⚫ | ⚫ (só `pg_trgm` criado por migration) | ⚫ | 0 | ⚫ | Etapa 6. Nenhum dos 7 sinais existe |
| **Website Scanner** | ⚫ | ⚫ (só limites em `base.py:235-237`) | ⚫ | 0 | ⚫ | Etapa 9. **Guard de SSRF é pré-requisito** |
| **Opportunities** | ⚫ | ⚫ | ⚫ | 0 | ⚫ | Etapa 10 |
| **Scoring** | ⚫ | ⚫ | ⚫ | 0 | ⚫ | Etapa 11. Não há como responder "por que 92?" |
| **CRM** | ⚫ | ⚫ | ⚫ | 0 | ⚫ | Etapa 12 |
| **Interactions** | ⚫ | ⚫ | ⚫ | 0 | ⚫ | Etapa 12 |
| **Dashboard** | ⚫ | ⚫ | ⚫ (home mostra usuário/org/papel) | 0 | ⚫ | Etapa 13 |
| **Audit Logs** | ✅ | ✅ append-only em 2 camadas, admin read-only | ⚫ nenhuma UI | 5 ❓ | 🟡 backend só | Revogação de convite não audita |
| **Security** | 🟢 | ✅ sessão, CSRF, CORS, HSTS, CSP, throttle, redação de log | 🟡 rota protegida só no cliente | ~20 ❓ | 🟢 | B3 (schema público), B4 (fallback fail-open), I2, I3, I5 |
| **Docker** | 🟢 | ✅ 6 serviços, healthchecks, dev/prod separados | ✅ | n/a | ❓ **não validado** | Docker indisponível nesta máquina. I7, I8 (beat ocioso, worker sem healthcheck) |
| **CI/CD** | 🔴 | ✅ workflow completo e bem escrito | ✅ 5 portões | n/a | 🔴 | **C2: nunca executou.** I1 (cobertura decorativa), I2 |

### Contagem

| Status | Módulos |
|---|---|
| ✅ COMPLETO E VALIDADO | 1 (Audit Logs — validado por leitura, não por execução) |
| 🟢 IMPLEMENTADO COM PEQUENOS AJUSTES | 6 (Auth, Organizations, RBAC, Redis, Security, Docker) |
| 🟡 PARCIAL | 1 (Celery) |
| 🔴 NÃO FUNCIONAL | 1 (CI/CD) |
| ⚫ NÃO IMPLEMENTADO | **14** |
| **Total** | **23** |

---

## End-to-End Flow

O fluxo de MVP definido em `docs/PROJECT_PLAN.md:145-149`:

> login → Radar (Paraná / Londrina / Dentistas) → job em background → empresas encontradas,
> normalizadas, deduplicadas → site identificado ou `NOT_FOUND` → diagnóstico → oportunidades →
> score com breakdown → abrir empresa → anotação → mover no pipeline até venda fechada.

### Estado real, passo a passo

```
LOGIN                          ✅ FUNCIONA
                                  views.py:72-104 + frontend/src/app/login/page.tsx
                                  Sessão em cookie HTTPOnly, CSRF, throttle 10/min
    ↓
DASHBOARD                      ⚫ NÃO EXISTE
                                  A home (page.tsx) mostra usuário, organização e papel.
                                  É prova de sessão, não dashboard. Etapa 13.
    ↓
RADAR                          ⚫ NÃO EXISTE
    ↓
╔═══════════════════════════════════════════════════════════════════════════════════╗
║  ▼▼▼  O FLUXO QUEBRA AQUI  ▼▼▼                                                    ║
║                                                                                   ║
║  SELECIONAR LOCALIZAÇÃO      ⚫ Não há State nem City. Não há importador IBGE.    ║
║                                 Nenhuma tabela de geografia existe.               ║
║                                                                                   ║
║  Este é o primeiro passo do produto depois do login, e ele não existe.            ║
║  Tudo abaixo é ausência total — não é defeito a corrigir, é código a escrever.    ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
    ↓
SELECIONAR SEGMENTO            ⚫ Sem Category
    ↓
CRIAR BUSCA                    ⚫ Sem Search
    ↓
CRIAR JOB                      ⚫ Sem SearchJob
    ↓
WORKER RECEBE JOB              ⚫ Worker sobe, mas não há task de negócio. Zero .delay()
    ↓
PROVIDER É CONSULTADO          ⚫ Sem BaseProvider, sem Overpass, sem Mock
    ↓
RESULTADOS RECEBIDOS           ⚫
    ↓
NORMALIZAÇÃO                   ⚫ Sem BusinessDTO, sem normalize_result
    ↓
DEDUPLICAÇÃO                   ⚫ Sem CompanyResolver. pg_trgm criado, sem uso
    ↓
EMPRESA SALVA/ATUALIZADA       ⚫ Sem Company, sem CompanySource
    ↓
CONTATO COMERCIAL SALVO        ⚫ Sem CompanyContact, sem normalização E.164
    ↓
SITE IDENTIFICADO              ⚫ Sem CompanyWebsite, sem website_status
    ↓
SITE ANALISADO                 ⚫ Sem scanner. E o guard de SSRF, que é pré-requisito
                                  de segurança do scanner, também não existe
    ↓
OPORTUNIDADES IDENTIFICADAS    ⚫ Sem OpportunityType, sem Opportunity
    ↓
SCORE CALCULADO                ⚫ Sem Score, sem ScoreComponent
    ↓
LEAD APARECE NO SISTEMA        ⚫ Sem Lead
    ↓
USUÁRIO ABRE EMPRESA           ⚫ Sem tela
    ↓
VISUALIZA TELEFONE/WHATSAPP    ⚫ Sem telefone
    ↓
REGISTRA CONTATO               ⚫ Sem Interaction
    ↓
CRM                            ⚫ Sem Pipeline, sem PipelineStage
    ↓
REUNIÃO / PROPOSTA             ⚫
    ↓
GANHO / PERDIDO                ⚫
```

### Ponto exato da quebra

**O fluxo quebra no primeiro passo depois do login: SELECIONAR LOCALIZAÇÃO.**

Não é uma integração faltando entre peças existentes. Das 22 etapas do fluxo, **1 funciona**
(login), **1 existe parcialmente como prova de sessão** (a home), e **20 não têm código**.

Isto é importante para calibrar expectativa: não há um "conserto" que faça o fluxo andar. As
etapas 4 a 13 do roteiro precisam ser **escritas**.

### Respostas específicas às áreas destacadas na auditoria

**Providers — quais funcionam hoje?**
**Nenhum.** Não existe `BaseProvider`, `MockProvider` nem `OverpassProvider`. Não existe pacote
`providers`. O que existe são três constantes de configuração em `settings/base.py:229-231`
(`OVERPASS_API_URL`, `OVERPASS_RATE_LIMIT_PER_SECOND`, `OVERPASS_USER_AGENT`) — configuração para
código que não foi escrito. Estrutura preparada não é integração funcional.

**Descoberta — o sistema consegue pesquisar empresas?**
**Não.** Sem `Search`, `SearchJob`, `SearchResult`, sem task Celery, sem provider. Não há criação
de job, envio para fila, processamento, persistência, progresso, erro, retry, cancelamento nem
idempotência — porque não há job. Não faz sentido procurar race condition em código inexistente.

**Deduplicação — como uma empresa é considerada nova/existente/duplicata?**
**Não é.** Não existe `CompanyResolver`. Nenhum dos 7 sinais documentados em `ARCHITECTURE.md`
(`provider+external_id`, CNPJ, domínio, telefone+cidade, nome+proximidade <150 m, similaridade
`pg_trgm`, nada) está implementado. Os casos de teste previstos — mesma empresa por dois
providers, mesmo telefone com nomes diferentes, mesmo nome em cidades diferentes, duas empresas no
mesmo endereço — não têm código contra o qual serem executados. A única preparação real é o
`pg_trgm` criado em `core/migrations/0002_extensions.py:21`.

**Telefone e WhatsApp — conseguimos EMPRESA + TELEFONE + ORIGEM?**
**Não.** Não há `Company`, não há `CompanyContact`, não há normalização brasileira (DDD, +55,
fixo vs. celular), não há campo de origem, tipo ou verificação. Nada a auditar além da ausência.

**Análise de site e SSRF — o scanner é seguro?**
**Não existe scanner.** Consequentemente não existe guard de SSRF. Foi auditado se há alguma
requisição HTTP de saída para URL fornecida pelo usuário em qualquer lugar do backend: **não há
nenhuma**. Hoje o risco de SSRF é **zero por ausência de superfície**. Quando o scanner for
escrito, `SECURITY.md` e ADR-0003 exigem que os testes de SSRF (127.0.0.1, ::1, 10/8, 172.16/12,
192.168/16, 169.254/16 incluindo metadata, fc00::/7, redirect para IP privado, revalidação por
redirect) existam **antes** do código do scanner. Isso é um pré-requisito, não um item de
hardening posterior.

**Opportunity Engine e Score — existem?**
**Não.** Nenhum tipo de oportunidade é detectado. Não há score, logo a pergunta "por que 92?" não
tem mecanismo de resposta. ADR-0008 já define o desenho correto (predicados registrados em código
com `@rule("code")`, pesos e parâmetros no banco, `ScoreComponent` como breakdown auditável,
proibição absoluta de `eval`/`exec`) — falta escrever.

**CRM e `DO_NOT_CONTACT`?**
**Não existe.** Nenhum dos 10 estágios, nenhuma transição, nenhum histórico, nenhum responsável,
nenhuma nota, nenhuma próxima ação. `SuppressionEntry` também não existe, então `DO_NOT_CONTACT`
não impede nada — não há fila automática para impedir.

---

## Technical Debt

### Andaime morto (código correto, sem uso)

| Item | Evidência | Observação |
|---|---|---|
| `TenantModel` sem subclasse concreta | `core/models.py:32-54` | A garantia de `on_delete=PROTECT` do docstring **não vale** para `Membership` nem `Invitation`, que declaram FK própria com `CASCADE` (`accounts/models.py:139,182`). Divergência entre o que o código promete e o que faz |
| `TenantViewSet.perform_create` inalcançável | `core/viewsets.py:29-30` | Nenhum viewset expõe POST pelo router |
| `ReadOnlyOrMinRole` sem importador | `permissions.py:52-63` | Declarado como default futuro |
| Escopos de throttle `search_create` e `analysis` | `settings/base.py:159-160` | Sem view que os use |
| `debug_task` | `config/celery.py:20-22` | Única task do backend; o próprio docstring diz que é só da verificação |
| Constantes `OVERPASS_*` e `WEBSITE_SCAN_*` | `settings/base.py:229-237` | Configuração para código inexistente |
| Dois contêineres `celery_beat` com schedule vazio | `docker-compose.yml:77-86`, `docker-compose.prod.yml:32-38` | Processos ociosos |

Nenhum deles é errado por si — são preparação deliberada. Viram dívida se as etapas correspondentes
não vierem. Vale registrar que `CLAUDE.md` diz *"Não crie um app antes da etapa que o usa. Pacotes
vazios são dívida, não preparo."* — a mesma lógica se aplica a estes.

### Defeitos de qualidade

| # | Item | Evidência |
|---|---|---|
| I1 | Cobertura é portão decorativo: `--cov` sem `--cov-fail-under`, e `[tool.coverage.report]` sem `fail_under`. Cobertura pode cair a 0% e o CI fica verde | `pyproject.toml:55-64`, `ci.yml:76` |
| I4 | `verify-foundation.sh` pode reportar "healthy" falso: `$estado` persiste da iteração anterior. Se `docker compose ps` sair vazio nas 60 tentativas, o valor do serviço **anterior** é reusado. Falso positivo num script de verificação é a classe cara de erro | `scripts/verify-foundation.sh:26` |
| I6 | `Organization._build_unique_slug` usa laço com `.exists()` — corrida sob concorrência. A `UniqueConstraint` do banco protege a integridade, mas o resultado é `IntegrityError` 500 em vez de degradação limpa. Contraria a regra do próprio `CLAUDE.md`: *"Idempotência vem de constraint no banco + `get_or_create`, não de `if exists` em Python"* | `accounts/models.py:124-131` |
| I7 | `celery_beat` sem schedule | `docker-compose.yml:77-86` |
| I8 | `celery_worker` e `celery_beat` sem healthcheck — worker morto aparece como "up". `verify-foundation.sh:19` reconhece a lacuna do beat, mas silenciosamente pula o worker também | `docker-compose.yml:66-86` |
| — | Revogação de convite não grava auditoria, enquanto remoção de membro grava — inconsistência | `views.py:379-383` vs `:307-315` |
| — | Import de `timezone` dentro da função em `perform_destroy` | `views.py:380` |
| — | `logout()` não chama `primeCsrf()` como `login()` faz. Severidade baixa: o cookie CSRF (1 ano) sobrevive à sessão (12 h), então na prática o cookie existe | `frontend/src/lib/auth.ts:53-55` |
| — | Tipos `Me`/`Organization`/`Membership` escritos à mão apesar de `drf-spectacular` estar configurado. Divergência garantida quando a API crescer | `frontend/src/lib/auth.ts:10-30` |
| — | `apiFetch` sem timeout/`AbortSignal`; falha de rede propaga `TypeError` cru, não `ApiError` | `frontend/src/lib/api.ts:38-60` |
| — | `Dockerfile` do backend é single-stage; a imagem de produção carrega `libgdal-dev`/`libproj-dev`. `INSTALL_DEV=false` pula só os pacotes Python | `backend/Dockerfile` |
| — | Dependabot não cobre `docker` em `/frontend` — `node:22-alpine` nunca é atualizado | `.github/dependabot.yml` |
| — | `mirrors-prettier` do pre-commit está em `v4.0.0-alpha.8`, mirror arquivado upstream | `.pre-commit-config.yaml` |
| — | `AuditLog.organization_id` é `UUIDField` puro, não FK — sem integridade referencial (deliberado, para durabilidade do append-only, mas vale registrar) | `core/models.py:94` |
| — | `User` não tem `created_at` (tem `date_joined`), diferente do resto dos models | `accounts/models.py:59-60` |

### Inconsistências na documentação

| # | Inconsistência |
|---|---|
| 1 | **Ingestão de CNPJ da Receita Federal** é tratada como entregável comprometido em ADR-0004 (ponto 3) e citada em `PROJECT_PLAN.md:156` como "Etapa 7+", mas a Etapa 7 do roteiro é "Providers" e **nenhuma etapa menciona CNPJ**. Entregável sem slot |
| 2 | **`make seed` é descrito de três formas diferentes:** README (cria organização de dev e usuário admin, imprime o login), `DEVELOPMENT.md` (cria empresas fictícias, categorias e regras iniciais), ADR-0008 (registra o conjunto inicial de regras) |
| 3 | **`Score` tem cardinalidade contraditória:** o ERD declara `Company \|\|--\|\| Score` (um-para-um estrito), mas `Score` tem campo `version` e ADR-0007 diz que pesos por organização "geram score próprio marcado com a versão da regra" — o que exige N scores por empresa. As duas coisas se excluem como escritas |
| 4 | **`SegmentSolution`** é citado em prosa no ERD ("entra na Etapa 10") sem entrada no diagrama, sem campos e sem constraints. Única entidade planejada sem especificação |
| 5 | **`ARCHITECTURE.md` descreve os 8 apps no presente**; 6 não existem. O README é mais honesto ("core, e os demais conforme as etapas") |
| 6 | **Escopo de tenancy do `AuditLog` conflita:** o ERD marca a seção de Auditoria como 🌐 global, mas a entidade tem `organization_id` e a lista de globais do ADR-0007 não inclui `AuditLog` |
| 7 | **`DEPLOYMENT.md` afirma que `DEBUG=True` em produção é impossível por construção** — falso quando `DJANGO_SETTINGS_MODULE` não é definido, porque o fallback é `development` (defeito B4) |

---

## Production Blockers

O que impede um deploy seguro **hoje**.

### Bloqueadores absolutos

| # | Bloqueador | Por quê |
|---|---|---|
| **P1** | **Não há o que fazer deploy.** O produto não existe — só a fundação | Deployar hoje entrega uma tela de login e uma home que mostra o nome do usuário |
| **P2** | **C1: nada versionado.** Sem commit não há tag, sem tag não há imagem versionada, sem imagem versionada não há rollback | `DEPLOYMENT.md` define rollback como "deploy da tag anterior". Não existe tag alguma |
| **P3** | **C2: CI nunca executou.** Nenhuma evidência de que os 94 testes passem, de que o mypy esteja limpo, ou de que `check --deploy` não acuse nada | Deployar sem nunca ter visto a suíte verde é deployar às cegas |

### Itens de configuração a resolver antes do primeiro deploy

| # | Item | Situação | Ação |
|---|---|---|---|
| 1 | `DEBUG` | ✅ `production.py:7` fixa `False` **quando carregado** | Corrigir B4: fallback deve ser fail-closed |
| 2 | `SECRET_KEY` | ✅ obrigatória, rejeita a de dev e `< 50` chars (`production.py:10-15`) | Gerar e guardar em secret manager |
| 3 | `ALLOWED_HOSTS` | ✅ obrigatória, levanta se vazia (`:17-19`) | Definir |
| 4 | CORS | ✅ `*` recusado (`:21-23`) | Definir origens exatas |
| 5 | CSRF | ✅ `CSRF_TRUSTED_ORIGINS` lido de env (`:25`) | Definir com esquema |
| 6 | HTTPS | ✅ SSL redirect + HSTS preload (`:29-32`) | TLS no proxy reverso |
| 7 | Proxy | ✅ `SECURE_PROXY_SSL_HEADER` (`:37`) | Configurar proxy para enviar `X-Forwarded-Proto` |
| 8 | Static files | ✅ `ManifestStaticFilesStorage` (`:41-43`) | `collectstatic` no deploy |
| 9 | Media | ⚫ Não há upload no projeto | Nada a fazer |
| 10 | Migrations | ✅ 4 migrations, extensões incluídas | `migrate --noinput` |
| 11 | Redis | ✅ configurado, com health check | Provisionar |
| 12 | Workers | 🟡 sobem, mas não têm trabalho; sem healthcheck | I8 |
| 13 | Banco | ✅ PostGIS 16-3.4 | Provisionar |
| 14 | **Backups** | 🔴 **Não configurados.** `DEPLOYMENT.md` documenta o procedimento e exige teste de restore trimestral, mas nada está agendado | Implementar antes de haver dado real |
| 15 | Logs | ✅ JSON estruturado com `request_id` e redação | Coletar em algum lugar |
| 16 | Health checks | ✅ `/health/live` e `/health/ready` | Ligar ao load balancer |
| 17 | Secrets | ✅ só por env, `.env` fora do Git | Usar secret manager |
| 18 | Observabilidade | 🟡 Sentry opcional via `SENTRY_DSN`, desligado | Opcional |
| 19 | **`/api/v1/schema/` e `/docs/`** | 🔴 públicos (B3) | Definir `SERVE_PERMISSIONS` |
| 20 | Portas expostas | 🟡 `docker-compose.prod.yml` não sobrescreve `ports` do backend, então a 8000 continua publicada no host | Fechar ou restringir ao proxy |
| 21 | Limites de recurso | 🔴 Nenhum `deploy`/`resources` no compose de produção; sem rotação de log | Definir |
| 22 | TLS / proxy reverso | 🔴 Nenhum serviço de proxy no compose de produção | Prover |

---

## Recommendations

Em ordem de prioridade real — o que desbloqueia o produto, não o que é mais fácil.

### 1. Segurança crítica e integridade (fazer agora, antes de qualquer código novo)

1. **Commit inicial e CI verde.** Versionar tudo, criar `main`, subir remoto, ver o pipeline passar
   pela primeira vez. Enquanto isso não acontecer, cada etapa nova entra sem verificação e o
   trabalho existente continua sem backup. **Esta é a próxima ação.**
2. **Corrigir B1** (500 anônimo no reset) com teste de `uid` malformado.
3. **Corrigir B2** (`PATCH` mudo): ou aplicar `is_active`, ou torná-lo read-only. Escrita aceita e
   descartada em silêncio é inadmissível. E devolver o corpo correto.
4. **Corrigir B3 e B4:** `SERVE_PERMISSIONS` no drf-spectacular; fallback de settings fail-closed.
5. **Fechar I1–I4:** `fail_under` na cobertura, regex do `.env` no CI, `gitleaks` no CI, `$estado`
   do `verify-foundation.sh`.

### 2. Fluxo principal (a ordem importa — cada etapa depende da anterior)

6. **Etapa 4 — Geografia.** É a raiz: toda busca começa por localização.
7. **Etapas 5–6 — Companies e `CompanyResolver`.** A dedup vem **junto** com o model, não depois.
   Dedup errada corrompe a base de forma que nenhuma correção posterior desfaz — a empresa é a
   entidade permanente do produto.
8. **Etapas 7–8 — Providers e Discovery.** `MockProvider` **antes** do Overpass: ele torna todo o
   pipeline testável sem rede e sem depender de um serviço comunitário. Aqui o Celery finalmente
   ganha trabalho real.
9. **Etapa 9 — SSRF guard, com testes, e só então o scanner.** Não inverter. `SECURITY.md` e
   ADR-0003 tratam isso como pré-requisito, e é a única superfície do produto que expõe a rede
   interna.
10. **Etapas 10–11 — Opportunity Engine e Score.** Seguir ADR-0008 à risca: predicados em código,
    parâmetros no banco, `ScoreComponent` sempre gravado, zero `eval`.
11. **Etapa 12 — CRM.** Histórico append-only; `DO_NOT_CONTACT` gerando `SuppressionEntry` por
    identificador normalizado, verificada na ingestão.
12. **Etapa 13 — Frontend.** Gerar os tipos a partir do schema OpenAPI em vez de escrevê-los à mão.

### 3. Qualidade e produção

13. **Etapa 14 — Hardening.** Índices, N+1, throttling dos endpoints novos, backup **com restore
    testado** antes de existir dado real, limites de recurso, proxy reverso.

### 4. Documentação

14. Resolver as 7 inconsistências listadas em *Technical Debt* — em especial a cardinalidade de
    `Score` (que é decisão de modelagem, não de redação) e a falta de slot para a ingestão de CNPJ.
15. Corrigir a afirmação de `DEPLOYMENT.md` sobre `DEBUG` ser impossível em produção, ou tornar a
    afirmação verdadeira (preferível — é o que a correção de B4 faz).
16. Ajustar `ARCHITECTURE.md` para distinguir arquitetura planejada de implementada.

### Notas de banco e performance

| Item | Classificação | Justificativa |
|---|---|---|
| Índices atuais | ✅ adequados | `created_at`, `(object_type, object_id)`, `(organization_id, -created_at)`, `(organization, role)`, `(organization, email)`. Proporcionais ao volume atual |
| N+1 | ✅ nenhum | Ambos os viewsets usam `select_related` (`views.py:285`, `:346`); o middleware também (`accounts/middleware.py:41`) |
| Paginação | ✅ obrigatória e global | `base.py:149-150` |
| PK UUIDv7 | ✅ decisão correta para o volume alvo | Prefixo temporal dá localidade de inserção no B-tree |
| `pg_trgm` + GIN para dedup | ⚪ **futuro** — extensão já criada, índice entra com a Etapa 6 | Criar índice antes da tabela existir não faz sentido |
| GiST em `CompanyAddress.location` | ⚪ **futuro** — entra com a Etapa 5 | |
| Blocking key antes de comparação de similaridade | 🟠 **necessário na Etapa 6** | `PROJECT_PLAN.md:63-69` já resolveu o desenho; O(n²) é inviável no volume alvo |
| `AddIndexConcurrently` em tabela grande | ⚪ **futuro** | `DEVELOPMENT.md` já documenta a prática |
| Réplica de leitura, particionamento | ⚪ **futuro** — sem medição, é otimização prematura | `DEPLOYMENT.md`: "Não escale por padrão o que ainda não mediu" |

**Nenhuma otimização de banco é necessária agora.** Não há dado, não há consulta, não há medição.

### Dependências

Diagnóstico apenas, sem atualizar nada:

- **Backend:** dependências coerentes com o stack declarado. `pip-audit --strict` está no CI mas
  nunca rodou, então não há resultado de vulnerabilidade para reportar — nem positivo nem negativo.
  Ressalva: `pip-audit` só varre `requirements.txt`, nunca `requirements-dev.txt`.
- **Frontend:** apenas `next`, `react`, `react-dom` em produção. Nada supérfluo, nada abandonado,
  nada duplicado. `npm audit --audit-level=high` está no CI e nunca rodou.
- **Observação sobre o CI:** `pip-audit --strict` e `npm audit --audit-level=high` como estão hoje
  quebram qualquer PR quando um CVE novo aparece em dependência transitiva não relacionada. É um
  portão sobre o mundo, não sobre o diff.

**Nenhuma dependência não utilizada, abandonada ou duplicada foi identificada.**

---

## Conclusão

O projeto está em **~5% do MVP funcional**, e essa é a leitura honesta: 3 de 14 etapas, 4 de 33
entidades, 2 de 8 apps, 0 tasks de negócio, 0 telas de produto.

A distinção que importa: **a fundação é boa, e o produto não começou.** O que foi construído tem
qualidade acima da média — UUIDv7 real, auditoria append-only de verdade, isolamento de tenant com
ponto único de imposição respondendo 404, settings de produção que falham na partida em vez de
degradar em silêncio, e 94 testes que atacam os contornos em vez de confirmar o caminho feliz.

Os problemas reais não são de arquitetura nem de segurança de aplicação. São dois de processo
(nada versionado, CI nunca executado) e quatro defeitos concretos no código existente (B1–B4). Os
dois de processo são os mais urgentes porque o primeiro põe todo o trabalho em risco de perda
total e o segundo significa que **ninguém nunca viu a suíte de testes passar**.

Não há atalho para o restante. As etapas 4 a 13 precisam ser escritas.

Plano de execução em [`docs/IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).
