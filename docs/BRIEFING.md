# Briefing — o projeto inteiro, para quem chega agora

> Documento de contexto para uma IA (ou pessoa) que precisa entender este projeto antes de
> mexer nele. **Leia junto com `CLAUDE.md`**, que está na raiz: aqui está o *mapa* (o que
> existe e onde), lá estão as *regras* (o que pode e o que não pode). Regra em conflito:
> `CLAUDE.md` vence.
>
> Estado deste documento: **15/08/2026**, depois da reestruturação de produto e da auditoria
> técnica que a seguiu. O que a auditoria confirmou, o que ela corrigiu e as **quatro lacunas
> que continuam abertas** estão na §12 — comece por ali se for mexer em algo delicado.

---

## 1. O que o produto é, em uma página

**Radar nacional de oportunidades digitais.** Encontra empresas brasileiras, coleta dados
comerciais públicos, analisa a presença digital delas, deduz onde falta alguma coisa (site,
agendamento, e-commerce, WhatsApp), pontua o quanto vale abordar cada uma, e acompanha a
prospecção até a venda.

**Quem usa:** quem vende serviços de tecnologia para pequenas e médias empresas — agência,
software house, freelancer. A pergunta que o produto responde é:

> *Quem, aqui perto, tem lacuna digital e telefone para eu ligar agora?*

**A tese, e ela governa o design inteiro:** *a ausência é o ativo*. A melhor empresa para
abordar é a que tem a **pior** presença digital. Por isso a interface pinta de âmbar o que
**falta** e deixa cinza o que já existe — o inverso de toda barra de progresso.

**O corolário que sustenta a credibilidade:** *"não sei" nunca vira "não tem"*. Empresa nunca
analisada não gera oportunidade nenhuma; sinal de scan que falhou chega como `None`, não como
`False`; a interface hachura o que não foi verificado em vez de pintar como lacuna; e o rótulo
correto é sempre **"Site oficial não identificado nas fontes analisadas"**, nunca "não tem
site". Isto está no `CLAUDE.md` como proibição e tem teste em vários pontos.

**Fluxo do produto:**

```
BUSCAR (fontes externas) → EMPRESA (base permanente) → ANALISAR (site) →
OPORTUNIDADE (regras) → SCORE (prioridade) → CONTATO (telefone/WhatsApp) →
LEAD (relação comercial) → FUNIL → VENDA
```

---

## 2. Stack e como rodar

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, Django 5.1, Django REST Framework |
| Banco | PostgreSQL 16 + PostGIS 3.4 (`django.contrib.gis`), extensão `pg_trgm` (só estas duas — acento é normalizado em Python, por `core.text.normalize_name`) |
| Fila / cache | Celery 5 + Redis 7 |
| Frontend | Next.js 15 (App Router), React 19, TypeScript strict, Tailwind 4 |
| Infra | Docker Compose (dev), containers em qualquer host (prod) |

Tamanho: ~19.000 linhas de Python, ~4.000 de TypeScript, 563 testes de backend e 18 de
frontend (15/08/2026).

```bash
make up          # sobe db, redis, backend, celery_worker, frontend
make migrate
make seed        # dados fictícios
make test        # pytest + vitest
make lint        # ruff + black --check + mypy + eslint + tsc
make format
make logs / make shell / make down
```

### `make test` e `make lint` **não** são o portão inteiro

A CI (`.github/workflows/ci.yml`) roda mais quatro checagens que os alvos do `Makefile` não
cobrem. Passar no `make lint` e quebrar a CI já aconteceu — foi assim que cinco avisos de
schema entraram sem ninguém ver:

```bash
# 1. Migration faltando (pega model alterado sem `makemigrations`)
python manage.py makemigrations --check --dry-run

# 2. Cobertura abaixo do piso (fail_under = 89 em pyproject.toml; hoje está em 94%)
pytest --cov=apps --cov-report=term-missing

# 3. Formatação do frontend (o `make lint` roda eslint e tsc, não o prettier)
npm run format:check

# 4. O portão que mais escapa: checagem de deploy com settings de PRODUÇÃO.
#    `--fail-level WARNING` faz qualquer aviso do drf-spectacular derrubar a CI.
DJANGO_SETTINGS_MODULE=config.settings.production \
DJANGO_SECRET_KEY=chave-de-ci-com-pelo-menos-cinquenta-caracteres-para-passar \
DJANGO_ALLOWED_HOSTS=example.com CORS_ALLOWED_ORIGINS=https://example.com \
CSRF_TRUSTED_ORIGINS=https://example.com \
python manage.py check --deploy --fail-level WARNING
```

