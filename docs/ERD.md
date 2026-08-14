# ERD — modelo de dados

Marcação de escopo em cada tabela:

- 🌐 **global** — dado público sobre a empresa no mundo real, compartilhado entre organizações.
- 🔒 **tenant** — dado comercial, pertence a uma `Organization` e nunca cruza a fronteira.

Ver [ADR-0007](adr/0007-tenancy-boundary.md) para o porquê.

## Contas e tenancy

```mermaid
erDiagram
    User ||--o{ Membership : tem
    Organization ||--o{ Membership : tem
    Membership }o--|| Role : possui

    User {
        uuid id PK
        string email UK
        string password
        string full_name
        bool is_active
        datetime last_login
    }
    Organization {
        uuid id PK
        string name
        string slug UK
        string timezone
        bool is_active
    }
    Membership {
        uuid id PK
        uuid user_id FK
        uuid organization_id FK
        string role
        datetime joined_at
    }
```

`UniqueConstraint(user, organization)` em `Membership`. Papéis: `OWNER`, `ADMIN`, `MANAGER`,
`SALES`, `VIEWER`.

## Geografia 🌐

```mermaid
erDiagram
    State ||--o{ City : contém

    State {
        uuid id PK
        string ibge_code UK
        string uf UK
        string name
        string region
    }
    City {
        uuid id PK
        uuid state_id FK
        string ibge_code UK
        string name
        string normalized_name
        point centroid
        multipolygon boundary
    }
```

Códigos IBGE são a chave natural. `centroid` alimenta o particionamento geográfico das buscas;
`boundary` é opcional e entra quando houver necessidade real de contorno.

## Empresas 🌐

```mermaid
erDiagram
    Company ||--o{ CompanyAddress : tem
    Company ||--o{ CompanyContact : tem
    Company ||--o{ CompanyWebsite : tem
    Company ||--o{ CompanySocialProfile : tem
    Company ||--o{ CompanySource : tem
    Company ||--o{ CompanyCategory : tem
    Category ||--o{ CompanyCategory : classifica
    Category ||--o{ Category : pai_de
    City ||--o{ CompanyAddress : localiza
    Provider ||--o{ CompanySource : origina

    Company {
        uuid id PK
        string name
        string normalized_name
        string legal_name
        string trade_name
        string tax_id UK "CNPJ normalizado, nulo permitido"
        text description
        string status
        string website_status
        decimal rating
        int review_count
        datetime discovered_at
        datetime last_seen_at
        jsonb data_quality
    }
    CompanyAddress {
        uuid id PK
        uuid company_id FK
        uuid city_id FK
        string street
        string number
        string complement
        string district
        string postal_code
        point location
        bool is_primary
        string source_ref
    }
    CompanyContact {
        uuid id PK
        uuid company_id FK
        string kind "PHONE|WHATSAPP|EMAIL"
        string value_raw
        string value_normalized
        bool is_primary
        string verification_status
        datetime last_verified_at
        decimal confidence
    }
    CompanyWebsite {
        uuid id PK
        uuid company_id FK
        string url
        string domain
        bool is_primary
        string status
        datetime last_checked_at
    }
    CompanySocialProfile {
        uuid id PK
        uuid company_id FK
        string network
        string url
        string handle
    }
    CompanySource {
        uuid id PK
        uuid company_id FK
        uuid provider_id FK
        string external_id
        jsonb raw_payload
        datetime collected_at
        datetime expires_at "providers efêmeros"
        decimal confidence
    }
    Category {
        uuid id PK
        uuid parent_id FK
        string slug UK
        string name
        jsonb provider_mapping
        bool is_active
    }
    CompanyCategory {
        uuid id PK
        uuid company_id FK
        uuid category_id FK
        bool is_primary
        string assigned_by
    }
```

> **Onde cada tabela mora.** `CompanySource` está no diagrama de Empresas porque é dela que
> a procedência fala, mas o app que a hospeda é `providers` (Etapa 7): ela tem FK para
> `Provider`, e a ordem de dependência do `CLAUDE.md` é `companies` ← `providers` — companies
> não pode depender de providers. O relacionamento acima continua válido; muda só o pacote.

