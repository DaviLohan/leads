# ADR-0003 — Abstração de providers e pipeline de ingestão

**Status:** aceito · 2026-08-13

## Contexto

As fontes de dados vão mudar: APIs abertas, dados oficiais, fornecedores pagos, cada uma com
formato, limite e termos próprios. Se a regra de negócio conhecer o formato de uma fonte
específica, trocar de fonte vira reescrita.

Também é inaceitável que um provider escreva direto no banco: dado externo entra sem validação,
sem deduplicação e sem registro de origem.

## Decisão

Interface comum `BaseProvider`:

```python
class BaseProvider(ABC):
    slug: str
    retention_policy: RetentionPolicy

    def search_businesses(self, query: SearchQuery) -> Iterable[RawResult]: ...
    def get_business_details(self, external_id: str) -> RawResult | None: ...
    def normalize_result(self, raw: RawResult) -> BusinessDTO: ...
    def check_rate_limit(self) -> None: ...
```

Pipeline fixo e obrigatório:

```
Provider → RawResult → Validation → Normalization (BusinessDTO)
        → Suppression check → Deduplication → Company Resolution → Persistence
```

Regras:

1. Nenhum provider importa models nem escreve no banco. Ele devolve DTO.
2. Todo resultado persistido gera `CompanySource` com provider, `external_id`, payload bruto,
   data de coleta e confiança.
3. `UniqueConstraint(provider, external_id)` garante idempotência no banco — reprocessar o mesmo
   resultado não cria empresa duplicada.
4. Cada provider declara `retention_policy` (ver ADR-0004) e seus limites de taxa.
5. Existe sempre um `MockProvider` determinístico: os testes não dependem de rede nem de API paga.

## Consequências

- **Bom:** adicionar ou remover fonte é escrever uma classe e uma linha de configuração.
  Testes de dedup, scoring e CRM rodam offline. Rastreabilidade de origem é estrutural.
- **Ruim:** um DTO comum é sempre um denominador — campos exclusivos de uma fonte ficam em
  `raw_payload` até que valha promovê-los a coluna.
- **Regra:** se aparecer `if provider == "x"` fora do pacote `providers`, a abstração vazou.

## Alternativas rejeitadas

- **Chamar a API direto no service de descoberta** — acopla a regra ao fornecedor e impede testar
  sem rede.
- **Normalizar só na leitura** — dado sujo persistido é dívida permanente; a normalização tem que
  acontecer antes de entrar.
