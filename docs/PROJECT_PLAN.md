# Plano do projeto

Documento de referência da arquitetura e do roteiro. Complementa `ARCHITECTURE.md` (como o
sistema é), `SECURITY.md` (o que não pode ser afrouxado) e `docs/ERD.md` (o modelo de dados).

## 1. Objetivo

Radar nacional de oportunidades digitais: localizar negócios brasileiros, analisar sua presença
digital, identificar oportunidades de venda de soluções (sites, e-commerce, agendamento,
sistemas sob medida, integrações, automações), pontuar os melhores potenciais clientes e
acompanhar toda a prospecção em CRM — aprendendo com o tempo quais perfis convertem.

Princípio fundamental: **empresa é entidade permanente**, não um "lead descartável". Ela pode
aparecer em várias buscas, ter várias fontes, telefones, sites, diagnósticos, oportunidades e
interações, e mudar de situação ao longo do tempo. Redescobrir não duplica.

## 2. Arquitetura

Ver `ARCHITECTURE.md`. Em resumo: monólito modular Django + DRF, PostgreSQL/PostGIS como fonte
de verdade, Celery/Redis para trabalho pesado, Next.js no frontend, tudo em containers.

Decisões travadas nos ADRs `0001`–`0008`.

## 3. Conflitos identificados nos requisitos e como foram resolvidos

Levantados na análise do documento original, antes de qualquer código.

### 3.1 Google Places × "empresa é entidade permanente" — **conflito real**

Os termos do Google permitem armazenar `place_id` indefinidamente e coordenadas por até 30 dias;
nome, telefone, nota e avaliações não podem ser armazenados. Isso é incompatível com o princípio
fundamental do produto.

**Resolução:** OSM/Overpass como provider primário; `Provider.retention_policy` (`PERSIST` ou
`EPHEMERAL_30D`) torna a conformidade parte do schema. Detalhes em ADR-0004.

### 3.2 Escala nacional × endpoint público gratuito

O Overpass público é serviço comunitário com política de uso justo e sem garantia de
disponibilidade. Varrer milhares de municípios contra ele é abuso e quebra.

**Resolução:** limitador conservador (≤1 req/s), backoff com jitter, User-Agent identificado e
endpoint configurável. Escala nacional exige instância própria/extratos Geofabrik, ou a ingestão
dos Dados Abertos de CNPJ. Está documentado como limite conhecido, não como surpresa futura.

### 3.3 "Empresa sem site" × cobertura incompleta da fonte

Ausência de `website` no OSM não significa ausência de site no mundo.

**Resolução:** `website_status = NOT_FOUND` e o texto *"Site oficial não identificado nas fontes
analisadas"*. `CompanySource` registra quais fontes foram consultadas e quando. Afirmar que a
empresa não tem site é proibido (`CLAUDE.md`).

### 3.4 LGPD × supressão por ID de empresa

MEI e profissional liberal são pessoa física; o telefone "comercial" pode ser pessoal. E suprimir
por `company_id` não basta — a mesma empresa reaparece por outra busca ou outro provider.

**Resolução:** `SuppressionEntry` por identificador normalizado (telefone E.164, e-mail, domínio,
CNPJ), verificada no pipeline de ingestão, antes de persistir e antes de enfileirar contato.
Base legal: legítimo interesse com opt-out registrado.

### 3.5 Deduplicação por similaridade × milhões de linhas

Comparar nomes par a par é O(n²) — inviável no volume alvo.

**Resolução:** blocking key obrigatório (cidade + prefixo do nome normalizado, ou raio
geográfico) antes de qualquer comparação; similaridade via `pg_trgm` com índice GIN no banco,
nunca em Python sobre a tabela inteira.

### 3.6 Multi-tenancy × custo de descoberta

Se `Company` fosse por organização, cada tenant repetiria as mesmas chamadas de API e as mesmas
varreduras de site para produzir o mesmo resultado.

**Resolução:** dado público é global, dado comercial é do tenant (ADR-0007), com marcação
explícita no ERD e teste de isolamento obrigatório.

### 3.7 UUID × desempenho de índice

UUIDv4 fragmenta índices B-tree exatamente no regime de volume almejado.

**Resolução:** UUIDv7 gerado por helper local (ADR-0006).

### 3.8 Regras configuráveis × interpretador caseiro

Guardar a regra inteira no banco leva a um mini-parser ou a `eval()`.

**Resolução:** predicados registrados em código, pesos e parâmetros no banco (ADR-0008).

### 3.9 Idempotência × concorrência entre workers

`if exists` em Python tem corrida entre workers paralelos.