Rode os quatro antes de dar qualquer trabalho por concluído.

Serviços: `db`, `redis`, `backend` (:8000), `celery_worker`, `frontend` (:3000).
O frontend faz *rewrite* de `/api/*` para o backend — o navegador vê **uma origem só**, que
é o que torna o cookie de sessão `SameSite=Lax` viável (ADR-0005).

**Ordem de preparo de uma base vazia** (cada comando é idempotente):

```bash
python manage.py create_organization   # a primeira org e o primeiro usuário
python manage.py import_ibge           # 27 estados, 5.571 municípios (não vem no seed)
python manage.py seed_providers        # OSM/Overpass e MockProvider
python manage.py seed_categories       # 48 ramos de atuação + tags de cada fonte
python manage.py seed_opportunity_types
python manage.py seed_score_rules
python manage.py seed_pipeline         # funil padrão da organização
python manage.py seed_dev_data         # só desenvolvimento: dados fictícios (exige DEBUG)
```

`seed_categories` é catálogo de **produto**, e por isso roda em produção. Até 17/08/2026 as
categorias moravam dentro do `seed_dev_data`, que recusa rodar sem `DEBUG=True` — o efeito era
não existir categoria alguma em produção e, portanto, nenhuma busca possível. Adicionar um
ramo é uma linha de dados naquele arquivo; ele usa `update_or_create` para que corrigir uma
tag errada propague, mantendo `is_active` fora do `defaults` (reimportar não reativa o que
alguém desligou no admin). `seed_dev_data` ainda chama `seed_categories`, para o `make seed`
seguir entregando uma base utilizável.

Não existe cadastro público: a primeira organização nasce por comando, os demais usuários
entram por convite.

---

## 3. Arquitetura em uma frase

**Monólito modular Django** com fronteiras de domínio explícitas por app, preparado para
extrair workers no futuro — **mas não separado agora** (ADR-0001).

Camadas: `HTTP (views/serializers)` → `services (regra de negócio)` → `domain` →
`persistence (models)` → `integrations (providers)`. Regra de negócio relevante **nunca** mora
na view.

**Ordem de dependência (não inverta):**

```
core ← accounts ← geography ← companies ← providers ← discovery ← analysis ← crm
```

App de cima importa o de baixo, nunca o contrário. `companies` **não** importa `crm` nem
`analysis`. Quando `companies` precisa de dado desses apps (score, oportunidade, lead), usa o
**nome da relação reversa** que as FKs deles criaram — acoplamento por string resolvido pelo
ORM, não por import. Ver `companies/queries.py`.

### Os oito apps

| App | Responsabilidade |
|---|---|
| `core` | `BaseModel`, `TenantModel`, uuid7, `AuditLog`, health, middleware, logging, `TenantViewSet`, paginação, normalização de texto |
| `accounts` | `User`, `Organization`, `Membership`, `Invitation`, RBAC, autenticação por sessão |
| `geography` | `State`, `City` (IBGE), geometrias |
| `companies` | `Company` + endereços/contatos/sites/categorias, normalização, deduplicação, merge, **o queryset da tela Empresas**, filtros, exportação CSV |
| `providers` | `BaseProvider`, Overpass, Mock, `CompanySource`, uso e rate limit, **ingestão** |
| `discovery` | `Search`, `SearchJob`, `SearchResult`, particionamento, tasks |
| `analysis` | `WebsiteScan`/`Finding`, guard de SSRF, `Opportunity`, `Score` e regras declarativas |
| `crm` | `Lead`, `Pipeline`, `Stage`, `Interaction`, `Note`, `Task`, `SuppressionEntry`, `CompanyList` |

### Decisões travadas (mudar exige ADR novo — `docs/adr/`)

1. Monólito modular. Sem microserviços, Kafka, K8s, CQRS, event sourcing.
2. PostgreSQL + PostGIS é a única fonte de verdade. Redis nunca é.
3. Provider **não escreve no banco**. Pipeline: Raw → Validate → Normalize → Dedup → Resolve → Persist.
4. OSM/Overpass é o provider primário. Dados do Google Places **não** podem ser armazenados.
5. Auth por sessão em cookie HTTPOnly + CSRF. Sem JWT, sem token em `localStorage`.
6. PK é UUIDv7 (`core.ids.uuid7`). Nunca uuid4, nunca int sequencial exposto.
7. **Dado público é global; dado comercial pertence à `Organization`.**
8. Regras de score/oportunidade são predicados registrados em código, parametrizados no banco. Nunca `eval`.

