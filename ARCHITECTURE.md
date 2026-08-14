# Arquitetura

## Visão geral

Monólito modular Django servindo uma API REST versionada (`/api/v1/`), com trabalho pesado em
workers Celery e um frontend Next.js separado. PostgreSQL + PostGIS é a única fonte de verdade.

```
                    ┌──────────────┐
   navegador ──────▶│  Next.js 15  │  rewrite /api/* (mesma origem, cookie de sessão)
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐        ┌─────────────┐
                    │ Django + DRF │───────▶│ PostgreSQL  │ ← fonte de verdade
                    │  /api/v1/    │        │  + PostGIS  │
                    └──────┬───────┘        └─────────────┘
                           │ enfileira              ▲
                    ┌──────▼───────┐                │
                    │    Redis     │                │
                    │ broker/cache │                │
                    │  rate limit  │                │
                    └──────┬───────┘                │
                           │                        │
              ┌────────────▼────────────┐           │
              │  Celery worker / beat   │───────────┘
              │  discovery · scanner    │
              │  scoring · enrichment   │
              └────────────┬────────────┘
                           │ HTTP saída controlada
                    ┌──────▼──────────────────┐
                    │ Providers externos      │
                    │ Overpass/OSM, Mock, ... │
                    └─────────────────────────┘
```

## Camadas

| Camada | Onde | Responsabilidade |
|---|---|---|
| HTTP | `views.py`, `serializers.py`, `urls.py` | Autenticar, validar entrada, serializar saída. **Sem regra de negócio.** |
| Aplicação | `services/` | Orquestra casos de uso, transações, permissões de domínio. |
| Domínio | `domain/`, `rules/` | Regras puras e testáveis sem banco (normalização, matching, score). |
| Persistência | `models.py`, `managers.py` | Schema, constraints, índices, querysets seguros por tenant. |
| Integrações | `providers/`, `clients/` | Chamadas externas, rate limit, retry, normalização para DTO. |
| Tarefas | `tasks.py` | Casca fina do Celery: recebe IDs, chama service, é idempotente. |

Regra prática: se a lógica cabe em teste sem banco, ela pertence ao domínio. Se precisa de
transação, pertence ao service. Se só traduz HTTP, pertence à view.

## Apps e fronteiras

```
core        base, ids, audit, health, middleware, logging, exceptions
accounts    User, Organization, Membership, Role, auth, sessões
geography   State, City (IBGE), geometrias, import de municípios
companies   Company, Address, Contact, Website, SocialProfile, Source, Category,
            normalização, CompanyResolver (dedup)
providers   BaseProvider, OverpassProvider, MockProvider, Credential, Usage, rate limit
discovery   Search, SearchJob, SearchResult, particionamento geográfico, tasks
analysis    WebsiteScan, WebsiteFinding, SSRF guard, Opportunity, Score, rules
crm         Lead, Pipeline, PipelineStage, Interaction, Note, Task, SuppressionEntry
```

Dependência é sempre "para baixo" nessa lista. `companies` não importa `crm`; `crm` importa
`companies`. Import circular é sinal de que a fronteira está errada — resolva movendo a regra,
não com import tardio.

Cada app só expõe o que outros apps podem usar através de `services/` e `models`. Não importe
`_internos` de outro app.

## Fronteira de multi-tenancy (ADR-0007)

| Global (compartilhado) | Da Organization (isolado) |
|---|---|
| `Company` e tudo que descreve a empresa no mundo real: endereços, contatos públicos, sites, perfis sociais, fontes | `Lead`, `Interaction`, `Note`, `Task`, `SuppressionEntry` |
| `WebsiteScan`, `WebsiteFinding` | `Search`, `SearchJob`, `SearchResult` |
| `Opportunity`, `Score` (derivados de dado público) | Configurações, credenciais de provider, regras e pesos customizados |
| `State`, `City`, `Category` | `Organization`, `Membership` |

Modelos de tenant carregam `organization` obrigatório e usam manager que exige o escopo.
Toda query de dado privado passa pelo tenant do request. Existe teste de isolamento — ele
não pode ser removido.

## Fluxo de descoberta

