# CLAUDE.md — memória operacional

> Leia este arquivo **antes de qualquer mudança relevante**. Ele resume o que o projeto é,
> como está organizado, e o que é proibido. Regras aqui vencem preferências pessoais.
>
> Aqui estão as **regras**. O **mapa** — modelo de dados completo, superfície da API, telas,
> e a tabela "onde mexer para cada tipo de mudança" — está em `docs/BRIEFING.md`.

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
| `discovery` | Search, SearchJob, SearchResult, particionamento, tasks | ✅ |
| `analysis` | WebsiteScan/Finding, SSRF guard, Opportunity, Score | ✅ |
| `crm` | Lead, Pipeline, Stage, Interaction, Note, Task, Suppression | ✅ |

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

## Armadilhas do ambiente (já custaram tempo)

- **Dependência nova exige `docker compose build`, não `pip install` no container.** O
  Compose constrói **uma imagem por serviço**: instalar à mão no `backend` deixa o
  `celery_worker` sem o pacote, e o erro só aparece quando algo roda na fila — etapas
  depois. Depois de mexer em `requirements*.txt`: `docker compose build backend celery_worker`.
- **App novo com tasks exige reiniciar o worker.** O `autodiscover_tasks` roda no boot; sem
  restart o worker responde `Received unregistered task` e os jobs ficam parados em
  `SCHEDULED`, sem erro visível no lado de quem disparou.
- **Índice de trigrama só é usado pelo operador `%`.** `similarity(x, y) >= 0.6` faz o
  planejador varrer a tabela e calcular linha a linha. Em `dedup._por_nome` o corte grosso é
  `__trigram_similar` (indexado) e o fino é `TrigramSimilarity` sobre o que sobrou. O lookup
  exige `django.contrib.postgres` no `INSTALLED_APPS`.
