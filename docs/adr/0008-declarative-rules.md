# ADR-0008 — Regras configuráveis: predicados registrados em código, parâmetros no banco

**Status:** aceito · 2026-08-13

## Contexto

Três subsistemas precisam de regras que mudam sem deploy: score do lead (pesos como "+30 sem
site"), detecção de oportunidades e recomendação de sistemas por segmento. O requisito é claro:
esses valores não podem ser número mágico espalhado pelo código.

O caminho natural — guardar a regra inteira no banco — leva a uma linguagem de expressão
interpretada em runtime. Isso significa parser próprio, ou pior, `eval()`. Regra vira dado não
testável, não versionado e sem revisão de código; um erro de digitação no banco derruba o motor
de scoring em produção.

## Decisão

Divisão de responsabilidade:

- **O código** define *como* avaliar. Predicados nomeados e registrados:

```python
@rule("sem_site")
def sem_site(ctx: CompanyContext, params: dict) -> bool:
    # Exige que a análise tenha acontecido: enquanto for NOT_CHECKED, a resposta
    # honesta é "ainda não sei", não "não tem".
    return not ctx.has_website and ctx.website_status == "NOT_FOUND"
```

- **O banco** define *se* a regra está ativa, *quanto* vale e com *quais parâmetros*:

```
ScoreRule(code="sem_site", points=30, is_active=True, params={})
ScoreRule(code="min_reviews", points=10, is_active=True, params={"threshold": 20})
```

Regras:

1. Código de regra desconhecido no banco é ignorado com log de aviso — nunca quebra o cálculo.
2. Toda avaliação grava `ScoreComponent` com código, pontos e justificativa — o breakdown exigido.
3. Score é limitado a 0–100 no fim; o motor guarda a versão do conjunto de regras usada.
4. Sem `eval`, sem `exec`, sem expressão em string vinda do banco. Nunca.
5. Mesma mecânica para `OpportunityType.rule_params` e para as recomendações por segmento.

## Consequências

- **Bom:** ajustar peso é UPDATE, sem deploy. A lógica continua tipada, testável e revisada em PR.
  O breakdown explica cada ponto para o time comercial.
- **Ruim:** criar um tipo *novo* de regra ainda exige código. É deliberado — regra nova é lógica
  nova, e lógica nova merece revisão.
- **Operacional:** o seed cadastra o conjunto inicial de regras; ambiente sem regras cadastradas
  produz score 0, não erro.

## Alternativas rejeitadas

- **Números fixos no código** — vetado pelo requisito; qualquer ajuste comercial vira deploy.
- **DSL/expressão no banco** — interpretador caseiro, sem tipagem, sem teste, sem revisão. É o
  modo mais comum de transformar configuração em incidente.
- **Motor de regras de terceiros** — dependência pesada para o que um dicionário de funções e
  uma tabela de pesos resolvem.