Pontos que valem constraint no banco:

- `UniqueConstraint(provider, external_id)` em `CompanySource` — base da idempotência.
- `UniqueConstraint(tax_id)` parcial (só quando não nulo) em `Company`.
- `UniqueConstraint(company, kind, value_normalized)` em `CompanyContact`.
- Índice GIN `pg_trgm` em `Company.normalized_name` e índice composto com a cidade — é o que
  torna a deduplicação viável em milhões de linhas.
- Índice GiST em `CompanyAddress.location` (PostGIS).

`Category.provider_mapping` guarda a tradução da categoria interna para cada fonte
(ex.: OSM `amenity=dentist`, CNAE `8630-5/04`) — é isso que evita categoria hardcoded no código.

## Providers

```mermaid
erDiagram
    Provider ||--o{ ProviderCredential : usa
    Provider ||--o{ ProviderUsage : registra
    Organization ||--o{ ProviderCredential : possui

    Provider {
        uuid id PK
        string slug UK
        string name
        bool is_enabled
        string retention_policy "PERSIST|EPHEMERAL_30D"
        int rate_limit_per_second
        int daily_quota
        jsonb config
    }
    ProviderCredential {
        uuid id PK
        uuid provider_id FK
        uuid organization_id FK "🔒 nulo = credencial da plataforma"
        string secret_ref "referência ao segredo, nunca o segredo"
        bool is_active
    }
    ProviderUsage {
        uuid id PK
        uuid provider_id FK
        uuid organization_id FK "🔒"
        date period
        int request_count
        int error_count
        decimal estimated_cost
    }
```

`retention_policy` é o que faz a diferença entre um provider cujos dados podem virar registro
permanente e um que só pode manter identificador + cache com expiração ([ADR-0004](adr/0004-osm-primary-provider.md)).

## Descoberta 🔒

```mermaid
erDiagram
    Organization ||--o{ Search : possui
    Search ||--o{ SearchJob : gera
    SearchJob ||--o{ SearchResult : produz
    SearchResult }o--|| Company : resolve_para
    City ||--o{ SearchJob : delimita
    Category ||--o{ SearchJob : filtra
    Provider ||--o{ SearchJob : executa

    Search {
        uuid id PK
        uuid organization_id FK
        uuid created_by FK
        string name
        jsonb criteria "UFs, cidades, raio, categorias, requisitos"
        string status
        datetime created_at
    }
    SearchJob {
        uuid id PK
        uuid search_id FK
        uuid city_id FK
        uuid category_id FK
        uuid provider_id FK
        string status
        int progress
        int found_count
        int new_count
        int duplicate_count
        int error_count
        int api_calls
        decimal estimated_cost
        int attempts
        text last_error
        datetime started_at
        datetime finished_at
    }
    SearchResult {
        uuid id PK
        uuid search_job_id FK
        uuid company_id FK
        string external_id
        string match_type "EXACT|PROBABLE|POSSIBLE|NEW"
        jsonb normalized_payload
    }
```

Status de `SearchJob`: `pending`, `scheduled`, `running`, `partially_completed`, `completed`,
`failed`, `cancelled`.

## Análise, oportunidades e score 🌐

