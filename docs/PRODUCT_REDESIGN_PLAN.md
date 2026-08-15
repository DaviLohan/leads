# Reestruturação de produto — Apollo como referência de clareza

## Contexto

O produto tem os dados e as regras certas (14 etapas concluídas), mas a experiência não
entrega o fluxo comercial. Medido no código, não presumido:

**A tela principal (`/`, o "Radar") lista `/analysis/scores/` — não empresas.** Consequências:

- **Não existe endpoint de empresas.** `apps/companies/urls.py` expõe só `categories/`. O
  comentário no topo de `companies/views.py` assume: *"`Company` continua sem endpoint"*.
- **Telefone não existe em lugar nenhum da interface nem da API de listagem.** `CompanyContact`
  (PHONE/WHATSAPP/EMAIL) está no banco desde a Etapa 5 e nunca foi serializado. O dado
  comercial mais importante do produto é inalcançável pelo navegador.
- **Nem cidade, nem UF, nem categoria, nem site** aparecem na lista ou no detalhe.
- **Nenhum filtro.** Quem quer "dentistas em Curitiba sem site" não tem por onde pedir.
- Empresa sem `Score` **não aparece**: quem entra na base e ainda não foi pontuada é invisível.
- Não existem **Listas**, **exportação**, **ações em massa** nem **painel de prospecção**.

O que já está correto e será preservado: providers, ingestão, deduplicação, SSRF guard,
regras/score declarativos, CRM append-only, supressão LGPD, tenancy por `TenantViewSet`.

Decisões tomadas com o usuário nesta sessão:

1. **Leads e CRM são uma seção só**, com alternador Lista ↔ Funil (mesmos dados, duas vistas).
2. **"Buscar Leads" é a tela Empresas** — um painel de filtros e uma tabela, com dois botões
   distintos: `FILTRAR` (base local) e `BUSCAR NOVAS EMPRESAS` (providers externos).
3. **Rotas em português**, como o resto do código.

Resultado pretendido: login → filtrar → ver telefone na tabela → salvar 20 em lista →
abrir empresa → copiar telefone / abrir WhatsApp → mandar para o CRM → mover até GANHO,
sem terminal e sem admin.

## Nova arquitetura

**Navegação (6 itens, era 4):** `Painel · Empresas · Leads · Listas · Buscas · Configurações`

| Rota | Tela | Estado |
|---|---|---|
| `/` | **Painel** — como está minha prospecção | reescreve o Radar atual |
| `/empresas` | **Empresas / Buscar Leads** — filtros + tabela | nova |
| `/empresas/[id]` | Detalhe da empresa | reescreve |
| `/leads` | Leads — `?vista=lista` (padrão) ou `?vista=funil` | move de `/crm` |
| `/leads/[id]` | Detalhe do lead + histórico | move de `/crm/[id]` |
| `/listas`, `/listas/[id]` | Listas | novas |
| `/buscas` | Buscas (descoberta) | mantém, enriquece |
| `/configuracoes` | Organização, membros, supressão LGPD | mantém |

`/crm` e `/crm/[id]` viram redirects em `next.config.ts` — não quebrar link salvo.

Wireframe da tela central (`/empresas`), filtros sincronizados na URL
(`/empresas?uf=PR&categoria=dentista&site=nao_identificado&tem_telefone=1&score_min=60`):

```
EMPRESAS                                    347 empresas · 83 com oportunidade aberta
┌── FILTRAR NA BASE ────┬──────────────────────────────────────────────────────────────┐
│ Estado    [PR ▾]      │ ☐  EMPRESA          SEGMENTO  CIDADE    TELEFONE      ZAP    │
│ Cidade    [Curitiba]  │ ☐  Clínica Sorriso+ Dentista  Curitiba  (41) 3333-…   ✓      │
│ Categoria [Dentista]  │      site não identificado · Site + Agendamento   94  NOVO ⋯ │
│ Site      [não ident.]│ ─────────────────────────────────────────────────────────────│
│ ☑ tem telefone        │ ☐  Odonto Batel     Dentista  Curitiba  (41) 99…     —      │
│ ☐ tem WhatsApp        │      site no ar · Agendamento                     71  LEAD ⋯ │
│ Score  [60] – [100]   │                                                              │
│ Situação  [todos ▾]   │  ── 20 selecionadas ────────────────────────────────────────│
│ [ + mais filtros ]    │  [SALVAR EM LISTA] [ADICIONAR AO CRM] [EXPORTAR CSV]         │
│                       │                                                              │
│ ▸ [ FILTRAR ]         │  ‹ 1 2 3 … ›                                                 │
│ ─────────────────     │                                                              │
│ Não achou? Descubra   │                                                              │
│ novas empresas nas    │                                                              │
│ fontes externas:      │                                                              │
│ [BUSCAR NOVAS EMPRESAS]                                                              │
└───────────────────────┴──────────────────────────────────────────────────────────────┘
```

