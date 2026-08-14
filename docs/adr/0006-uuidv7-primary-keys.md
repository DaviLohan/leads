# ADR-0006 — UUIDv7 como chave primária

**Status:** aceito · 2026-08-13

## Contexto

O requisito pede UUID como identificador público/interno principal. Faz sentido: não expõe
volume de negócio, permite gerar ID antes de gravar e evita colisão em ingestão paralela.

O problema é o UUIDv4: valores aleatórios em índice B-tree espalham inserções por toda a árvore.
Em tabelas de milhões de linhas — que é exatamente o alvo deste produto — isso significa mais
páginas sujas, cache menos eficaz e índices maiores.

UUIDv7 (RFC 9562) resolve: 48 bits de timestamp em milissegundos no início, resto aleatório.
Ordenado no tempo, mantendo o formato UUID. A stdlib do Python 3.12 não tem `uuid7`.

## Decisão

PK `UUIDField(primary_key=True, default=core.ids.uuid7, editable=False)` em `core.models.BaseModel`,
herdado por todos os models.

O gerador é uma função de ~10 linhas em `apps/core/ids.py` — sem dependência nova para algo que
é aritmética de bytes.

## Consequências

- **Bom:** localidade de inserção parecida com a de um inteiro sequencial, com todas as
  vantagens do UUID. Ordenar por PK dá aproximadamente ordem cronológica. Migrar de v4 para v7
  depois seria reescrever todas as PKs e FKs — evitado.
- **Ruim:** 16 bytes por chave contra 8 de `bigint`, refletido em cada FK. Aceito em troca de não
  expor sequência e de gerar ID no cliente.
- **Vazamento:** o ID revela o instante de criação em milissegundos. Para um cadastro de empresas
  públicas isso é irrelevante.
- **Atenção:** `uuid7()` é usado como `default`, nunca chamado no import do módulo.

## Alternativas rejeitadas

- **UUIDv4** — fragmentação de índice no exato regime de volume que o produto almeja.
- **`bigint` PK + coluna `public_id` UUID** — teoricamente o melhor dos dois, mas dobra o
  identificador: toda query precisa saber qual usar, e todo bug de "usei o ID errado" passa a
  existir. Não compensa.
- **ULID** — mesmas propriedades, mas não é tipo nativo do Postgres nem do Django; UUIDv7 entrega
  o mesmo com suporte de primeira classe.
