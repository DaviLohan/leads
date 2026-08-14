# Plano de execução

Derivado de [`docs/AUDIT_REPORT.md`](AUDIT_REPORT.md) (auditoria de 2026-08-14).

Complementa `docs/PROJECT_PLAN.md`: aquele define **o quê** e **por quê** (roteiro estratégico de
14 etapas); este define **em que ordem**, **com que critério de aceite** e **com quais testes**.

## Princípio de ordenação

Prioridade por **desbloqueio**, não por facilidade:

```
SEGURANÇA CRÍTICA → INTEGRIDADE → FLUXO PRINCIPAL → BACKEND →
INTEGRAÇÕES → FRONTEND → QUALIDADE → OTIMIZAÇÕES → FUTURO
```

Cada tarefa tem: ID · Prioridade · Problema · Objetivo · Arquivos · Dependências · Critério de
aceite · Testes exigidos.

**Legenda de prioridade:** 🔴 CRÍTICO · 🟠 BLOQUEADOR · 🟡 IMPORTANTE · 🔵 MELHORIA · ⚪ FUTURO

---

## Visão geral das fases

| Fase | Nome | Etapas do roteiro | Desbloqueia |
|---|---|---|---|
| **0** | Correções críticas | — | Rede de proteção para todo o resto |
| **1** | Geografia | 4 | O primeiro passo do fluxo do produto |
| **2** | Empresas e deduplicação | 5–6 | A entidade permanente do produto |
| **3** | Descoberta ponta a ponta | 7–8 | O sistema encontra empresa real pela primeira vez |
| **4** | Análise de site | 9 | Diagnóstico digital |
| **5** | Oportunidades e score | 10–11 | O produto passa a ter valor comercial |
| **6** | CRM | 12 | Fecha o ciclo de prospecção |
| **7** | Frontend do produto | 13 | O usuário enxerga o que o backend faz |
| **8** | Produção | 14 | Deploy seguro |

---

# PHASE 0 — Critical Fixes

Nada nesta fase adiciona funcionalidade. Tudo aqui existe para que as fases seguintes sejam
construídas com verificação e sem risco de perda.

---

### TASK GIT-001 — Versionar o projeto e colocar o CI para rodar

**Prioridade:** 🔴 CRÍTICO

**Problema:**
O repositório tem **zero commits**. `git log` responde *"your current branch 'master' does not
have any commits yet"* e `git ls-files` devolve **0 arquivos**. As ~3.900 linhas das etapas 1–3
existem apenas no disco — sem backup, sem histórico, sem possibilidade de reverter nada. Um
`git clean`, um disco perdido ou uma remoção acidental de diretório apaga o projeto inteiro.

Consequência encadeada: `.github/workflows/ci.yml:3-6` dispara em `push: branches: [main]` e em
`pull_request`. O branch local é `master`, não existe `main`, e não há commits. **O CI nunca
executou uma única vez.** Ruff, black, mypy, `makemigrations --check`, 94 testes, `check --deploy`,
pip-audit e npm audit são todos portões teóricos. Ninguém jamais viu este pipeline passar.

**Objetivo:**
Todo o trabalho existente versionado, com remoto configurado, e o pipeline de CI executando e
passando verde pela primeira vez.

**Arquivos/módulos envolvidos:**
- Todo o repositório (primeiro commit)
- `.github/workflows/ci.yml` — alinhar o gatilho ao nome real do branch principal

**Dependências:** nenhuma. É a primeira tarefa do projeto.

**Critério de aceite:**
- [ ] `git log` mostra ao menos um commit
- [ ] `git ls-files | wc -l` > 0 e `.env` **não** aparece na lista
- [ ] O branch principal se chama `main`, ou `ci.yml` foi ajustado para o nome em uso
- [ ] Remoto configurado e `push` concluído
- [ ] **O workflow de CI executou e passou verde**, com os três jobs (`backend`, `frontend`, `seguranca`)
- [ ] A saída real do CI foi lida e reportada — não "deve funcionar"

**Testes exigidos:**
Nenhum teste novo. Esta tarefa **executa** os 103 testes existentes pela primeira vez. Se algum
falhar, a correção entra como tarefa nova antes de qualquer avanço para a Fase 1.

**Nota:** o backend exige PostGIS e Docker. Esta máquina não tem nenhum dos dois (`docker` não
existe nesta distro WSL, e não há Django/pytest instalados). O CI do GitHub Actions provisiona
ambos — por isso o caminho de validação é o CI, não a máquina local.

---

### TASK SEC-001 — Corrigir 500 anônimo no confirm de reset de senha

**Prioridade:** 🟡 IMPORTANTE

**Problema:**
`backend/apps/accounts/views.py:247-253` captura `(ValueError, TypeError, User.DoesNotExist)`, mas
um `uid` que é base64 válido e decodifica para uma string não-UUID — por exemplo `"YWJj"` → `"abc"`
— chega em `User.objects.filter(pk="abc")`. O `UUIDField.to_python` do Django levanta
`django.core.exceptions.ValidationError`, que **não herda de `ValueError`** e não é tratada pelo
`exception_handler` do DRF. Resultado: **HTTP 500 em endpoint `AllowAny`**, acionável por qualquer
anônimo.

O teste existente (`test_auth.py:260`) usa um `uid` bem-formado e não cobre o caso.

**Objetivo:**
`uid` malformado responde 400 com a mesma mensagem genérica de token inválido — sem distinguir
`uid` inválido de token inválido, para não criar oráculo.

**Arquivos/módulos envolvidos:**
- `backend/apps/accounts/views.py:247-253`
- `backend/apps/accounts/tests/test_auth.py`

**Dependências:** `GIT-001` (para que a correção seja verificada pelo CI).