- **Build de produção com a mesma tag da imagem de dev apaga o ambiente de desenvolvimento.**
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml build` reaproveitava a tag
  `leads-frontend`/`leads-backend` e sobrescrevia a imagem de dev — o frontend passava a ser
  o estágio `runner` (uid 1001, sem o binário `next`), e o sintoma aparecia só no próximo
  `up`: `sh: next: not found` ou `EACCES` no `.next`. Cada serviço do `docker-compose.prod.yml`
  agora tem `image: ...-prod`. Se acontecer de novo:
  `docker compose build frontend && docker compose up -d -V frontend` — o `-V` é obrigatório,
  senão os volumes anônimos (`node_modules`, `.next`) continuam com o conteúdo antigo.
- **Não rode `npm run build` no container que serve `next dev`.** O build de produção
  sobrescreve o `.next/` que o servidor de desenvolvimento está usando, e todas as rotas
  passam a dar 500 com `ENOENT: vendor-chunks/next.js` — erro que não parece ter relação
  nenhuma com a causa. Para verificar o build, pare o container antes, ou limpe o `.next` e
  reinicie depois.

## Antes de uma mudança grande

1. Reler este arquivo e o ADR relacionado.
2. Ver o que já existe — não duplicar helper/serviço.
3. Checar impacto: segurança, tenancy, índices, N+1, custo de API externa.
4. Implementar na camada certa (service, não view).
5. `make test` e `make lint` — e reportar a saída real, nunca "deve funcionar".
   **Os dois não são o portão inteiro:** a CI ainda roda `makemigrations --check`,
   `pytest --cov` (piso 89%), `prettier --check` e `check --deploy --fail-level WARNING`.
   Este último já falhou com o lint local passando — comandos prontos em `docs/BRIEFING.md` §2.
   Se mexeu em dependência, rode **também** no `celery_worker`: passar só no `backend`
   esconde imagem desatualizada.
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

**As 14 etapas do roteiro estão concluídas**, e depois delas veio a **reestruturação de
produto** (`docs/PRODUCT_REDESIGN_PLAN.md`), que reorganizou a experiência em torno do fluxo
comercial: login → Empresas (filtrar) → telefone na linha → lista ou CRM → funil até venda
fechada. Antes dela, o telefone — o dado mais importante do produto — não existia em lugar
nenhum da interface, e `Company` não tinha endpoint.

Pendências conhecidas, fora do roteiro: a CI está configurada mas **nunca completou um
passo** — as execuções do workflow travam por faturamento (conta do GitHub) antes de iniciar
qualquer job, e ficam vermelhas em `main`. O repositório está público desde 14/08 — foi para
destravar o Actions, o que não funcionou, e dá para reverter.
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

## Descoberta

`Search` é a intenção; o particionamento a quebra em `SearchJob`, um por **cidade x
categoria x fonte** — a menor unidade que dá para executar, repetir e reportar sozinha. Um
504 em Cambé não pode obrigar a refazer o Paraná.

`plan_search` **recusa antes de criar** o que passar de `DISCOVERY_MAX_JOBS_PER_SEARCH`.
Não é limitação técnica: é o que impede um clique em "Brasil inteiro" de virar 5.571
requisições contra um serviço comunitário (ADR-0004).

`claim_job` usa `select_for_update`: é ele, e não a fila, que garante que a mesma task
reentregue pelo broker (`acks_late` faz isso) execute uma vez só.

Progresso e situação da busca são **derivados** dos jobs, nunca acumulados — contador
incrementado por worker paralelo diverge, e a divergência vira busca eternamente "em
andamento" com tudo pronto. Na listagem eles vêm de anotação, senão é N+1 numa tela que a
interface consulta em laço.

Antes de usar: `seed_providers` e as categorias do `seed_dev_data` (é o `provider_mapping`
que traduz "Dentistas" para as tags de cada fonte).

## Análise de site

**`apps/analysis/ssrf.safe_get` é o único caminho para buscar URL de terceiro.** Se aparecer
`urlopen` ou `requests` em qualquer app, o guard virou decoração. As sete regras do
`SECURITY.md` estão implementadas lá, e os testes delas são pré-requisito do scanner existir.

Os dois pontos que não são óbvios:

- **Conectar no IP validado, não no nome.** Validar a string e deixar a lib resolver de novo
  é TOCTOU: o DNS muda entre a checagem e a conexão. O socket é aberto à mão no IP aprovado,
  com `server_hostname` no nome para SNI e certificado.
- **Revalidar cada redirect do zero.** Cada `301` é uma URL escolhida pelo servidor remoto,
  que nunca passou por validação.

`WebsiteScan.status=BLOCKED` é o guard tendo recusado — evento de segurança, e nunca deve
virar `UNREACHABLE`, que é site fora do ar. Confundir os dois esconde uma tentativa de SSRF.

`Company.website_status` responde "a fonte identificou um site?"; `WebsiteScan.status`
responde "o site funciona?". Perguntas diferentes, campos diferentes: domínio expirado
continua `FOUND`, e quem lê o funcionamento é a Etapa 10.

URL entra normalizada por `CompanyWebsite.save` — a tag `website` do OSM vem sem esquema na
maioria das vezes, e URL torta faria o guard tratar dado sujo como ataque.

## Regras e oportunidades (ADR-0008)

Predicado em `apps/analysis/rules.py`, decorado com `@rule("codigo")`. Parâmetro, peso e
ativação em `OpportunityType`, no banco. **Sem `eval`, sem `exec`, sem expressão vinda de
string — nunca.** Há teste que verifica isso pela AST.

Criar tipo novo de regra exige código, e é de propósito: regra nova é lógica nova, e lógica
nova merece revisão em PR. Ajustar peso é `UPDATE`.

Código de regra desconhecido é ignorado com aviso e não quebra o cálculo; predicado com
defeito derruba a sua regra, não a empresa inteira.

**A regra que sustenta a credibilidade do produto: "não sei" nunca vira "não tem".** Empresa
nunca analisada não gera oportunidade nenhuma. Sinal vindo de scan que falhou chega como
`None`, e não como o `False` padrão do model — senão site que nem foi visitado viraria três
oportunidades inventadas.

`CompanyContext` é montado uma vez por empresa, em `opportunities.build_context`. Predicado
não consulta o banco: viraria N+1 silencioso sobre milhares de empresas.

Oportunidade que deixou de valer vira `RESOLVED` com data, nunca é apagada.

O score mede **quanto vale ir atrás da empresa**, não quão boa ela é: quem não tem site é
lead melhor para quem vende site. Peso negativo existe para dificuldade de abordagem —
empresa sem telefone nenhum cai na fila mesmo tendo boa oportunidade.

Toda parcela grava regra, pontos e motivo: o breakdown **soma** o valor exibido, e o corte
em 0–100 é no fim, sobre a soma. `Score.version` é hash do conjunto de regras, não número
que alguém precisa lembrar de incrementar — sem ele, comparar scores de semanas diferentes é
comparar coisas distintas.

Antes de usar: `seed_opportunity_types` e `seed_score_rules`.

## CRM e LGPD

`Company` é global, `Lead` é do tenant — a fronteira do ADR-0007 na prática. Duas
organizações prospectando a mesma empresa têm dois leads e nenhum acesso ao histórico da
outra.

`Interaction` é **append-only**, inclusive pelo admin. É o único registro de que a abordagem
aconteceu, e a prova diante da LGPD. Mudança de estágio entra como `STATUS_CHANGE` gerado
pelo serviço — trocar `lead.stage` direto apagaria a evidência da decisão.

`Note` é separada de `Interaction` de propósito: interação é *evento* ("liguei terça"), e por
isso não se reescreve; anotação é *conhecimento* ("o dono é irmão do concorrente"), que se
corrige quando estava errado.

Só CALL/WHATSAPP/EMAIL/MEETING/PROPOSAL atualizam `last_contacted_at`. Anotação e mudança de
estágio não são contato — contá-los faria o time achar que falou com o cliente quando só
mexeu no sistema.

**A supressão não fica na ingestão**, e isso é decisão registrada, não esquecimento:
`Company` é global e `SuppressionEntry` é da organização, então recusar a persistência
esconderia a empresa de quem nunca pediu opt-out. Ela morde em `crm/services.create_lead` e
em `log_interaction` — onde significa alguma coisa. Ver `crm/suppression.py`.

Suprimir **encerra os leads abertos na hora**: registrar sem encerrar deixaria o lead na fila
de alguém, que ligaria amanhã. E é por identificador normalizado, nunca por empresa — a mesma
pessoa reaparece com outro `company_id` na próxima busca.

Antes de usar: `python manage.py seed_pipeline`.

## A tela Empresas (o centro do produto)

`GET /api/v1/companies/` é o endpoint que sustenta quase tudo: tabela de empresas, listas,
exportação e o painel. Ele é **global** (ADR-0007) — o que é do tenant são as colunas
`lead_id`/`lead_stage_*`, anotadas a partir da organização da sessão.

`companies/queries.py` é o **único** construtor desse queryset. Três coisas não são detalhe:

- **Nada ali importa `analysis`, `crm` ou `providers`.** Os dados desses apps entram pelo
  nome da relação reversa (`score`, `opportunities`, `scans`, `leads`), que as FKs *deles*
  criaram. Acoplamento por string resolvido pelo ORM mantém a ordem de dependência intacta.
  O preço são dois literais de status (`OPPORTUNITY_OPEN`, `SCAN_BROKEN`), guardados por
  teste que mora em `analysis` — o app de cima, que pode importar o de baixo.
- **Tudo é `Subquery`/`FilteredRelation`.** Contagem de consultas não cresce com o número de
  linhas; há teste medindo com 10 e com 30 (o método da Etapa 14).
- **`isnull` sobre alias de `FilteredRelation` não vira `IS NULL`.** Filtrar "ainda não é meu
  lead" é pela anotação (`lead_id__isnull`), nunca pelo alias — pelo alias devolve a tabela
  inteira em silêncio.

Filtro multivalorado corta por `Exists` (sem `distinct`), exceto quando o dado mora em app
superior — aí é `JOIN` + `distinct`, porque `Exists` exigiria import proibido.

**Lista não é lead.** `CompanyList` separa um lote para trabalhar depois; `Lead` é relação
comercial, abre histórico e passa pela supressão da LGPD. O lote em massa
(`POST /crm/leads/bulk/`) devolve `criados`, `ja_existiam` e `suprimidos` separados: um
opt-out no meio de 20 não pode passar por estar acompanhado.

Exportação (`companies/export.py`) tem teto de 5.000 linhas, escreve no CSV que truncou,
grava `AuditLog.Action.EXPORT` e escapa por `csv.writer`. O rótulo do site sai por extenso —
"Site oficial não identificado nas fontes analisadas" —, porque no CSV a frase deixa o
produto e vira "verdade" na mão de terceiros.

## Frontend

A tese do design é a mesma do produto: **a ausência é o ativo**. O âmbar — única cor forte da
paleta — marca o que *falta*; o que a empresa já tem fica cinza, quase invisível. É o inverso
de toda barra de progresso, e é o que faz uma lista de trinta empresas ser lida num segundo.

A **barra de lacunas** (`components/lacunas.tsx`) é o elemento assinatura: cinco segmentos por
empresa — site, celular, contato, agenda, https. Cheio = falta. Hachurado = ainda não
verificado, e **nunca** é pintado como lacuna: "não sei" não vira "não tem" na tela, pela
mesma razão que não vira no backend.

Fundo é papel de escritório (cinza-verde frio), não creme. Chivo nos títulos, Archivo no
corpo, Azeret Mono em todo número — score, telefone, código IBGE e contagem alinham em
coluna, que é como se varre uma lista de ligações com o olho.

Português em toda parte, inclusive no código do frontend: os nomes das telas e componentes
são os do domínio (`Casca`, `BarraDeLacunas`, `Regua`), como no backend. **As rotas também**
— `/empresas`, `/leads`, `/listas`, `/buscas`. `/crm` redireciona para `/leads` no
`next.config.ts`: renomear rota sem redirecionar quebra o usuário, não o código.

Navegação: `Painel · Empresas · Leads · Listas · Buscas · Configurações`. Leads e funil são
**uma seção com duas vistas** (`/leads?vista=funil`), não dois itens de menu — são o mesmo
dado, e separá-los criaria dois lugares para procurar o mesmo lead.

Os filtros da tela Empresas vivem na URL, com **os mesmos nomes da API** (`uf`, `category`,
`has_phone`, `site`, `score_min`, `in_crm`): a query string da tela e a da requisição são a
mesma coisa, então não existe tabela de tradução para esquecer de atualizar.

**Telefone é dado de primeira classe** (`components/telefone.tsx`): aparece na tabela de
empresas, na de leads e na ficha, com copiar de um clique. O botão de WhatsApp só existe
quando há contato do tipo `WHATSAPP` — celular não é WhatsApp presumido, nem na tela nem no
banco. A máscara só é aplicada a número brasileiro reconhecido; o resto sai como veio.

## O que a Etapa 14 mediu

Medido, não presumido — e o método importa porque com dezenas de linhas o planejador escolhe
seq scan e está **certo**:

- **N+1**: contagem de consultas com 10 e depois 30 registros. Ficou plana em todos os
  endpoints (10, 9, 6, 5, 4), então não há N+1.
- **Índices**: `EXPLAIN` com `enable_seqscan = off`, que obriga o planejador a revelar qual
  índice usaria — ou admitir que não há nenhum. Foi assim que apareceu o único furo real.
- **Redação de log**: cada padrão testado com o segredo dentro, conferindo que ele some.
