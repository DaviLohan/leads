"""Motor de pontuação, com breakdown auditável (ADR-0008).

Reusa os mesmos predicados de `rules.py` que o Opportunity Engine — é a "mesma mecânica"
que o ADR exige, e não um segundo motor de regras vivendo em paralelo.

O que a pontuação mede: **quanto vale ir atrás desta empresa**, não quão boa ela é. Quem não
tem site é lead melhor para quem vende site. Por isso "sem site" soma pontos.

Toda parcela grava regra, pontos e justificativa. Um número de 0 a 100 sem explicação não
convence ninguém do time comercial, e não dá para depurar quando estiver errado.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

from django.db import transaction

from apps.analysis.models import Score, ScoreComponent, ScoreRule
from apps.analysis.opportunities import build_context
from apps.analysis.rules import CompanyContext, evaluate
from apps.companies.models import Company

logger = logging.getLogger(__name__)

MINIMO, MAXIMO = 0, 100


@dataclass
class Breakdown:
    """O resultado do cálculo, antes de virar linha no banco."""

    value: int = 0
    version: str = ""
    parcelas: list[tuple[str, int, str]] = field(default_factory=list)

    @property
    def bruto(self) -> int:
        return sum(pontos for _, pontos, _ in self.parcelas)


def ruleset_version(regras: list[ScoreRule]) -> str:
    """Identifica o conjunto de regras que produziu um score.

    É um hash do conteúdo — código, pontos e parâmetros de cada regra ativa — e não um número
    que alguém precisa lembrar de incrementar. Versão que depende de disciplina humana fica
    desatualizada exatamente quando mais importa.

    Sem isso, comparar dois scores calculados em semanas diferentes é comparar coisas
    distintas, e ninguém saberia que os pesos mudaram no meio.
    """
    conteudo = json.dumps(
        sorted((r.code, r.points, r.params) for r in regras),
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(conteudo.encode()).hexdigest()[:16]


def compute(ctx: CompanyContext, regras: list[ScoreRule] | None = None) -> Breakdown:
    """Calcula a pontuação a partir de um contexto. Não toca no banco.

    Separado da persistência de propósito: dá para simular o efeito de mudar um peso sem
    gravar nada, e o teste exercita a aritmética sem precisar de linha no banco.
    """
    if regras is None:
        regras = list(ScoreRule.objects.filter(is_active=True))

    resultado = Breakdown(version=ruleset_version(regras))

    for regra in regras:
        acionou = evaluate(regra.code, ctx, regra.params)
        if acionou is None:
            # Regra desconhecida ou com defeito: não pontua e não derruba o cálculo
            # (ADR-0008, regra 1). Um UPDATE errado no banco não pode zerar o radar.
            continue
        if acionou:
            resultado.parcelas.append((regra.code, regra.points, regra.reason_template))

    # O corte em 0 a 100 é no fim, sobre a soma (ADR-0008, regra 3). Cortar parcela a parcela
    # esconderia que o conjunto de regras passou do teto — e o breakdown deixaria de somar o
    # total exibido, que é o pior tipo de relatório: o que não fecha.
    resultado.value = max(MINIMO, min(MAXIMO, resultado.bruto))
    return resultado


def score_company(company: Company) -> Score:
    """Calcula e grava a pontuação da empresa, com o breakdown.

    Idempotente: recalcular substitui as parcelas em vez de empilhá-las. Empresa sem regras
    cadastradas recebe zero, não erro (ADR-0008, seção operacional).
    """
    breakdown = compute(build_context(company))

    with transaction.atomic():
        score, _ = Score.objects.update_or_create(
            company=company,
            defaults={"value": breakdown.value, "version": breakdown.version},
        )
        # Substitui em vez de acumular: o breakdown tem de refletir o cálculo atual, e
        # parcela velha de regra desativada mentiria sobre de onde veio o número.
        score.components.all().delete()
        ScoreComponent.objects.bulk_create(
            [
                ScoreComponent(score=score, rule_code=codigo, points=pontos, reason=motivo)
                for codigo, pontos, motivo in breakdown.parcelas
            ]
        )

    logger.info(
        "Pontuação calculada",
        extra={
            "company": str(company.pk),
            "value": breakdown.value,
            "bruto": breakdown.bruto,
            "version": breakdown.version,
        },
    )
    return score