**Critério de aceite:**
- [ ] `POST /api/v1/auth/password/reset/confirm/` com `uid` que decodifica para string não-UUID responde **400**, nunca 500
- [ ] A mensagem é idêntica à de token inválido — sem revelar qual parte falhou
- [ ] `uid` não-base64 continua respondendo 400
- [ ] Nenhum outro caminho do reset foi alterado

**Testes exigidos:**
- `uid` base64 válido decodificando para não-UUID (`"YWJj"`) → 400
- `uid` não-base64 → 400
- Verificação de que a mensagem dos dois casos é igual à do token inválido

---

### TASK API-001 — Corrigir `PATCH` de membro: resposta correta e escrita não ignorada

**Prioridade:** 🟡 IMPORTANTE

**Problema:**
`backend/apps/accounts/views.py:288-300` tem dois defeitos numa função:

1. `perform_update` nunca chama `serializer.save()`. Refaz `self.get_object()`, obtendo uma
   **segunda instância**, e muta essa. O `UpdateModelMixin.update()` do DRF serializa
   `serializer.instance` — o objeto que ele buscou, não o mutado. A resposta 200 devolve o papel
   **antigo** enquanto o banco tem o novo.
2. `is_active` é gravável no `MemberSerializer` (`serializers.py:104` não o lista em
   `read_only_fields`), mas o caminho de escrita só lê `role`. Um `PATCH {"is_active": false}`
   responde **200 OK e não faz nada**.

`test_rbac.py:64-73` só verifica status e linha do banco, então passa apesar dos dois.

**Objetivo:**
A resposta do `PATCH` reflete o estado real após a alteração, e nenhum campo enviado é aceito e
descartado em silêncio.

**Arquivos/módulos envolvidos:**
- `backend/apps/accounts/views.py:288-300`
- `backend/apps/accounts/serializers.py:98-104`
- `backend/apps/accounts/tests/test_rbac.py`

**Dependências:** `GIT-001`.

**Critério de aceite:**
- [ ] `PATCH` de papel devolve no corpo o papel **novo**
- [ ] `is_active` é read-only no serializer **ou** aplicado de fato — decidido explicitamente, nunca ignorado
- [ ] Se read-only: `PATCH {"is_active": false}` não altera nada e a resposta não sugere que alterou
- [ ] A guarda do último OWNER continua funcionando
- [ ] A auditoria de mudança de papel continua sendo gravada

**Testes exigidos:**
- `PATCH` de papel: assertiva sobre o **corpo da resposta**, não só sobre o banco
- `PATCH {"is_active": false}`: comportamento definido e verificado
- Regressão da guarda do último OWNER

---

### TASK SEC-002 — Fechar schema público e tornar o fallback de settings fail-closed

**Prioridade:** 🟡 IMPORTANTE

**Problema:**
Dois defeitos de configuração com a mesma raiz — o padrão é o permissivo:

1. `settings/base.py:164-170` nunca define `SERVE_PERMISSIONS` no `SPECTACULAR_SETTINGS`. O default
   do drf-spectacular é `AllowAny`, então `/api/v1/schema/` e `/api/v1/docs/` respondem sem
   autenticação em produção.
2. `manage.py:7`, `config/wsgi.py:5`, `config/asgi.py:5` e `config/celery.py:13` fazem
   `setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")`, e `development.py` é
   `DEBUG=True` (`:7`) com `ALLOWED_HOSTS=["*"]` (`:8`). Um deploy fora do compose que esqueça a
   variável sobe em modo desenvolvimento. Isto **contradiz** `DEPLOYMENT.md`, que afirma que
   "`DEBUG=True` em produção é impossível por construção".

**Objetivo:**
Schema e docs exigem autenticação em produção; o fallback de settings deixa de abrir `DEBUG` e
`ALLOWED_HOSTS` por esquecimento.

**Arquivos/módulos envolvidos:**
- `backend/config/settings/base.py:164-170`, `development.py`, `production.py`
- `backend/manage.py`, `backend/config/wsgi.py`, `backend/config/asgi.py`, `backend/config/celery.py`
- `DEPLOYMENT.md` — corrigir ou tornar verdadeira a afirmação sobre `DEBUG`

**Dependências:** `GIT-001`.

**Critério de aceite:**
- [ ] `/api/v1/schema/` e `/api/v1/docs/` exigem autenticação com settings de produção
- [ ] Em desenvolvimento continuam acessíveis (produtividade preservada)
- [ ] Sem `DJANGO_SETTINGS_MODULE` definida, a aplicação **não** sobe com `DEBUG=True` e `ALLOWED_HOSTS=["*"]`
- [ ] `manage.py check --deploy --fail-level WARNING` continua limpo
- [ ] A afirmação de `DEPLOYMENT.md` passa a ser verdadeira

**Testes exigidos:**
- Schema e docs sem autenticação com settings de produção → 401/403
- Schema e docs autenticados → 200
- Teste do fallback de settings

---

### TASK CI-001 — Fechar as lacunas dos portões de qualidade

**Prioridade:** 🟡 IMPORTANTE

**Problema:**
Quatro portões existem mas não seguram nada:

- **I1** — `pytest --cov` sem `--cov-fail-under`, e `[tool.coverage.report]` sem `fail_under`
  (`pyproject.toml:55-64`). Cobertura pode cair a 0% e o CI fica verde.
- **I2** — A guarda de `.env` no CI (`ci.yml:143`) usa `(^|/)\.env\.[^e]`, que exclui **qualquer**
  nome começando por `.env.e`, não só `.env.example`. `.env.encrypted` e `.env.eu-prod` passariam.
- **I3** — `gitleaks` existe só no `.pre-commit-config.yaml:42-44`. `pre-commit run --all-files`
  nunca é passo de CI, então só protege quem rodou `pre-commit install`.
- **I4** — `scripts/verify-foundation.sh:26` lê `$estado` da iteração anterior do laço. Se
  `docker compose ps` sair vazio nas 60 tentativas, o valor do serviço **anterior** é reusado e o
  script pode reportar "healthy" falso. Falso positivo em script de verificação é a classe cara.

