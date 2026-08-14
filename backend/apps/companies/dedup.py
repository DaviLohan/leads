"""Deduplicação: decidir se uma empresa encontrada já existe.

O produto trata empresa como **entidade permanente** (PROJECT_PLAN §1): a mesma clínica
aparece em buscas diferentes, por fontes diferentes, em meses diferentes. Redescobrir não
pode duplicar — e também não pode fundir dois negócios distintos que dividem o sobrenome do
dono. Os dois erros custam caro, e em direções opostas.

Este módulo **só lê**. Devolve uma decisão; quem persiste é o pipeline de ingestão
(ADR-0003: Raw → Validate → Normalize → Dedup → Resolve → Persist). Separar assim é o que
permite testar a decisão sem gravar nada e reprocessar uma busca sem efeito colateral.

## Sinais, em ordem de força

1. **CNPJ** — identificador legal. Bate, é a mesma empresa. `EXACT`.
2. **Domínio** — dois negócios raramente dividem um site. `PROBABLE`, não `EXACT`, por causa
   de franquia e de site institucional de grupo.
3. **Telefone + mesma cidade** — telefone é reaproveitado quando uma empresa fecha e outra
   assume a linha, então sozinho não basta. `PROBABLE`.
4. **Similaridade de nome dentro da cidade** — trigrama no banco. `PROBABLE` acima do limiar
   alto, `POSSIBLE` acima do baixo.
5. Nada bate: `NEW`.

`POSSIBLE` **nunca** funde sozinho (PROJECT_PLAN §4). Vai para revisão humana.

## Por que cidade antes de tudo

Comparar nome par a par em milhões de linhas é O(n²) e não termina (PROJECT_PLAN §3.5). O
blocking key — restringir a busca ao município antes de qualquer comparação — é o que torna
o problema tratável. Candidato sem cidade só usa CNPJ e domínio, que são globais; nunca cai
na comparação por nome, porque sem recorte ela varreria a tabela inteira.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.postgres.search import TrigramSimilarity
from django.db import models

from apps.companies.models import Company, CompanyContact, CompanyWebsite
from apps.core.text import normalize_name
from apps.geography.models import City


class MatchType(models.TextChoices):
    """Quanta certeza a decisão carrega. A Etapa 8 grava isto em `SearchResult`."""

    EXACT = "EXACT", "Correspondência exata"
    PROBABLE = "PROBABLE", "Correspondência provável"
    POSSIBLE = "POSSIBLE", "Correspondência possível"
    NEW = "NEW", "Empresa nova"


@dataclass(frozen=True)
class CompanyCandidate:
    """Empresa vinda de uma fonte, já normalizada, ainda não persistida.

    É o que o pipeline monta depois de normalizar e antes de decidir. A partir da Etapa 7 os
    providers produzem isto; hoje quem monta é o teste.

    Os identificadores já chegam normalizados de `apps.companies.normalization` — o resolver
    não normaliza nada, para não haver duas normalizações divergindo com o tempo.
    """

    name: str
    tax_id: str | None = None
    domain: str | None = None
    phones: tuple[str, ...] = field(default_factory=tuple)
    city: City | None = None

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.name)


@dataclass(frozen=True)
class Resolution:
    """A decisão: com quem bateu, por qual sinal e com que força."""

    match_type: str
    company: Company | None = None
    signal: str = ""
    score: float = 0.0

    @property
    def is_new(self) -> bool:
        return self.match_type == MatchType.NEW

    @property
    def can_merge_automatically(self) -> bool:
        """`POSSIBLE` nunca funde sozinho — vai para revisão humana (PROJECT_PLAN §4).

        A assimetria é deliberada: deixar de fundir gera uma duplicata, que dá para juntar
        depois. Fundir errado destrói o histórico de duas empresas, e desfazer é caro.
        """
        return self.match_type in (MatchType.EXACT, MatchType.PROBABLE)


def _ativas() -> models.QuerySet[Company]:
    """Empresa já fundida não pode voltar a ser candidata — senão o merge se desfaz sozinho."""
    return Company.objects.exclude(status=Company.Status.MERGED)


def _na_cidade(city: City) -> models.QuerySet[Company]:
    """Blocking key: só quem tem endereço no município entra na comparação.

    ponytail: o recorte é o município, não um raio em metros. Para B2B brasileiro o
    município é a unidade certa na esmagadora maioria dos casos; onde falha é em região
    metropolitana que atravessa divisa (ABC, Grande Curitiba). Se isso doer, o caminho é
    `CompanyAddress.location__distance_lte` — o índice GiST já existe, sai de graça.
    """
    return _ativas().filter(addresses__city=city).distinct()


def resolve(candidate: CompanyCandidate) -> Resolution:
    """Decide se `candidate` já existe. Só lê; não grava nada."""
    for sinal in (_por_cnpj, _por_dominio, _por_telefone, _por_nome):
        resultado = sinal(candidate)
        if resultado is not None:
            return resultado
    return Resolution(match_type=MatchType.NEW)


def _por_cnpj(candidate: CompanyCandidate) -> Resolution | None:
    if not candidate.tax_id:
        return None
    empresa = _ativas().filter(tax_id=candidate.tax_id).first()
    if empresa is None:
        return None
    return Resolution(MatchType.EXACT, empresa, signal="tax_id", score=1.0)


def _por_dominio(candidate: CompanyCandidate) -> Resolution | None:
    if not candidate.domain:
        return None
    site = (
        CompanyWebsite.objects.filter(domain=candidate.domain)
        .exclude(company__status=Company.Status.MERGED)
        .select_related("company")
        .first()
    )
    if site is None:
        return None
    return Resolution(MatchType.PROBABLE, site.company, signal="domain", score=0.9)


def _por_telefone(candidate: CompanyCandidate) -> Resolution | None:
    """Telefone só vale acompanhado da cidade.

    Linha desativada é reatribuída: o número da pizzaria que fechou vira o da barbearia que
    abriu. Sem o recorte geográfico, esse reaproveitamento fundiria os dois negócios.
    """
    if not candidate.phones or candidate.city is None:
        return None

    contato = (
        CompanyContact.objects.filter(
            value_normalized__in=candidate.phones,
            kind__in=(CompanyContact.Kind.PHONE, CompanyContact.Kind.WHATSAPP),
            company__addresses__city=candidate.city,
        )
        .exclude(company__status=Company.Status.MERGED)
        .select_related("company")
        .first()
    )
    if contato is None:
        return None
    return Resolution(MatchType.PROBABLE, contato.company, signal="phone+city", score=0.8)


def _por_nome(candidate: CompanyCandidate) -> Resolution | None:
    """Similaridade por trigrama, sempre dentro do município.

    O cálculo acontece no Postgres, com o índice GIN de `normalized_name`. Trazer os nomes
    para o Python e comparar aqui seria O(n²) sobre a tabela inteira — o erro que a
    PROJECT_PLAN §3.5 manda evitar.
    """
    if candidate.city is None or not candidate.normalized_name:
        return None

    melhor = (
        _na_cidade(candidate.city)
        .annotate(similaridade=TrigramSimilarity("normalized_name", candidate.normalized_name))
        .filter(similaridade__gte=settings.DEDUP_NAME_SIMILARITY_POSSIBLE)
        .order_by("-similaridade")
        .first()
    )
    if melhor is None:
        return None

    score = float(melhor.similaridade)
    tipo = (
        MatchType.PROBABLE
        if score >= settings.DEDUP_NAME_SIMILARITY_PROBABLE
        else MatchType.POSSIBLE
    )
    return Resolution(tipo, melhor, signal="name+city", score=score)