---

## 4. Modelo de dados (o que existe de fato)

`BaseModel` dá a todos: `id` (uuid7), `created_at`, `updated_at`.
`TenantModel` acrescenta `organization` (FK `PROTECT`) e o manager com `for_organization()`.

**Global** (o mesmo para todas as organizações) — `Company` e tudo que descreve o mundo:

```
Category(parent, slug, name, provider_mapping, is_active)
Company(name, normalized_name, legal_name, trade_name, tax_id, description,
        status, website_status, rating, review_count, merged_into,
        discovered_at, last_seen_at, data_quality)
  ├── CompanyAddress(city→geography.City, street, number, district, postal_code,
  │                  location:Point, is_primary, source_ref)
  ├── CompanyContact(kind[PHONE|WHATSAPP|EMAIL], value_raw, value_normalized,
  │                  is_primary, verification_status, confidence)
  ├── CompanyWebsite(url, domain, is_primary, status, last_checked_at)
  ├── CompanySocialProfile(network, url, handle)
  ├── CompanyCategory(category, is_primary, assigned_by)
  ├── CompanySource(provider, external_id, raw_payload, collected_at, expires_at)  ← app providers
  ├── WebsiteScan(status, final_url, http_status, is_https, has_valid_cert,
  │               response_time_ms, has_viewport, has_contact_form, has_whatsapp,
  │               has_booking, has_cart, signals, error_detail) → WebsiteFinding(code, severity, detail)
  ├── Opportunity(type→OpportunityType, status, confidence, evidence, detected_at, resolved_at)
  └── Score(value 0..100, version, computed_at) → ScoreComponent(rule_code, points, reason)

State(ibge_code, uf, name, region) → City(ibge_code, name, normalized_name, centroid)
Provider(slug, name, is_enabled, retention_policy, rate_limit_per_second, daily_quota, config)
OpportunityType(code, name, description, rule_code, rule_params, category_slugs, base_confidence)
ScoreRule(code, name, points, params, reason_template, is_active)
```

**Do tenant** (`organization`) — a relação comercial:

```
Organization → Membership(user, role) → User
Search(name, criteria, status) → SearchJob(city, category, provider, contadores) → SearchResult
Pipeline(name, is_default) → PipelineStage(code, name, position, is_terminal, is_won)
Lead(company, stage, owner, score_snapshot, last_contacted_at, next_action_at)
  ├── Interaction(kind, description, outcome, next_action, occurred_at)   ← APPEND-ONLY
  ├── Note(body)                                                          ← editável
  └── Task(title, due_at, status)
CompanyList(name, description) → CompanyListItem(company, added_by)
SuppressionEntry(identifier_kind, identifier_value, reason)               ← LGPD
ProviderUsage(provider, period, request_count, error_count, estimated_cost)
AuditLog(actor, organization, action, object_type, object_id, changes, ip, request_id)
```

**A fronteira que mais importa (ADR-0007):** `Company` é global — o que a empresa é no mundo
vale para todo mundo. `Lead` é do tenant. Duas organizações prospectando a mesma empresa têm
dois leads e nenhum acesso ao histórico da outra.

---

## 5. Superfície da API (`/api/v1/`)

Autenticação por sessão em todas as rotas (`IsAuthenticated` é o padrão). Paginação padrão de
25, `page_size` até 200. Filtros por `django-filter`.

```
auth/         csrf/ · login/ · logout/ · me/ · organization/ · password/change/
              password/reset/ · password/reset/confirm/ · invitations/accept/
organizations/ members/ · invitations/
geography/    states/ · cities/            (?uf=, ?q= sem acento)
companies/    ← A TELA CENTRAL
                GET  /companies/                 tabela filtrável (ver abaixo)
                GET  /companies/{id}/            ficha com contatos, endereços, sites, redes
                GET  /companies/export/          CSV do recorte (teto 5.000, auditado)
                GET  /companies/categories/      catálogo
providers/    sources/?company=              procedência: fonte, id externo, data, confiança
discovery/    searches/ · searches/preview/ · searches/{id}/cancel|jobs|results · jobs/
analysis/     scans/ · scans/companies/{id}/ (POST reanalisa) · opportunities/ · scores/
crm/          leads/ · leads/{id}/move|interactions|notes
                POST /crm/leads/bulk/            lote no funil (teto 200)
                GET  /crm/leads/summary/         números do painel
              lists/ · lists/{id}/items (POST/DELETE) · lists/{id}/companies · lists/{id}/export
              pipelines/ · suppressions/
health/ · schema/ · docs/  (Swagger)
```