**Objetivo:**
Cada portão de qualidade realmente reprova o que deveria reprovar.

**Arquivos/módulos envolvidos:**
- `backend/pyproject.toml`
- `.github/workflows/ci.yml`
- `scripts/verify-foundation.sh`

**Dependências:** `GIT-001` (o CI precisa rodar para que os portões importem).

**Critério de aceite:**
- [ ] `fail_under` definido num piso realista medido na primeira execução verde, não chutado
- [ ] Regex do `.env` reprova `.env.encrypted` e aceita `.env.example` — verificado com os dois nomes
- [ ] `gitleaks` roda no CI
- [ ] `verify-foundation.sh` não pode reportar healthy falso; `celery_worker` também é verificado
- [ ] O CI continua verde depois das mudanças

**Testes exigidos:**
- Verificação manual da regex contra `.env`, `.env.example`, `.env.encrypted`, `.env.eu-prod`
- Execução de `verify-foundation.sh` em ambiente com Docker

---

### TASK OPS-001 — Corrigir contêineres e a corrida do slug

**Prioridade:** 🔵 MELHORIA

**Problema:**
- **I7** — `celery_beat` sobe em dois compose (`docker-compose.yml:77-86`,
  `docker-compose.prod.yml:32-38`) com **schedule vazio**. Não existe `beat_schedule` no projeto e
  `django-celery-beat` não é dependência. São processos ociosos consumindo recurso.
- **I8** — `celery_worker` e `celery_beat` não têm healthcheck. Worker morto aparece como "up".
- **I6** — `Organization._build_unique_slug` (`accounts/models.py:124-131`) usa laço com
  `.exists()`. A `UniqueConstraint` protege a integridade, mas o resultado sob concorrência é
  `IntegrityError` 500 em vez de degradação limpa. Contraria a regra do próprio `CLAUDE.md`:
  *"Idempotência vem de constraint no banco + `get_or_create`, não de `if exists` em Python."*
- Revogação de convite não grava auditoria (`views.py:379-383`), enquanto remoção de membro grava.

**Objetivo:**
Nenhum processo ocioso sem justificativa, worker morto detectável, e criação de organização sem
corrida.

**Arquivos/módulos envolvidos:**
- `docker-compose.yml`, `docker-compose.prod.yml`
- `backend/apps/accounts/models.py:119-131`
- `backend/apps/accounts/views.py:379-383`

**Dependências:** `GIT-001`.

**Critério de aceite:**
- [ ] `celery_beat` removido até haver tarefa periódica, **ou** com schedule real definido
- [ ] `celery_worker` com healthcheck (`celery inspect ping`)
- [ ] Criação concorrente de organizações com o mesmo nome não levanta 500
- [ ] Revogação de convite grava auditoria

**Testes exigidos:**
- Criação de organizações com nomes colidentes gerando slugs distintos sem exceção
- Revogação de convite gera `AuditLog`

---

## Portão da Fase 0

**Nenhuma tarefa da Fase 1 começa antes de:**

- [ ] CI verde, com a saída real reportada
- [ ] Número real de testes que passam e falham conhecido — não estimado
- [ ] B1–B4 corrigidos e cobertos por teste

---

# PHASE 1 — Geografia (Etapa 4)

Raiz do fluxo do produto: toda busca começa por localização.

### TASK GEO-001 — App `geography` com `State` e `City`

**Prioridade:** 🟠 BLOQUEADOR

**Problema:** Não existe app `geography`, nem `State`, nem `City`. Sem geografia é impossível
selecionar localização — e o fluxo do produto não passa do login.

**Objetivo:** Modelo geográfico com código IBGE como chave natural e geometria PostGIS.

**Arquivos:** `backend/apps/geography/` (novo), `config/settings/base.py` (`INSTALLED_APPS`),
`config/urls.py`

**Dependências:** Portão da Fase 0. As extensões PostGIS e `pg_trgm` já existem
(`core/migrations/0002_extensions.py`).

**Critério de aceite:**
- [ ] `State`: `ibge_code` único, `uf` único, `name`, `region`
- [ ] `City`: FK para `State`, `ibge_code` único, `name`, `normalized_name`, `centroid` (`PointField` SRID 4326)
- [ ] Ambos herdam de `core.models.BaseModel` (PK uuid7)
- [ ] Índice GiST em `City.centroid`; índice em `normalized_name`
- [ ] Escopo 🌐 global — **não** herdam de `TenantModel` (ADR-0007)
- [ ] Constraints no banco, não só na aplicação
- [ ] Migration revisada

**Testes:** unicidade de `ibge_code`; normalização de nome (acento, caixa, hífen); `centroid` com
SRID correto; PK versão 7.

---

### TASK GEO-002 — Importador IBGE

**Prioridade:** 🟠 BLOQUEADOR

**Problema:** Sem dado, os models de geografia são tabelas vazias.

**Objetivo:** Comando de gestão idempotente que carrega os 27 estados e os ~5.570 municípios.

**Arquivos:** `backend/apps/geography/management/commands/import_ibge.py`,
`backend/apps/geography/services.py`

**Dependências:** `GEO-001`.

**Critério de aceite:**
- [ ] Comando carrega estados e municípios com código IBGE
- [ ] **Idempotente por constraint do banco + `get_or_create`**, nunca por `if exists` em Python
- [ ] Rodar duas vezes não duplica nem levanta exceção
- [ ] Transacional — falha no meio não deixa carga parcial inconsistente
- [ ] Erro externo com timeout, retry limitado e backoff com jitter — nunca retry infinito
- [ ] Progresso reportado; falha registrada em log, nunca engolida
- [ ] Fonte e data de coleta registradas

**Testes:** importação com fixture local (**sem rede**); reimportação não duplica; município com
código inválido é rejeitado; contagem final bate.

