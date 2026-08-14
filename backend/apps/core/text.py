"""Normalização de texto para comparação e busca.

Nome digitado por humano varia em acento, caixa e espaço — "São Paulo", "SAO PAULO" e
"Sao  Paulo" são a mesma cidade. Guardar a forma normalizada em coluna própria (e indexá-la)
permite comparar e buscar sem `unaccent()` a cada consulta, que não usa índice.

Usado por `geography.City.normalized_name` e, a partir da Etapa 5, por
`companies.Company.normalized_name` e pelo blocking key da deduplicação (Etapa 6) —
por isso mora em `core`, não em um app de domínio.
"""

from __future__ import annotations

import unicodedata


def normalize_name(value: str) -> str:
    """Devolve `value` sem acento, em minúsculas e com espaços colapsados.

    >>> normalize_name("  SÃO   Paulo ")
    'sao paulo'
    >>> normalize_name("Açaí")
    'acai'

    A decomposição NFKD separa a letra do sinal diacrítico (`ç` → `c` + cedilha); descartar
    os caracteres combinantes remove o acento sem tabela de substituição própria.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.casefold().split())