**Filtros de `GET /companies/`** — todos de servidor, e os mesmos nomes aparecem na URL da
tela: `q` (nome, sem acento), `uf`, `city` (ids, CSV), `category` (slugs, CSV),
`site` (`found|not_found|not_checked|broken`), `has_phone`, `has_whatsapp`, `has_email`,
`opportunity` (códigos), `score_min`, `score_max`, `in_crm`, `stage`, `ordering`
(`score_value|name|discovered_at`), `page`, `page_size`.

Cada linha devolve plana: `name, category, city, uf, phone, whatsapp, email, website,
website_status, score, opportunities[], lead_id, lead_stage_code, lead_stage_name, rating,
review_count, discovered_at`.

**Throttling** (escopos em `config/settings/base.py`): `login` 10/min, `password_reset`
5/hora, `search_create` 30/hora, `analysis` 60/hora, `export` 20/hora.

**Papéis:** `OWNER > ADMIN > MANAGER > SALES > VIEWER`, por `MinRole.at_least(...)`.
Criar busca, lead ou lista é `SALES`. Supressão da LGPD é `ADMIN`.

**Ler** o funil é `SALES`; **desenhar** o funil é `MANAGER` (`crm/views.PipelineViewSet.get_permissions`).
A distinção existe porque estava tudo em `MANAGER` e isso quebrava a tela de Leads inteira
para quem vende: a régua de estágios é a primeira coisa que a tela carrega, e sem ela a
página não abre. **Papel de leitura e papel de escrita são perguntas diferentes** — vale para
qualquer viewset novo.

---

## 6. Frontend

Rotas (App Router, `frontend/src/app/`), **tudo em português**:

| Rota | Tela |
|---|---|
| `/` | **Painel** — números da prospecção + melhores oportunidades |
| `/empresas` | **Empresas / Buscar leads** — painel de filtros + tabela + seleção e ações em lote |
| `/empresas/[id]` | Ficha: contato primeiro, lacunas, oportunidades, evidência, score, origem |
| `/leads` | Fila comercial. `?vista=funil` mostra a régua do funil; `?stage=` filtra |
| `/leads/[id]` | Lead: histórico append-only, anotações, mudança de estágio |
| `/listas`, `/listas/[id]` | Listas de trabalho |
| `/buscas` | Descoberta: criar, acompanhar progresso, ver o que rendeu |
| `/configuracoes` | Organização, membros, supressão da LGPD |
| `/login` | Entrada |
| `/crm`, `/crm/[id]` | Redirecionam para `/leads` (`next.config.ts`) |

Componentes (`frontend/src/components/`): `casca.tsx` (sidebar de 240px + gaveta no mobile),
`tabela.tsx` (tabela de empresas com seleção opcional), `filtros.tsx` (painel ↔ query params),
`telefone.tsx` (`Telefone` com copiar, `BotaoWhatsApp`, `formatarTelefone`, `linkDeWhatsApp`,
`Ausente`), `lote.tsx` (barra de ações em massa, fixa no rodapé), `lacunas.tsx`
(`BarraDeLacunas`).

**Primitivos em `components/ui/`** — é aqui que se mexe antes de escrever classe nova:
`botao.tsx` (`Botao`, `BotaoDeIcone`), `campo.tsx` (`Campo`, `Selecao`, `Marcador`,
`ParDeCampos`), `etiqueta.tsx` (`Etiqueta`, `EtiquetaDeEstagio`, `Score`), `superficie.tsx`
(`Cartao`, `Esqueleto`, `EsqueletoDeTabela`, `Vazio`, `Erro`), `cabecalho.tsx`
(`CabecalhoDaPagina`, `CartaoDeMetrica`), `aviso.tsx` (`ProvedorDeAvisos`, `useAviso`).

Auditoria visual e decisões do redesign: `docs/UI_AUDIT.md` e `docs/UI_REDESIGN_REPORT.md`.