---

### TASK GEO-003 — API de geografia

**Prioridade:** 🟠 BLOQUEADOR

**Problema:** O frontend precisa listar estados e municípios para o usuário escolher.

**Objetivo:** Endpoints de leitura, paginados e filtráveis.

**Arquivos:** `backend/apps/geography/{serializers,views,urls}.py`, `config/urls.py`

**Dependências:** `GEO-002`.

**Critério de aceite:**
- [ ] `GET /api/v1/geography/states/` e `GET /api/v1/geography/cities/`
- [ ] Somente leitura
- [ ] Paginação obrigatória (nunca 5.570 municípios numa resposta)
- [ ] Filtro de cidade por estado e busca por nome — **primeiro uso real do `DjangoFilterBackend`**, que hoje está configurado e sem nenhum `filterset`
- [ ] Exige autenticação
- [ ] Sem N+1 (`select_related` no estado)

**Testes:** paginação respeitada; filtro por estado; busca por nome normalizado; anônimo recebe 403;
contagem de queries constante independente do tamanho da página.

---

# PHASE 2 — Empresas e deduplicação (Etapas 5–6)

**A deduplicação vem junto com o model, não depois.** Dedup errada corrompe a base de forma que
nenhuma correção posterior desfaz — a empresa é a entidade permanente do produto
(`PROJECT_PLAN.md:13-15`).

### TASK COMP-001 — Modelo de empresa

**Prioridade:** 🟠 BLOQUEADOR

**Objetivo:** `Company` e satélites conforme `docs/ERD.md`, escopo 🌐 global.

**Arquivos:** `backend/apps/companies/`

**Dependências:** `GEO-003`.

**Critério de aceite:**
- [ ] `Company`, `CompanyAddress`, `CompanyContact`, `CompanyWebsite`, `CompanySocialProfile`, `CompanySource`, `Category`, `CompanyCategory`
- [ ] `UniqueConstraint(provider, external_id)` em `CompanySource` — base da idempotência (ADR-0003)
- [ ] `UniqueConstraint` parcial em `Company.tax_id`, só quando não nulo
- [ ] `UniqueConstraint(company, kind, value_normalized)` em `CompanyContact`
- [ ] Índice GIN `pg_trgm` em `Company.normalized_name`; GiST em `CompanyAddress.location`
- [ ] `website_status` com `NOT_FOUND` — **nunca** um campo que afirme ausência de site
- [ ] Todo dado registra fonte, data de coleta, tipo e confiabilidade (`SECURITY.md`)
- [ ] `companies` **não** importa `crm`

**Testes:** cada constraint verificada no banco; `tax_id` nulo permitido em várias linhas;
`tax_id` repetido não-nulo rejeitado.

---

### TASK COMP-002 — Normalização brasileira

**Prioridade:** 🟠 BLOQUEADOR

**Problema:** Sem normalização, dedup não funciona e telefone é inútil comercialmente.

**Objetivo:** Normalizadores puros e testáveis, sem banco.

**Arquivos:** `backend/apps/companies/domain/normalization.py`

**Dependências:** `COMP-001`.

**Critério de aceite:**
- [ ] **Telefone:** E.164 com +55, DDD validado contra a lista real, distinção fixo/celular, nono dígito
- [ ] **Nunca inventar nem inferir número.** Entrada inválida → rejeitada, não "consertada"
- [ ] WhatsApp só quando a **fonte** o identifica — nunca deduzido de "é celular"
- [ ] **CNPJ:** validação de dígito verificador, armazenamento só de dígitos
- [ ] **Nome:** minúsculas, sem acento, sem pontuação, sem sufixo societário (LTDA, ME, EIRELI, S/A)
- [ ] **Domínio:** domínio registrável, sem `www`, sem esquema, sem path
- [ ] Funções puras, testáveis sem banco e sem rede

**Testes:** telefone fixo e celular de várias regiões; DDD inexistente rejeitado; número curto
rejeitado; CNPJ com DV inválido rejeitado; nomes com acento e sufixo; domínio com subdomínio e
porta.

---

### TASK DEDUP-001 — `CompanyResolver`

**Prioridade:** 🟠 BLOQUEADOR

**Problema:** Sem resolver, redescobrir a mesma empresa cria duplicata — quebrando o princípio
fundamental do produto.

**Objetivo:** Classificação em `EXACT` / `PROBABLE` / `POSSIBLE` / `NEW` pelos 7 sinais de
`ARCHITECTURE.md`, em ordem de força.

**Arquivos:** `backend/apps/companies/services/resolver.py`

**Dependências:** `COMP-002`.

**Critério de aceite:**
- [ ] Sinais na ordem: (1) `provider+external_id` → EXACT · (2) CNPJ → EXACT · (3) domínio → PROBABLE · (4) telefone E.164 + cidade → PROBABLE · (5) nome + proximidade <150 m → PROBABLE · (6) similaridade `pg_trgm` + cidade → POSSIBLE · (7) nada → NEW
- [ ] **`POSSIBLE` nunca faz merge automático** — gera registro de revisão
- [ ] **Blocking key obrigatória** (cidade + prefixo do nome normalizado, ou raio geográfico) antes de qualquer comparação. Comparação par a par é O(n²) e inviável no volume alvo
- [ ] Similaridade calculada **pelo Postgres** com índice GIN, nunca em Python sobre a tabela
- [ ] Merge é transacional, auditado, e preserva o histórico de fontes
- [ ] Idempotência por `UniqueConstraint` + `get_or_create` em transação, não por `if exists`