`FILTRAR` é botão primário na coluna de filtros; `BUSCAR NOVAS EMPRESAS` fica separado por
régua, com texto explicando que sai para fontes externas e leva minutos — as duas ações
nunca se parecem.

## Backend

Ordem de dependência preservada: `companies` não importa `crm`; `crm` importa `companies`.

### 1. `/api/v1/companies/companies/` — o endpoint que falta (o núcleo de tudo)

`apps/companies/queries.py` (novo) — **um** construtor de queryset usado por todos os
consumidores (lista, detalhe, listas, export), para que a otimização não seja reescrita:

- telefone / WhatsApp / e-mail: `Subquery` sobre `CompanyContact` (`-is_primary`), um por tipo;
- cidade / UF: `Subquery` sobre `CompanyAddress` primário → `city.name`, `city.state.uf`;
- site principal e categoria principal: `Subquery`;
- score: `select_related("score")` (OneToOne existente);
- oportunidades abertas: `Prefetch` com `select_related("type")`;
- `lead_id`/`lead_stage`: `Subquery` de `Lead` **filtrado pela organização do request** —
  `Company` é global, a coluna "já está no meu CRM" é do tenant (ADR-0007).

`CompanyFilter` (django-filter, backend já é o padrão em settings): `uf`, `cidade`,
`categoria`, `q` (nome via `normalize_name` + índice trigrama existente), `site`
(`identificado` / `nao_identificado` / `nao_verificado` / `com_problemas` → `Exists` de
`WebsiteScan` não-OK), `tem_telefone` / `tem_whatsapp` / `tem_email` (`Exists`),
`oportunidade` (código do tipo, abertas), `score_min` / `score_max`, `situacao`
(sem lead / com lead / código do estágio). Ordenação por `OrderingFilter`
(`-score__value` padrão, `name`, `-discovered_at`).

Detalhe (`retrieve`): contatos completos com `verification_status`, endereços, sites, perfis
sociais, score com breakdown, oportunidades abertas, último scan.

**Rastreabilidade (item 13 do documento):** `CompanySource` mora em `providers` e `companies`
não pode importá-lo. Vai como viewset somente-leitura em `apps/providers/` —
`/providers/sources/?company=<id>` —, consumido pelo botão "Ver origem" do detalhe.

Índice novo: `Score.value` (`Index(fields=["-value"])`). É a ordenação padrão da tela
principal e hoje não existe índice nenhum sobre ela.

### 2. Listas — `apps/crm/models.py`

`CompanyList(TenantModel)`: `name`, `description`, `UniqueConstraint(organization, name)`.
`CompanyListItem(BaseModel)`: `list`, `company`, `added_by`, `UniqueConstraint(list, company)`
— uma empresa em várias listas, sem duplicar dentro da mesma. Migration puramente aditiva.

API: `/crm/lists/` (CRUD, `lead_count` por anotação), `POST /crm/lists/{id}/items/`
(`{company_ids: [...]}`, teto de 200, `get_or_create` — idempotência vem da constraint),
`DELETE .../items/{company_id}/`, `GET /crm/lists/{id}/companies/` reusando
`companies/queries.py`.

### 3. Ações em massa e exportação

- `POST /crm/leads/bulk/` — `{company_ids: [...]}`, teto de 100, chama
  `crm.services.create_lead` por empresa (é ele que checa supressão, escolhe estágio e abre
  histórico). Devolve `{criados, ja_existiam, suprimidos: [...]}` — parcial é resultado
  legítimo, não erro.
- `GET /companies/companies/export/` e `GET /crm/lists/{id}/export/` — `StreamingHttpResponse`
  CSV, mesmo filterset, teto de 5.000 linhas (e o CSV diz quando truncou), escopo de throttle
  novo `export` (20/hora), `record_audit` em toda exportação. Exportar carteira comercial é
  exatamente o tipo de ação que precisa de rastro.
- Mudança de estágio em massa: **fora deste plano** — mover lead gera `Interaction` e é
  decisão individual. Entra se você pedir.

### 4. Painel e Buscas

