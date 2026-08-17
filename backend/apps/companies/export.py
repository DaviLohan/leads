"""Exportação de empresas em CSV.

Uma implementação só, usada pela tela Empresas e pelas listas: o formato do arquivo que sai
daqui é contrato com a planilha de quem vende, e duas versões dele divergiriam na primeira
coluna nova.

Duas decisões que não são detalhe:

- **Teto de linhas.** Sem ele, "exportar tudo" numa base de milhões monta um arquivo que o
  servidor tenta produzir por minutos. O corte é explícito e a última linha do arquivo diz
  que houve corte — truncar em silêncio é pior que recusar.
- **Streaming.** As linhas saem à medida que o cursor anda; montar a lista inteira em memória
  antes de responder é o que derruba o processo justamente na exportação grande.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from typing import Any

#: Teto por exportação. Acima disso, refine o filtro — é mais barato que baixar 200 mil
#: linhas que ninguém vai ligar.
LIMITE_DE_LINHAS = 5_000

COLUNAS = [
    ("name", "Empresa"),
    ("category", "Segmento"),
    ("city", "Cidade"),
    ("uf", "UF"),
    ("phone", "Telefone"),
    ("whatsapp", "WhatsApp"),
    ("email", "E-mail"),
    ("website", "Site"),
    ("website_status", "Situação do site"),
    ("score", "Score"),
    ("opportunities", "Oportunidades"),
    ("lead_stage_name", "Situação no funil"),
    ("discovered_at", "Descoberta em"),
]

ROTULO_DO_SITE = {
    "FOUND": "Site identificado",
    # Literal e obrigatório: afirmar que a empresa não tem site é proibido (CLAUDE.md), e um
    # CSV é justamente onde a frase sai do produto e vira "verdade" na mão de terceiros.
    "NOT_FOUND": "Site oficial não identificado nas fontes analisadas",
    "NOT_CHECKED": "Ainda não verificado",
}


class _Buffer:
    """Escreve devolvendo a linha, em vez de acumular — é o que o `csv` precisa para streamar."""

    def write(self, valor: str) -> str:
        return valor


def linhas_csv(queryset, serializer_class) -> Iterator[str]:
    """Gera o CSV linha a linha, respeitando o teto."""
    escritor = csv.writer(_Buffer())
    yield escritor.writerow([rotulo for _, rotulo in COLUNAS])

    total = 0
    # Fatia em vez de `.iterator()`: o queryset traz `prefetch_related` (oportunidades), e
    # prefetch com cursor é justamente o caso em que o Django volta a consultar por linha.
    # O teto já limita a memória.
    for empresa in queryset[: LIMITE_DE_LINHAS + 1]:
        if total == LIMITE_DE_LINHAS:
            yield escritor.writerow(
                [f"— exportação limitada a {LIMITE_DE_LINHAS} linhas; refine os filtros —"]
            )
            return
        dados = serializer_class(empresa).data
        yield escritor.writerow([_celula(campo, dados) for campo, _ in COLUNAS])
        total += 1


def _celula(campo: str, dados: dict[str, Any]) -> str:
    valor = dados.get(campo)
    if campo == "opportunities":
        return " | ".join(o["name"] for o in valor or [])
    if campo == "website_status":
        return ROTULO_DO_SITE.get(str(valor), str(valor))
    if valor is None:
        return ""
    return str(valor)