**Testes — os casos exigidos pela auditoria:**
- [ ] Mesma empresa encontrada duas vezes pelo mesmo provider → EXACT, sem duplicata
- [ ] Mesma empresa encontrada por dois providers diferentes → resolve para uma só
- [ ] Mesmo telefone, nomes ligeiramente diferentes → PROBABLE
- [ ] Mesmo nome em cidades diferentes → **NEW**, jamais merge
- [ ] Duas empresas distintas no mesmo endereço (sala comercial) → **não** faz merge
- [ ] `POSSIBLE` não faz merge automático
- [ ] Dois workers processando o mesmo resultado em paralelo não criam duplicata
- [ ] Blocking key limita o conjunto comparado — verificado por contagem de queries

---

# PHASE 3 — Descoberta ponta a ponta (Etapas 7–8)

Primeiro momento em que o sistema encontra empresa real.

### TASK PROV-001 — `BaseProvider` e `MockProvider`

**Prioridade:** 🟠 BLOQUEADOR

**Problema:** Não existe abstração de provider. Sem `MockProvider`, todo o pipeline fica dependente
de rede e de um serviço comunitário para ser testado.

**Objetivo:** Interface do ADR-0003 e um provider determinístico. **Mock antes do Overpass.**

**Arquivos:** `backend/apps/providers/`

**Dependências:** `DEDUP-001`.

**Critério de aceite:**
- [ ] `BaseProvider(ABC)` exatamente com a interface do ADR-0003: `slug`, `retention_policy`, `search_businesses`, `get_business_details`, `normalize_result`, `check_rate_limit`
- [ ] **Provider nunca importa model nem escreve no banco** — devolve DTO
- [ ] `Provider`, `ProviderCredential` (só `secret_ref`, **nunca** o segredo), `ProviderUsage`
- [ ] `MockProvider` determinístico, sem rede, sem API paga
- [ ] `retention_policy` declarada (`PERSIST` / `EPHEMERAL_30D`)
- [ ] Nenhum `if provider == "x"` fora do pacote `providers` (ADR-0003)

**Testes:** Mock devolve resultado estável; provider não toca no banco; DTO validado; interface
cumprida por todo provider registrado.

---

### TASK PROV-002 — `OverpassProvider`

**Prioridade:** 🟠 BLOQUEADOR

**Objetivo:** Provider primário real (ADR-0004), com uso responsável do endpoint público.

**Arquivos:** `backend/apps/providers/overpass.py`

**Dependências:** `PROV-001`.

**Critério de aceite:**
- [ ] **≤1 req/s**, limitado por Redis
- [ ] Backoff exponencial **com jitter**, máximo de tentativas, timeout — nunca retry infinito
- [ ] User-Agent identificado (exigência do OSM)
- [ ] Endpoint configurável por ambiente
- [ ] `retention_policy = PERSIST` (ODbL permite)
- [ ] Atribuição "© colaboradores do OpenStreetMap" onde o dado aparecer
- [ ] Erro do provider não derruba o job — é registrado
- [ ] **Nenhum teste depende de rede**

**Testes:** limitador respeitado; backoff com jitter; timeout tratado; resposta malformada não
quebra; normalização de payload real capturado em fixture.

---

### TASK DISC-001 — `Search` e `SearchJob`

**Prioridade:** 🟠 BLOQUEADOR

**Objetivo:** Busca particionada em jobs por cidade × categoria × provider.

**Arquivos:** `backend/apps/discovery/`

**Dependências:** `PROV-002`.

**Critério de aceite:**
- [ ] `Search`, `SearchJob`, `SearchResult` — escopo 🔒 **tenant**, herdando de `core.models.TenantModel`
- [ ] **Primeiro uso real do `TenantModel`**, que hoje não tem subclasse concreta
- [ ] Particionamento geográfico usando `City.centroid`
- [ ] `SearchJob` registra progresso, contagens (encontrados/novos/duplicados/erros), chamadas de API, custo estimado, tentativas e último erro
- [ ] Estados: `pending → scheduled → running → {completed, partially_completed, failed, cancelled}`
- [ ] Exposto por `TenantViewSet`; throttle `search_create` (30/hora), hoje definido e sem uso

**Testes:** particionamento gera N jobs esperados; transições de estado válidas e inválidas;
**teste de isolamento por model de tenant** (exigência do ADR-0007).

---

### TASK DISC-002 — Task Celery de descoberta

**Prioridade:** 🟠 BLOQUEADOR

**Problema:**
O worker Celery sobe, mas **não existe nenhuma task de negócio** no backend. A única task é
`debug_task` (`config/celery.py:20-22`), cujo docstring diz que serve só para verificar a fundação.
Não há nenhum `.delay()` nem `apply_async()` em todo o projeto. Criar `SearchJob` sem enfileirá-lo
deixaria o job parado para sempre.

**Objetivo:** Job criado é enfileirado, processado, e o resultado persistido pelo pipeline completo
do ADR-0003.

**Arquivos:** `backend/apps/discovery/tasks.py`, `backend/apps/discovery/services/`

**Dependências:** `DISC-001`.

**Critério de aceite:**
- [ ] Task é **casca fina**: recebe IDs, chama o service, é idempotente (`CLAUDE.md`)
- [ ] Pipeline completo: rate limit + lock → `search_businesses` → validação → normalização → **supressão** → `CompanyResolver` → persistência transacional + `CompanySource` → enfileira análise de site quando houver domínio
- [ ] Lock distribuído em Redis impede processamento duplicado do mesmo job
- [ ] Reprocessar o mesmo resultado **não** cria empresa duplicada
- [ ] Retry limitado com backoff e jitter; falha persistida em `last_error`
- [ ] Cancelamento respeitado
- [ ] Redis é broker e lock — **nunca** fonte de verdade (ADR-0002)

**Testes:**
- [ ] Criar `Search` enfileira os jobs — o defeito clássico de "job criado e nunca enviado"
- [ ] Worker processa e persiste
- [ ] Status muda corretamente em sucesso, falha parcial e falha total
- [ ] Falha é persistida, não engolida
- [ ] Retry funciona e não é infinito
- [ ] **Idempotência:** processar o mesmo job duas vezes não duplica
- [ ] **Concorrência:** dois workers no mesmo job não duplicam
- [ ] Cancelamento interrompe