```
Search (usuário: UF/cidades/categoria/quantidade/providers)
  └─▶ particionamento geográfico → N SearchJob (cidade × categoria × provider)
        └─▶ Celery task por job
              ├─ rate limit (Redis) + lock distribuído
              ├─ provider.search_businesses() → resultados brutos
              ├─ validação do payload
              ├─ provider.normalize_result() → DTO comum
              ├─ checagem de supressão (telefone/e-mail/domínio/CNPJ normalizados)
              ├─ CompanyResolver → EXACT / PROBABLE / POSSIBLE / NEW
              ├─ persistência em transação + CompanySource (fonte, data, confiança)
              └─ enfileira análise de site quando houver domínio
```

Jobs registram progresso, contagens (encontradas / novas / duplicadas / falhas), chamadas de
API e custo estimado. Estados: `pending → scheduled → running → {completed, partially_completed,
failed, cancelled}`. Reprocessar o mesmo resultado não pode criar empresa duplicada.

## Fluxo de deduplicação

Nunca por nome isolado. Ordem de sinais, do mais forte ao mais fraco:

1. `provider + external_id` → **EXACT_MATCH** (mesma fonte, mesmo registro)
2. CNPJ normalizado → **EXACT_MATCH**
3. Domínio registrável → **PROBABLE_MATCH**
4. Telefone E.164 + mesma cidade → **PROBABLE_MATCH**
5. Nome normalizado + proximidade geográfica (< 150 m) → **PROBABLE_MATCH**
6. Similaridade de nome (`pg_trgm`) + mesma cidade → **POSSIBLE_MATCH**
7. Nada bate → **NEW_COMPANY**

Antes de comparar, um **blocking key** (cidade + prefixo do nome normalizado, ou raio
geográfico) reduz o universo de candidatos — comparação em massa é feita pelo Postgres com
índice GIN `pg_trgm`, não em Python.

`POSSIBLE_MATCH` **não** faz merge automático: gera um registro de revisão. Merge é operação
transacional, auditada e reversível em intenção (o histórico das fontes é preservado).

## Fluxo de análise de site

```
Company com domínio
  └─▶ task de scan
        ├─ SSRF guard: resolve DNS, valida TODOS os IPs, conecta no IP validado
        ├─ limites: timeout, máx. 3 redirects (revalidados), teto de bytes
        ├─ coleta: status, HTTPS/certificado, tempo de resposta, metadata, viewport,
        │          telefone/WhatsApp, formulário, CTA, agendamento, carrinho, links quebrados
        ├─ WebsiteScan + WebsiteFinding (cada achado com severidade e evidência)
        ├─ Opportunity Engine → oportunidades (NO_WEBSITE, NO_HTTPS, NO_ONLINE_BOOKING, ...)
        └─ Scoring Engine → Score 0–100 + ScoreComponent (breakdown auditável)
```

Sem site identificado: `website_status = NOT_FOUND` e a UI diz *"Site oficial não identificado
nas fontes analisadas"* — nunca "não tem site".

## Fluxo de CRM

`Lead` liga `Organization` + `Company`. Pipeline: `NEW → CONTACTED → REPLIED → QUALIFIED →
MEETING → PROPOSAL → NEGOTIATION → {WON, LOST}` e `DO_NOT_CONTACT` como saída terminal.

Toda mudança de estágio grava histórico append-only (`Interaction` do tipo mudança de status).
Histórico nunca é sobrescrito nem apagado. `DO_NOT_CONTACT` cria `SuppressionEntry` pelos
identificadores normalizados e remove a empresa de qualquer fila automática.

## Observabilidade

- Logs estruturados em JSON com `request_id` propagado (middleware) e filtro que remove
  senha, token, secret e API key.
- `/health/live` (processo vivo, sem dependências) e `/health/ready` (Postgres + Redis).
- `ProviderUsage` registra requests, quota e custo estimado por provider/período.
- Preparado para Sentry via `SENTRY_DSN` (opcional, desligado por padrão).

## O que foi deliberadamente deixado de fora

Kubernetes, Kafka, microserviços, event sourcing, CQRS, service mesh, GraphQL, billing.
Entram só com necessidade comprovada e ADR. Candidatos naturais a virar serviço separado
**quando** houver motivo: Discovery Worker, Website Scanner, AI Service, Analytics — as
fronteiras já estão desenhadas para isso.