- `GET /crm/summary/` — leads por estágio, novos hoje/semana, contatados hoje, sem contato,
  propostas, ganhos no mês, conversão, e as 5 melhores oportunidades ainda sem lead. Um
  endpoint com agregações, não seis chamadas da tela.
- `SearchSerializer` ganha soma dos contadores que os `SearchJob` **já gravam**
  (`found/new/duplicate/review/error`). "Com telefone", "oportunidades" e "custo estimado"
  do documento **não** entram: não são medidos hoje, e inventar número no painel é pior que
  não mostrar.

## Frontend

Reaproveitar: `Casca`, `Cabecalho`, `Botao`, `Etiqueta`, `Vazio`, `Erro`, `Score`,
`BarraDeLacunas`, `lacunasDe`, `apiFetch`, `errorMessage`, `qs`.

Componentes novos (`frontend/src/components/`):

| Componente | Papel |
|---|---|
| `tabela.tsx` | Tabela densa com seleção (☐ linha / página), barra de ações em massa |
| `filtros.tsx` | Painel de filtros ↔ query params (`useSearchParams` + `router.replace`) |
| `telefone.tsx` | Telefone em Azeret Mono + `COPIAR` + `WhatsApp` (`wa.me`) só quando há contato `WHATSAPP` — celular **não** vira WhatsApp presumido |
| `estado.tsx` | Etiqueta de situação: NOVO · LEAD · CONTATADO · GANHO · PERDIDO |

A tese visual continua: âmbar marca o que **falta**, cinza o que já existe, hachura para
"ainda não verificado" — e `null` nunca é pintado como lacuna.

## Ordem de execução

Cada passo é entregável e verificável sozinho.

| # | Passo | Fecha |
|---|---|---|
| 0 | `docs/PRODUCT_REDESIGN_PLAN.md` com este conteúdo | rastro da decisão |
| 1 | `companies/queries.py` + `CompanyViewSet` + `CompanyFilter` + índice do score + testes | base de tudo |
| 2 | Nav nova + `/empresas` (filtros, tabela, telefone, WhatsApp) + `/empresas/[id]` reescrita | cenários 1 e 2 |
| 3 | Listas (models, API, `/listas`) + ações em massa (salvar em lista, adicionar ao CRM) | cenário 3 |
| 4 | `/leads` (lista ↔ funil) + `/leads/[id]` + redirects de `/crm` | cenários 4 e 5 |
| 5 | Painel (`/`) + `/buscas` enriquecida | pergunta "como está minha prospecção" |
| 6 | Exportação CSV (empresas e listas) + auditoria | item 21 |

**Fora do MVP, de propósito** (arquitetura permite, código não entra agora): colunas
configuráveis pelo usuário, busca em linguagem natural com IA, `Pessoas/Decisores`,
enriquecimento por provider, buscas salvas, mensagens em massa. Cada um vira etapa própria
quando for pedido.

## Riscos

- **Consulta lenta na tela principal** — é a única tela que junta empresa, endereço, contato,
  score e oportunidade. Mitigação: tudo por `Subquery`/`Prefetch` e a medição da Etapa 14
  (contagem de consultas com 10 e 30 registros; tem de ficar plana).
- **Vazamento de tenant** — `/companies/` é global mas anota dados de `Lead`. Teste explícito:
  duas organizações, a mesma empresa, cada uma só enxerga o próprio lead.
- **LGPD na exportação** — empresa com identificador suprimido sai marcada e não pode ser
  adicionada ao CRM em massa; `crm.services.create_lead` já recusa, o teste garante que o
  bulk não contorna.
- **Rotas** — `/crm` e `/crm/[id]` redirecionam; nenhum link existente quebra.
- **Migrations** — só aditivas (duas tabelas novas, um índice). Nenhuma destrutiva, nenhum
  backfill. Se algum passo exigir mudança destrutiva, paro e explico antes.

## Verificação

Backend: `make test` e `make lint` a cada passo (e no `celery_worker` se mexer em dependência).
Testes novos por passo: filtros da API (cada filtro com caso positivo e negativo), isolamento
de tenant, contagem de consultas 10 vs 30, listas (idempotência do `get_or_create`), bulk com
empresa suprimida, CSV (cabeçalho, escapes, teto).

Frontend: vitest para `filtros` (ida e volta de query params) e para o link de WhatsApp
(só aparece com contato `WHATSAPP` real).

Homologação no navegador, com os dados reais de dev (31 empresas pontuadas, 56 oportunidades):