---

### TASK DISC-003 — `SuppressionEntry` na ingestão

**Prioridade:** 🟡 IMPORTANTE

**Problema:** `SECURITY.md` exige verificação de supressão **antes de persistir e antes de
enfileirar contato**. Suprimir por `company_id` não basta: a mesma empresa reaparece por outra
busca ou outro provider (`PROJECT_PLAN.md:54-61`).

**Objetivo:** Opt-out por identificador normalizado, verificado no pipeline.

**Arquivos:** `backend/apps/crm/models.py` (ou `companies`, conforme a fronteira), pipeline de ingestão

**Dependências:** `DISC-002`.

**Critério de aceite:**
- [ ] `SuppressionEntry` por telefone E.164, e-mail, domínio e CNPJ — **não** só por empresa
- [ ] `UniqueConstraint(organization, identifier_kind, identifier_value)` com índice
- [ ] Verificada **antes** de persistir e **antes** de enfileirar qualquer contato
- [ ] Escopo 🔒 tenant

**Testes:** empresa suprimida por telefone não é persistida ao reaparecer por outro provider;
supressão por domínio; supressão não vaza entre organizações.

---

## Portão da Fase 3 — primeiro marco de produto

- [ ] Criar uma busca (Paraná / Londrina / Dentistas) resulta em empresas reais no banco
- [ ] Empresas normalizadas e deduplicadas
- [ ] Telefone comercial com origem registrada
- [ ] Reexecutar a busca **não** duplica nada

---

# PHASE 4 — Análise de site (Etapa 9)

**A ordem desta fase é inegociável.** `SECURITY.md` e ADR-0003 exigem que os testes de SSRF existam
**antes** do scanner: *"Testes de SSRF são pré-requisito para o scanner existir."*

### TASK SSRF-001 — Guard de SSRF, com testes, antes do scanner

**Prioridade:** 🔴 CRÍTICO (pré-requisito de segurança)

**Problema:**
Hoje o risco de SSRF é **zero por ausência de superfície** — não há nenhuma requisição de saída
para URL fornecida pelo usuário em todo o backend. No instante em que o scanner existir, essa
superfície nasce. Validar a string antes de conectar não protege contra mudança de DNS (TOCTOU)
nem contra redirect.

**Objetivo:** Guard que resolve DNS manualmente, valida **todos** os IPs e conecta no IP validado.

**Arquivos:** `backend/apps/analysis/security/ssrf.py`

**Dependências:** Portão da Fase 3.

**Critério de aceite — os 7 controles do `SECURITY.md`:**
- [ ] Só esquemas `http` e `https` — bloqueia `file:`, `gopher:`, `ftp:`, `data:`
- [ ] Resolução manual do hostname, validando **todos** os IPs devolvidos (A e AAAA)
- [ ] Bloqueia `127.0.0.0/8`, `::1`, `0.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16` (incl. `169.254.169.254`), `fc00::/7`, `fe80::/10`, multicast, reservado, IPv4-mapeado-em-IPv6
- [ ] Conecta no IP **já validado**, enviando o `Host` original — sem deixar a biblioteca re-resolver
- [ ] Revalida a **cada** redirect, máximo de 3
- [ ] Timeout de conexão e de leitura, mais teto de bytes com corte por streaming
- [ ] Nenhum redirect para esquema não-http/https

**Testes — pré-requisito, escritos antes do scanner:**
- [ ] `127.0.0.1`, `localhost`, `::1` bloqueados
- [ ] `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` bloqueados
- [ ] `169.254.169.254` (metadata) bloqueado
- [ ] Hostname público que **resolve** para IP privado é bloqueado
- [ ] Redirect para IP privado é bloqueado na revalidação
- [ ] DNS rebinding: conexão vai ao IP validado, não a uma re-resolução
- [ ] Teto de redirects respeitado
- [ ] Timeout respeitado
- [ ] Resposta maior que o teto de bytes é cortada
- [ ] `file://` e `gopher://` rejeitados

**Este código não entra no branch principal sem estes testes verdes.**

---

### TASK SCAN-001 — Scanner de site

**Prioridade:** 🟠 BLOQUEADOR

**Objetivo:** Coleta de sinais do site, sempre através do guard.

**Arquivos:** `backend/apps/analysis/`

**Dependências:** `SSRF-001` **com todos os testes verdes**.

**Critério de aceite:**
- [ ] `WebsiteScan` e `WebsiteFinding` conforme o ERD, escopo 🌐 global
- [ ] **Nenhuma** requisição de saída fora do guard de SSRF
- [ ] Descoberta de domínio, HTTP/HTTPS, redirects, certificado, tempo de resposta
- [ ] Sinais: título, meta, viewport, formulário de contato, WhatsApp, agendamento, carrinho
- [ ] Cada `WebsiteFinding` com severidade e evidência
- [ ] Task assíncrona, idempotente, com throttle `analysis` (60/hora), hoje definido e sem uso
- [ ] Site não identificado → `website_status = NOT_FOUND` e o texto **"Site oficial não identificado nas fontes analisadas"** — nunca "empresa não tem site"

**Testes:** scan com fixture local (sem rede); site fora do ar; certificado inválido; redirect
encadeado; resposta gigante cortada; `NOT_FOUND` gerado corretamente.

---

# PHASE 5 — Oportunidades e score (Etapas 10–11)

### TASK OPP-001 — Opportunity Engine

**Prioridade:** 🟠 BLOQUEADOR

**Objetivo:** Detecção declarativa de oportunidades, conforme ADR-0008.

**Arquivos:** `backend/apps/analysis/rules/`

**Dependências:** `SCAN-001`.