**Resolução:** `UniqueConstraint(provider, external_id)` + `get_or_create` em transação. O banco
arbitra.

### 3.10 SSRF × validação de URL

Validar a string antes de conectar não protege contra mudança de DNS (TOCTOU) nem contra
redirects.

**Resolução:** resolução manual de DNS, validação de todos os IPs, conexão no IP validado com
`Host` original, revalidação a cada redirect, teto de redirects, timeout e limite de bytes.
Testes de SSRF são pré-requisito para o scanner existir.

## 4. Fluxos principais

Descrição detalhada em `ARCHITECTURE.md`. Resumo:

- **Descoberta:** `Search` → particionamento geográfico → N `SearchJob` (cidade × categoria ×
  provider) → task Celery com rate limit e lock → normalização → supressão → dedup → persistência
  → enfileira análise de site.
- **Deduplicação:** sinais em ordem de força (provider+external_id, CNPJ, domínio, telefone+cidade,
  nome+proximidade, similaridade) classificando em `EXACT` / `PROBABLE` / `POSSIBLE` / `NEW`.
  `POSSIBLE` nunca faz merge automático.
- **Análise:** guard de SSRF → coleta de sinais → `WebsiteScan` + `WebsiteFinding` → Opportunity
  Engine → Scoring Engine com breakdown.
- **CRM:** `Lead` por organização, pipeline `NEW → … → WON/LOST` + `DO_NOT_CONTACT`, histórico
  append-only.

## 5. Modelo de dados

`docs/ERD.md`, com escopo (global/tenant) marcado por tabela.

## 6. Roteiro

| Etapa | Escopo | Situação |
|---|---|---|
| 1 | Arquitetura, ERD, ADRs, documentação | ✅ concluída |
| 2 | Fundação: monorepo, Docker, Postgres/PostGIS, Redis, Celery, Django, Next.js, lint/test/CI | ✅ concluída |
| 3 | Auth, Organization, Membership, RBAC, isolamento de tenant, auditoria | ✅ concluída |
| 4 | Geografia: State, City, importador IBGE, PostGIS | ✅ concluída |
| 5 | Companies: modelo completo + normalização | ✅ concluída |
| 6 | Deduplicação: `CompanyResolver` + testes robustos | ✅ concluída |
| 7 | Providers: abstração + Overpass + Mock | ✅ concluída |
| 8 | Search engine: Search, SearchJob, tasks, progresso, retries, rate limit | ✅ concluída |
| 9 | Análise de site: guard de SSRF primeiro, depois o scanner | ✅ concluída |
| 10 | Opportunity Engine | próxima |
| 11 | Scoring configurável com breakdown | |
| 12 | CRM: Lead, Pipeline, Stage, Interaction | |
| 13 | Frontend: Login, Dashboard, Radar, Empresas, Detalhe, CRM, Buscas, Configurações | |
| 14 | Hardening: segurança, performance, índices, N+1, throttling, logging, container | |

Critério de MVP operacional — o fluxo completo funcionando de ponta a ponta:

login → Radar (Paraná / Londrina / Dentistas) → job em background → empresas encontradas,
normalizadas, deduplicadas → site identificado ou `NOT_FOUND` → diagnóstico → oportunidades →
score com breakdown → abrir empresa → anotação → mover no pipeline até venda fechada.

## 7. Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| Endpoint público do Overpass indisponível ou limitado | Descoberta para | Endpoint configurável, backoff, caminho para instância própria/Geofabrik |
| Cobertura irregular do OSM no interior | Poucos resultados em cidades pequenas | Ingestão dos Dados Abertos de CNPJ (Etapa 7+) |
| Dedup gerando falso positivo | Merge indevido de empresas distintas | `POSSIBLE_MATCH` vai para revisão manual; merge é transacional e auditado |
| Volume de scans saturando worker | Fila travada | Filas Celery separadas por tipo de trabalho, concorrência configurável |
| SSRF no scanner | Acesso a rede interna | Guard obrigatório + testes antes do scanner existir |
| Vazamento entre organizações | Grave, contratual | Fronteira no ERD + manager com escopo + teste de isolamento |
| Custo de API externa fora de controle | Financeiro | `ProviderUsage` com requests, quota e custo estimado por período |
| Regras de score viram código espalhado | Manutenção | ADR-0008 |

## 8. O que está deliberadamente fora

Kubernetes, Kafka, microserviços, event sourcing, CQRS, service mesh, billing, MFA, uploads,
IA (módulo auxiliar, entra depois do MVP e a plataforma funciona sem ela). Cada item entra com
necessidade comprovada e ADR.