```mermaid
erDiagram
    Company ||--o{ WebsiteScan : analisada_por
    CompanyWebsite ||--o{ WebsiteScan : alvo
    WebsiteScan ||--o{ WebsiteFinding : produz
    Company ||--o{ Opportunity : gera
    OpportunityType ||--o{ Opportunity : tipifica
    Company ||--|| Score : pontuada
    Score ||--o{ ScoreComponent : detalha

    WebsiteScan {
        uuid id PK
        uuid company_id FK
        uuid website_id FK
        string final_url
        int http_status
        bool is_https
        int response_time_ms
        bool has_valid_cert
        int redirect_count
        string title
        string meta_description
        bool has_viewport
        bool has_contact_form
        bool has_whatsapp
        bool has_booking
        bool has_cart
        jsonb signals
        string status
        datetime scanned_at
    }
    WebsiteFinding {
        uuid id PK
        uuid scan_id FK
        string code
        string severity
        text detail
        jsonb evidence
    }
    OpportunityType {
        uuid id PK
        string code UK
        string name
        text description
        jsonb rule_params
        bool is_active
    }
    Opportunity {
        uuid id PK
        uuid company_id FK
        uuid type_id FK
        string status
        decimal confidence
        jsonb evidence
        datetime detected_at
        datetime resolved_at
    }
    Score {
        uuid id PK
        uuid company_id FK
        int value "0-100"
        string version
        datetime computed_at
    }
    ScoreComponent {
        uuid id PK
        uuid score_id FK
        string rule_code
        int points
        text reason
    }
```

`ScoreComponent` é o breakdown auditável exigido: cada ponto do score tem regra e justificativa.
`OpportunityType.rule_params` parametriza um predicado registrado em código
([ADR-0008](adr/0008-declarative-rules.md)) — o banco não guarda expressão para interpretar.

`SegmentSolution` (recomendação de sistemas por segmento — dentista → agendamento, restaurante →
cardápio digital) entra na Etapa 10 como tabela ligando `Category` a `OpportunityType` com
peso, mantendo essas regras fora do código.

## CRM 🔒

```mermaid
erDiagram
    Organization ||--o{ Lead : possui
    Company ||--o{ Lead : origina
    Pipeline ||--o{ PipelineStage : tem
    PipelineStage ||--o{ Lead : posiciona
    Lead ||--o{ Interaction : registra
    Lead ||--o{ Note : anota
    Lead ||--o{ Task : agenda
    User ||--o{ Interaction : autor
    Organization ||--o{ SuppressionEntry : mantém

    Pipeline {
        uuid id PK
        uuid organization_id FK
        string name
        bool is_default
    }
    PipelineStage {
        uuid id PK
        uuid pipeline_id FK
        string code
        string name
        int position
        bool is_terminal
    }
    Lead {
        uuid id PK
        uuid organization_id FK
        uuid company_id FK
        uuid stage_id FK
        uuid owner_id FK
        int score_snapshot
        datetime last_contacted_at
        datetime next_action_at
        datetime created_at
    }
    Interaction {
        uuid id PK
        uuid lead_id FK
        uuid author_id FK
        string kind "CALL|WHATSAPP|EMAIL|MEETING|NOTE|PROPOSAL|STATUS_CHANGE"
        text description
        string outcome
        string next_action
        datetime next_action_at
        datetime occurred_at
    }
    Note {
        uuid id PK
        uuid lead_id FK
        uuid author_id FK
        text body
        datetime created_at
    }
    Task {
        uuid id PK
        uuid lead_id FK
        uuid assignee_id FK
        string title
        datetime due_at
        string status
    }
    SuppressionEntry {
        uuid id PK
        uuid organization_id FK
        string identifier_kind "PHONE|EMAIL|DOMAIN|TAX_ID|COMPANY"
        string identifier_value
        string reason
        uuid created_by FK
        datetime created_at
    }
```

`UniqueConstraint(organization, company)` em `Lead` — uma empresa é um lead por organização.
`UniqueConstraint(organization, identifier_kind, identifier_value)` em `SuppressionEntry`, com
índice usado pelo pipeline de ingestão.

`Interaction` é append-only: mudança de estágio vira registro `STATUS_CHANGE`, nunca sobrescreve.

## Auditoria 🌐

```mermaid
erDiagram
    User ||--o{ AuditLog : executa
    Organization ||--o{ AuditLog : contextualiza

    AuditLog {
        uuid id PK
        uuid actor_id FK
        uuid organization_id FK
        string action
        string object_type
        uuid object_id
        jsonb changes
        inet ip_address
        string request_id
        datetime created_at
    }
```

Append-only: a aplicação não faz update nem delete.