**Critério de aceite:**
- [ ] Tipos: `NO_WEBSITE`, `BROKEN_WEBSITE`, `NO_HTTPS`, `NO_BOOKING`, `NO_CATALOG`, `NO_ECOMMERCE`, `NO_CONTACT_FORM`, `NO_WHATSAPP_CTA`, `CUSTOM_SYSTEM_OPPORTUNITY`
- [ ] Predicados registrados em código por `@rule("code")`; parâmetros em `OpportunityType.rule_params`
- [ ] **Zero `eval`, zero `exec`, zero expressão em string vinda do banco**
- [ ] Código de regra desconhecido no banco é ignorado com log de aviso — nunca quebra o cálculo
- [ ] Cada oportunidade grava evidência
- [ ] Recalculável sem perder histórico
- [ ] Ambiente sem regras registradas produz resultado vazio, não erro

**Testes:** cada tipo com caso positivo **e** negativo (falso positivo é o risco real); regra
desconhecida não quebra; recálculo é idempotente.

---

### TASK SCORE-001 — Scoring com breakdown

**Prioridade:** 🟠 BLOQUEADOR

**Problema:** Um score "92/100" precisa responder **por que 92**.

**Objetivo:** Score 0–100 com `ScoreComponent` auditável.

**Arquivos:** `backend/apps/analysis/scoring.py`

**Dependências:** `OPP-001`.

**Critério de aceite:**
- [ ] Pesos e parâmetros no banco; predicados em código (ADR-0008)
- [ ] **Toda** avaliação grava `ScoreComponent` com código, pontos e justificativa
- [ ] Score limitado a 0–100 no final
- [ ] A versão do conjunto de regras usado é armazenada
- [ ] Recalculável, com histórico preservado
- [ ] Sem regras registradas → score 0, não erro

**Testes:** soma dos componentes é o score; limite 0–100 respeitado nos extremos; recálculo com
pesos alterados gera versão nova sem apagar a anterior; **breakdown explica o valor** — teste que
reconstrói o total a partir dos componentes.

**Nota de modelagem:** resolver antes a contradição apontada na auditoria — o ERD declara
`Company ||--|| Score` (um-para-um) mas `Score` tem `version` e o ADR-0007 prevê score por
organização. As duas coisas se excluem. Decisão registrada em ADR novo.

---

# PHASE 6 — CRM (Etapa 12)

### TASK CRM-001 — Lead, Pipeline e estágios

**Prioridade:** 🟠 BLOQUEADOR

**Objetivo:** Pipeline comercial por organização.

**Arquivos:** `backend/apps/crm/`

**Dependências:** `SCORE-001`.

**Critério de aceite:**
- [ ] `Pipeline`, `PipelineStage`, `Lead` — escopo 🔒 tenant
- [ ] Estágios: `NEW`, `CONTACTED`, `REPLIED`, `QUALIFIED`, `MEETING`, `PROPOSAL`, `NEGOTIATION`, `WON`, `LOST`, `DO_NOT_CONTACT`
- [ ] `UniqueConstraint(organization, company)` — um lead por empresa por organização
- [ ] Transições válidas verificadas; transição inválida rejeitada
- [ ] Responsável, próxima ação e datas
- [ ] Mudança de estágio em `transaction.atomic`
- [ ] **`DO_NOT_CONTACT` gera `SuppressionEntry` e remove a empresa de toda fila automática**

**Testes:** transições válidas e inválidas; isolamento por organização (obrigatório por model de
tenant); `DO_NOT_CONTACT` impede ação automática; um lead por empresa por organização.

---

### TASK CRM-002 — Interações append-only

**Prioridade:** 🟠 BLOQUEADOR

**Objetivo:** Histórico que não se reescreve.

**Arquivos:** `backend/apps/crm/models.py`

**Dependências:** `CRM-001`.

**Critério de aceite:**
- [ ] `Interaction` com tipos `CALL`, `WHATSAPP`, `EMAIL`, `MEETING`, `NOTE`, `PROPOSAL`, `STATUS_CHANGE`
- [ ] **Append-only** — mesma disciplina do `AuditLog` (`core/models.py:61-122`), bloqueando instância e queryset
- [ ] Mudança de estágio vira `STATUS_CHANGE`, **nunca** sobrescrita
- [ ] `Note` e `Task` com responsável e prazo

**Testes:** update e delete recusados, em instância **e** em queryset; mudança de estágio gera
registro; histórico sobrevive à mudança de estágio.

---

# PHASE 7 — Frontend do produto (Etapa 13)

### TASK FE-001 — Tipos gerados do OpenAPI

**Prioridade:** 🟡 IMPORTANTE

**Problema:** `frontend/src/lib/auth.ts:10-30` tem `Me`, `Organization` e `Membership` escritos à
mão, apesar de `drf-spectacular` estar configurado e servindo o schema. Divergência é garantida
quando a API crescer de 12 para dezenas de endpoints.

**Objetivo:** Tipos derivados do schema, não copiados.

**Dependências:** `SEC-002` (schema autenticado), `CRM-002`.

**Critério de aceite:**
- [ ] Tipos gerados do OpenAPI
- [ ] Geração no `Makefile` e verificada no CI
- [ ] Nenhum tipo de resposta de API escrito à mão
- [ ] `any` continua sendo erro de lint

---

### TASK FE-002 — Proteção de rota e telas do produto

**Prioridade:** 🟠 BLOQUEADOR

**Problema:** A proteção hoje é só client-side (`frontend/src/app/page.tsx:20-23`): a página é
baixada e o redirect só ocorre depois que `getMe()` resolve. Não existe `middleware.ts`.

**Objetivo:** Telas do produto com proteção antes da renderização.

**Dependências:** `FE-001`.