Biblioteca (`frontend/src/lib/`): `api.ts` (`apiFetch` com CSRF e cookie), `auth.ts`
(`getMe`, `logout`, `errorMessage`), `recursos.ts` (**uma função por chamada de API** — é aqui
que se acrescenta endpoint novo), `tipos.ts` (espelha os serializers).

Design: fundo papel de escritório (cinza-verde frio), Chivo nos títulos, Archivo no corpo,
Azeret Mono em **todo número** (score, telefone, IBGE, contagem alinham em coluna). Âmbar
`--color-lacuna` só para o que falta. Classe `.entrada` para campo de formulário.

---

## 7. Como as sete mecânicas funcionam

Resumo operacional; o detalhe e o *porquê* de cada uma estão em `CLAUDE.md`.

**1. Descoberta.** `Search` é a intenção; `plan_search` a quebra em `SearchJob`, um por
**cidade × categoria × fonte** — a menor unidade que dá para executar, repetir e reportar
sozinha. Recusa antes de criar o que passar de `DISCOVERY_MAX_JOBS_PER_SEARCH`. `claim_job`
usa `select_for_update` (é ele, não a fila, que garante execução única). Progresso e situação
são **derivados** dos jobs, nunca acumulados. `_classificar` liga a empresa encontrada à
categoria do job (`CompanyCategory`, `assigned_by=PROVIDER`) na mesma transação dos
`SearchResult` — **menos** os `POSSIBLE`, cujo `company_id` é da empresa candidata que o dedup
não confirmou. O catálogo de ramos é `seed_categories` (48 hoje), fora do `seed_dev_data`.

**2. Fontes.** Provider devolve `RawResult` e não toca o banco (ADR-0003); quem valida,
deduplica e persiste é `providers/ingestion.py`. `if provider == "x"` fora de `apps/providers`
significa que a abstração vazou. Busca no Overpass recorta por `IBGE:GEOCODIGO` com
`map_to_area`. `MockProvider` é determinístico e imita as imperfeições do OSM de propósito.

**3. Deduplicação.** `companies/dedup.py` **só lê** e devolve uma `Resolution`. Sinais em
ordem de força: CNPJ (`EXACT`) → domínio → telefone+cidade → similaridade de nome. `POSSIBLE`
nunca funde sozinho. O recorte por município antes de comparar nome é o que torna o problema
tratável. Merge é `companies/services.merge_companies`, atômico, com `select_for_update` antes
de validar; a duplicata vira `status=MERGED` com `merged_into`.

**4. Análise de site.** `analysis/ssrf.safe_get` é o **único** caminho para buscar URL que veio
de fora (site de empresa, redirect, qualquer endereço que uma fonte tenha dito). Conecta no IP
já validado (não no nome — DNS muda entre a checagem e a conexão) e
revalida cada redirect do zero. `status=BLOCKED` é o guard tendo recusado — evento de
segurança, nunca confundir com `UNREACHABLE` (site fora do ar).

**5. Oportunidades e score (ADR-0008).** Predicado em `analysis/rules.py` decorado com
`@rule("codigo")`; peso e parâmetros no banco (`OpportunityType`, `ScoreRule`). **Sem `eval`,
sem `exec`** — há teste que verifica por AST. Regras hoje: `sem_site`, `site_fora_do_ar`,
`site_sem_https`, `site_nao_responsivo`, `site_lento`, `sem_canal_de_contato`,
`sem_agendamento`, `sem_ecommerce`, `sem_whatsapp`, `poucos_contatos`, `da_categoria`.
O score mede **quanto vale ir atrás**, não quão boa é a empresa. Toda parcela grava regra,
pontos e motivo; `Score.version` é hash do conjunto de regras.

**6. CRM e LGPD.** `Interaction` é append-only, inclusive pelo admin — é a prova de que a
abordagem aconteceu. Mudança de estágio entra como `STATUS_CHANGE` gerado pelo serviço. Só
CALL/WHATSAPP/EMAIL/MEETING/PROPOSAL atualizam `last_contacted_at`. A **supressão** morde em
`crm/services.create_lead` e em `log_interaction`, não na ingestão, e encerra os leads abertos
na hora; é por identificador normalizado, nunca por empresa.

O histórico ordena por `["-occurred_at", "-id"]`, e o segundo critério não é enfeite: a
mudança de estágio gerada pelo serviço e a interação registrada pelo usuário caem no mesmo
instante, e sem desempate o Postgres devolvia as duas em ordem arbitrária — o histórico
aparecia de cabeça para baixo de vez em quando. `-id` funciona porque uuid7 é ordenado no
tempo. **Toda ordenação precisa de critério determinístico até o fim.**