1. "Dentistas em Curitiba sem site" — contar cliques até a lista (meta: ≤ 4);
2. "Telefone da Clínica X" — visível na tabela, sem abrir nada;
3. selecionar 20 → SALVAR EM LISTA;
4. abrir empresa → COPIAR TELEFONE → WhatsApp → ADICIONAR AO CRM → CONTATADO;
5. `/leads?vista=funil` → ver propostas → mover até GANHO.

Ao final, o relatório ANTES/DEPOIS pedido no item 50, respondendo às nove perguntas
("onde encontro meus leads / o telefone / o WhatsApp / …") com a rota de cada uma.

---

# Executado — 15/08/2026

Todos os seis passos foram entregues. O que mudou de fato em relação ao plano:

- O índice de `Score.value` **já existia** (`Index(fields=["-value"])`); nenhuma migration
  foi necessária para ele.
- Os nomes dos filtros na URL da tela ficaram **iguais aos da API** (`uf`, `category`,
  `has_phone`…) em vez de traduzidos, para não existir mapa de tradução no meio.
- `analysis` e `providers` não ganharam duplicação: score, oportunidades e diagnóstico
  continuam em `/analysis/…`, e a procedência saiu em `/providers/sources/`.
- Dois defeitos reais apareceram durante a execução e foram corrigidos na raiz (abaixo).

## Endpoints novos

| Método e rota | Para quê |
|---|---|
| `GET /api/v1/companies/` | Tabela de empresas: 13 filtros de servidor, ordenação, paginação |
| `GET /api/v1/companies/{id}/` | Ficha: contatos, endereços, sites, redes, categorias |
| `GET /api/v1/companies/export/` | CSV do recorte atual (teto 5.000, auditado) |
| `GET /api/v1/providers/sources/?company=` | Procedência: fonte, id externo, data, confiança |
| `GET/POST /api/v1/crm/lists/` | Listas de trabalho |
| `POST/DELETE /api/v1/crm/lists/{id}/items/` | Adicionar/remover lote (teto 200, idempotente) |
| `GET /api/v1/crm/lists/{id}/companies/` | Conteúdo da lista, mesmas colunas da tabela |
| `GET /api/v1/crm/lists/{id}/export/` | CSV da lista |
| `POST /api/v1/crm/leads/bulk/` | Lote no funil (teto 100 na tela, 200 na API) |
| `GET /api/v1/crm/leads/summary/` | Painel: números da prospecção + melhores oportunidades |

Alterados: `LeadSerializer` ganhou `phone`, `whatsapp`, `city`, `uf`, `opportunities`;
`SearchSerializer` ganhou as somas dos jobs (`found/new/duplicate/review/error`).

## Defeitos encontrados e corrigidos na raiz

1. **Vendedor não conseguia abrir a tela de Leads.** `PipelineViewSet` exigia `MANAGER`
   inclusive para leitura, e a régua de estágios é a primeira coisa que a tela carrega. Ler o
   funil passou a ser `SALES`; desenhá-lo continua `MANAGER`.
2. **Histórico do lead podia sair de cabeça para baixo.** `Interaction` ordenava só por
   `-occurred_at`; dois eventos no mesmo instante (mudança de estágio + interação) saíam em
   ordem arbitrária do banco. Desempate por `-id` (uuid7 é ordenado no tempo).

Fora do redesenho, mas no caminho: o build de produção compartilhava a tag de imagem com o de
desenvolvimento e apagava as dependências de dev — cada serviço do `docker-compose.prod.yml`
agora tem `image: …-prod`.

## Onde está cada coisa

| Pergunta | Resposta |
|---|---|
| Onde encontro meus leads? | `/leads` — lista para trabalhar, `?vista=funil` para o funil |
| Onde encontro o telefone? | Na coluna **Telefone** de `/empresas` e `/leads`, com "copiar"; e no bloco Contato da ficha |
| Onde encontro o WhatsApp? | Coluna **WhatsApp**, só quando há contato desse tipo confirmado |
| Onde vejo empresas? | `/empresas` — a base inteira, com filtros |
| Onde vejo oportunidade? | Abaixo do nome na tabela; com evidência na ficha da empresa |
| Onde crio lista? | Selecionando na tabela → **Salvar em lista**; ou em `/listas` |
| Onde exporto? | **Exportar CSV** em `/empresas` (segue o filtro) e em `/listas/{id}` |
| Onde acompanho o CRM? | `/leads?vista=funil`, e a ficha do lead em `/leads/{id}` |
| Onde vejo buscas anteriores? | `/buscas` — situação, progresso e o que cada uma rendeu |