**Critério de aceite:**
- [ ] `middleware.ts` protege as rotas autenticadas
- [ ] Telas: Dashboard, Radar, Empresas, Detalhe da empresa, CRM, Buscas, Configurações
- [ ] Todas consomem a API real — **zero dado mockado, zero número hardcoded**
- [ ] Todo botão tem handler; todo formulário salva
- [ ] Estados de carregamento, vazio e erro em cada tela
- [ ] Telefone e WhatsApp só exibidos quando existem, com origem visível
- [ ] Atribuição do OpenStreetMap onde o dado aparece
- [ ] Nunca exibir "empresa não tem site" — sempre "Site oficial não identificado nas fontes analisadas"
- [ ] Acessibilidade básica: rótulo em campo, `role="alert"` em erro, foco gerenciado
- [ ] Strings em pt-BR

**Testes:** teste de componente por tela (exige adicionar jsdom + testing-library — hoje
`vitest.config.ts:5` usa `environment: "node"` e não há como testar componente); estados de
carregamento, vazio e erro; redirect de não autenticado.

---

### TASK FE-003 — Fechar lacunas do frontend atual

**Prioridade:** 🔵 MELHORIA

**Critério de aceite:**
- [ ] `logout()` chama `primeCsrf()` como `login()` faz (`lib/auth.ts:53-55`)
- [ ] `apiFetch` com timeout/`AbortSignal`; falha de rede vira `ApiError`, não `TypeError` cru
- [ ] Telas de "esqueci a senha" e de aceite de convite — endpoints já existem no backend
- [ ] UI de troca de organização — endpoint já existe
- [ ] Testes para `apiFetch`, `login`, `logout` e o ramo `401 → null` de `getMe()`, hoje sem cobertura

---

# PHASE 8 — Produção (Etapa 14)

### TASK PROD-001 — Backup com restore testado

**Prioridade:** 🔴 CRÍTICO (antes de existir dado real)

**Problema:** `DEPLOYMENT.md` documenta o procedimento e exige teste de restore trimestral, mas
**nada está agendado**. Backup nunca restaurado não é backup.

**Critério de aceite:**
- [ ] Dump diário automatizado, retenção de 30 dias, armazenado **fora** do host da aplicação
- [ ] **Restore testado de fato**, em ambiente separado, com a aplicação subindo contra ele
- [ ] Data e resultado de cada teste registrados

---

### TASK PROD-002 — Hardening de deploy

**Prioridade:** 🟡 IMPORTANTE

**Critério de aceite:**
- [ ] Porta 8000 do backend não publicada diretamente no host em produção
- [ ] Limites de recurso e rotação de log no compose de produção
- [ ] Proxy reverso com TLS
- [ ] `Dockerfile` do backend multi-stage — hoje a imagem de produção carrega `libgdal-dev`/`libproj-dev`
- [ ] Dependabot cobrindo `docker` em `/frontend`
- [ ] `manage.py check --deploy --fail-level WARNING` limpo
- [ ] Checklist de primeiro deploy do `DEPLOYMENT.md` percorrido

---

### TASK PROD-003 — Performance sob evidência

**Prioridade:** 🔵 MELHORIA

**Regra:** nenhuma otimização sem medição. A auditoria não encontrou N+1 nem índice ausente no
código atual.

**Critério de aceite:**
- [ ] Consultas medidas com volume realista antes de qualquer índice novo
- [ ] N+1 verificado por contagem de queries nos endpoints de listagem
- [ ] Blocking key da dedup validada em escala
- [ ] Filas Celery separadas por tipo de trabalho **quando houver medição** que justifique
- [ ] Cada otimização com número antes/depois

---

### TASK DOC-001 — Resolver as inconsistências da documentação

**Prioridade:** 🔵 MELHORIA

**Critério de aceite:**
- [ ] Cardinalidade de `Score` resolvida em ADR novo (é decisão de modelagem, não de redação)
- [ ] Ingestão de CNPJ ganha etapa no roteiro, ou o ADR-0004 é ajustado
- [ ] `make seed` descrito de uma forma só nos três documentos
- [ ] `SegmentSolution` especificado ou removido
- [ ] `ARCHITECTURE.md` distingue arquitetura planejada de implementada
- [ ] Escopo de tenancy do `AuditLog` alinhado entre ERD e ADR-0007
- [ ] Afirmação do `DEPLOYMENT.md` sobre `DEBUG` corrigida — ou tornada verdadeira por `SEC-002`

---

# NEXT ACTION

**Executar `TASK GIT-001`: versionar o projeto e colocar o CI para rodar pela primeira vez.**

### Por que esta, e não a Etapa 4

1. **É o único achado da auditoria em que a perda é total e irreversível.** ~3.900 linhas de código
   de boa qualidade existem apenas no disco, sem commit. Todo o resto do plano assume que esse
   trabalho continua existindo.

2. **Ninguém sabe se os 94 testes passam.** O CI valida ruff, black, mypy, migrations pendentes,
   os testes, `check --deploy` e auditoria de dependências — e **nunca executou**. Escrever a
   Etapa 4 sobre uma base cujo estado de verificação é desconhecido é construir sobre suposição.

3. **É pré-requisito estrutural.** Sem commit não há PR; sem PR o CI não dispara; sem CI cada uma
   das 10 etapas seguintes entra sem nenhuma verificação automática.

4. **Custa minutos.** Não há trade-off aqui — é o maior retorno por esforço do plano inteiro.

**Concretamente:** commit inicial, branch `main` (ou ajuste do gatilho do CI para `master`), remoto
configurado, push, e leitura da saída real do pipeline.

**Ressalva de ambiente:** a máquina de desenvolvimento atual não tem Docker (`docker` não existe
nesta distro WSL) nem Python/Django/pytest instalados. O backend exige PostGIS e não roda sem
container. Por isso a primeira execução real da suíte acontece **no CI**, que provisiona PostGIS e
Redis como serviços — não localmente.

**Depois de GIT-001:** `SEC-001`, `API-001`, `SEC-002` e `CI-001` fecham a Fase 0. Só então
`GEO-001` inicia o produto.