**7. Tabela de empresas.** `companies/queries.py` é o único construtor do queryset (usado pela
listagem, pelas listas, pela exportação e pelo painel). Tudo por `Subquery`/`FilteredRelation`
— a contagem de consultas não cresce com o número de linhas, e há teste medindo com 10 e com
30. Filtro multivalorado corta por `Exists` (sem `distinct`), exceto quando o dado mora em app
superior. **`isnull` sobre alias de `FilteredRelation` não vira `IS NULL`**: filtrar "ainda
não é meu lead" é pela anotação `lead_id__isnull`.

---

## 8. Onde mexer para cada tipo de mudança

| Quero… | Mexo em |
|---|---|
| Coluna nova na tabela de empresas | `companies/queries.py` (anotação) + `serializers.CompanyTableSerializer` + `components/tabela.tsx` + `lib/tipos.ts` |
| Filtro novo na tela Empresas | `companies/filters.py` + `components/filtros.tsx` (o nome do parâmetro é o mesmo nos dois) |
| Campo novo na ficha da empresa | `serializers.CompanyDetailSerializer` + `app/empresas/[id]/page.tsx` |
| Regra de oportunidade ou de score | `analysis/rules.py` (predicado) + seed do `OpportunityType`/`ScoreRule`. **Regra nova exige código, de propósito**; ajustar peso é `UPDATE` no banco |
| Fonte de dados nova | `providers/` (subclasse de `BaseProvider` + registro em `registry.py`). Nunca escrever no banco a partir dela |
| Coluna nova no CSV | `companies/export.py` (`COLUNAS`) |
| Estágio novo no funil | `crm/management/commands/seed_pipeline.py` |
| Ramo de comércio novo | `companies/management/commands/seed_categories.py` (`CATEGORIAS`) — uma linha com slug, nome e a tag OSM; depois `python manage.py seed_categories`. Sem migration, sem frontend: o menu e o filtro leem a API |
| Endpoint novo | app correspondente: `views.py` + `serializers.py` + `urls.py`; e `lib/recursos.ts` no frontend. **Rode `check --deploy` depois** (ver §2) |
| `SerializerMethodField` novo | O tipo do schema **não** é inferido: ou anotação de retorno (`-> list[dict[str, str]]`), ou `@extend_schema_field(...)` quando o retorno é `.data` de outro serializer — `ReturnList` faz o mypy recusar a anotação. Sem um dos dois, a CI cai |
| Filtro com `method=` | Passe também `field_name=` apontando para um caminho real do model (ex.: `addresses__city`). Não muda o que o filtro faz; é o que permite o gerador de schema resolver o parâmetro |
| Tela nova | `app/<rota>/page.tsx` + item em `SECOES` de `components/casca.tsx` |
| Task assíncrona | `<app>/tasks.py`. **Reinicie o worker** (o `autodiscover_tasks` roda no boot). As que existem: `discovery.dispatch_search`, `discovery.run_search_job` (com retry só para falha de fonte), `analysis.scan_company_task`, `analysis.scan_website_task` |
| Número no painel | `crm/views.LeadViewSet.summary` + `app/page.tsx` |

---

## 9. Invariantes — quebrar qualquer um destes é bug, não escolha

1. **"Não sei" nunca vira "não tem".** Nem no backend, nem na tela, nem no CSV.
2. **Recurso de outra organização responde 404, não 403.**
3. **Organização nunca vem do payload** — só de `request.organization`, revalidada a cada requisição.
4. **`Interaction` não se altera nem se apaga.**
5. **Nenhuma requisição HTTP a URL influenciada pelo usuário fora de `analysis/ssrf.safe_get`.**
   As duas exceções são de endereço fixo, definido pelo operador em variável de ambiente, e
   não por dado que veio de fora: `providers/overpass.py` e `geography/ibge.py` usam `urlopen`
   direto sobre `OVERPASS_API_URL` e `IBGE_API_URL`, com esquema validado, timeout e teto de
   bytes. Site de empresa — que é endereço vindo de fonte externa — passa **sempre** pelo guard.
6. **Provider não escreve no banco.**
7. **Toda listagem pagina.** Nunca devolver milhares de linhas.
8. **Integridade no banco**, não só na aplicação: `UniqueConstraint`, `CheckConstraint`, FK.
9. **Idempotência vem de constraint + `get_or_create`**, não de `if exists` em Python.
10. **Dinheiro é `Decimal`**, data em UTC no banco, conversão só na apresentação.
11. **Sem `eval`/`exec`** em regra nenhuma.
12. **Nada de `except Exception: pass`** — o lint bloqueia.
13. **Segredo só em variável de ambiente.** `.env` não é versionado.
14. **Não remover nem pular teste para o pipeline passar.**

---

## 10. Armadilhas do ambiente (cada uma já custou tempo)

- **Dependência nova exige `docker compose build`, não `pip install` no container.** São
  imagens separadas por serviço: instalar à mão no `backend` deixa o `celery_worker` sem o
  pacote, e o erro só aparece quando algo roda na fila. Depois de mexer em `requirements*.txt`:
  `docker compose build backend celery_worker`.
- **App novo com tasks exige reiniciar o worker**, senão os jobs ficam parados em `SCHEDULED`
  sem erro visível. O worker de dev tem `watchmedo` para recarregar ao mudar `.py`.
- **Índice de trigrama só é usado pelo operador `%`** (`__trigram_similar`).
  `similarity(x, y) >= 0.6` faz varredura de tabela.
- **Não rode `npm run build` no container que serve `next dev`** — o build de produção
  sobrescreve o `.next/` e todas as rotas passam a dar 500.
- **Build de produção compartilhando tag com o de dev apaga o ambiente de desenvolvimento.**
  Cada serviço do `docker-compose.prod.yml` tem `image: …-prod` por causa disso. Sintoma:
  `sh: next: not found` ou `pytest: not found`. Conserto:
  `docker compose build <serviço> && docker compose up -d -V <serviço>`.
- **`useSearchParams` exige fronteira de `<Suspense>`** no App Router.
- **Calar o mypy pode quebrar a CI.** Remover a anotação de retorno de um
  `SerializerMethodField` resolve o erro de tipo do mypy (`.data` é `ReturnList`, não
  `list[dict]`) e, no mesmo movimento, faz o drf-spectacular cair para `string`, o que derruba
  `check --deploy --fail-level WARNING`. Os dois portões cobram coisas diferentes do mesmo
  ponto: use `@extend_schema_field` quando o retorno vier de outro serializer.
- **Volume anônimo do Docker guarda o conteúdo antigo.** `docker compose up -d` sozinho não o
  recria; sem `-V`, `node_modules` e `.next` continuam com o que veio da imagem errada.

---

## 11. Estado atual e o que não existe (ainda)

**Funciona de ponta a ponta pelo navegador:** login → Empresas com filtros → telefone na linha
→ salvar em lista ou mandar para o CRM → funil até venda fechada. As 14 etapas do roteiro
estão concluídas, e a reestruturação de produto (`docs/PRODUCT_REDESIGN_PLAN.md`) reorganizou
a experiência em torno desse fluxo.

**Deliberadamente fora, com arquitetura pronta para receber:**

- colunas configuráveis pelo usuário na tabela;
- busca em linguagem natural com IA ("clínicas do PR sem site") virando filtros estruturados;
- `Pessoas/Decisores` por empresa (só de fonte legítima — nada de dado pessoal privado);
- enriquecimento por provider (consultar, normalizar, comparar, **nunca sobrescrever em silêncio**);
- buscas salvas e mensagens em massa (nunca spam; abordagem sempre controlada pelo usuário);
- `City.centroid` está nulo de propósito; `City.boundary` não existe;
- mudança de estágio em massa (mover lead gera `Interaction`, é decisão individual).

**Pendências conhecidas:** a CI está configurada mas **nunca completou um passo** — as
execuções do workflow travam por faturamento (conta do GitHub) antes de iniciar qualquer job,
e ficam vermelhas em `main`. O repositório está público desde 14/08 — foi tentativa de
destravar o Actions, e dá para reverter.

---

## 12. O que a auditoria de 15/08 verificou — e o que ficou aberto

Uma auditoria completa conferiu o código contra as regras do `CLAUDE.md` e as afirmações
deste briefing. **28 itens conformes, 3 violados (todos corrigidos), 4 não verificados.**

Confirmado com evidência (arquivo:linha ou saída de comando), para não precisar refazer:

- ordem de dependência entre os 8 apps: **zero** violações fora de testes e migrations;
- nenhum `eval`/`exec`, com teste por AST que passa (`analysis/tests/test_opportunities.py:149`);
- 404 e não 403 entre organizações, com teste em `accounts`, `discovery` e `crm`;
- `organization` só de `request.organization`, revalidada por membership a cada requisição;
- **nenhum segredo nos 18 commits do histórico** — `.env` nunca foi versionado (a varredura
  importa: o repositório é público desde 14/08);
- uuid7 em todos os 33 models e no `User`; 22 `UniqueConstraint` + 13 `CheckConstraint`;
  nenhum `FloatField` no projeto;
- nenhum `except Exception: pass` — os nove `except Exception` logam ou relançam;
- provider não escreve no banco; `dedup.py` só lê; `POSSIBLE` nunca funde sozinho;
- 563 testes de backend + 18 de frontend passando, cobertura 94%, zero `skip`/`xfail`.

O que foi corrigido depois de encontrado:

1. **`check --deploy` da CI falhava** (5 avisos de schema) — consertado com
   `@extend_schema_field`, anotação de retorno e `field_name` nos filtros com `method=`.
2. **Régua do funil exigia `MANAGER` para leitura**, quebrando a tela de Leads para vendedor.
3. **Histórico do lead sem desempate de ordenação** — corrigido com `-id`.

**As quatro lacunas que continuam abertas** (não são "conforme"; são "não sei"):

| Lacuna | O que falta |
|---|---|
| N+1 medido só em `/companies/` | `/crm/leads/`, `/crm/lists/{id}/companies/` e o painel usam as mesmas subconsultas mais um `prefetch_related`, e **nenhum tem teste de contagem de consultas** |
| Guarda de AST é parcial | Cobre `rules.py` e `opportunities.py`, não `scoring.py`. Hoje `scoring.py` está limpo, mas nada impede um `eval` entrar ali sem quebrar teste |
| Produção nunca executou | As settings de produção só passaram pelo `check --deploy`; nada rodou de fato com elas, e nenhuma execução da CI chegou a iniciar um job (trava por faturamento) |
| Guard de SSRF só com dublê | Os 44 testes de `test_ssrf.py` passam, todos com substituto de rede. A proteção nunca foi exercida contra um alvo hostil real |

---

## 13. Antes de mudar qualquer coisa

1. Reler `CLAUDE.md` e o ADR relacionado.
2. Ver o que já existe — não duplicar helper nem serviço (`companies/queries.py`,
   `companies/normalization.py`, `core/text.py`, `crm/services.py` já resolvem muita coisa).
3. Checar impacto: segurança, tenancy, índices, N+1, custo de API externa.
4. Implementar na camada certa (service, não view).
5. `make test` e `make lint` — **e os quatro portões da §2 que eles não cobrem**. Reportar a
   saída real, nunca "deve funcionar".
6. Migration revisada (nada de editar banco à mão).
7. Decisão relevante vira ADR em `docs/adr/`.

**Prioridade quando houver conflito:** Segurança → Integridade dos dados → Manutenibilidade →
Clareza → Testabilidade → Performance → Conveniência.

**A pergunta que decide qualquer dúvida de produto:**

> *Essa alteração torna mais fácil encontrar uma oportunidade comercial e entrar em contato
> com a empresa?* Se não, reavalie a necessidade dela.

---

## 14. Mapa dos documentos

| Arquivo | O que é |
|---|---|
| `CLAUDE.md` | **Memória operacional: as regras.** Leitura obrigatória antes de mudar algo |
| `AGENTS.md` | Porta de entrada para ferramentas de IA: manda ler `CLAUDE.md` e este arquivo, nesta ordem |
| `docs/BRIEFING.md` | Este arquivo: o mapa do que existe e onde |
| `docs/PROJECT_PLAN.md` | Visão de produto e roadmap original |
| `docs/IMPLEMENTATION_PLAN.md` | As 14 etapas, com o que cada uma entregou |
| `docs/PRODUCT_REDESIGN_PLAN.md` | A reestruturação de agosto/2026 e o que ela mudou |
| `docs/ERD.md` | Diagrama de entidades |
| `docs/AUDIT_REPORT.md` | Auditoria de segurança e performance da Etapa 14 |
| `docs/adr/0001..0008` | As oito decisões travadas, com o porquê de cada uma |
| `SECURITY.md` | As sete regras do guard de SSRF |
