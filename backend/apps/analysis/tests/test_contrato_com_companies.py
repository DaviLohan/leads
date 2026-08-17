"""Os literais que `companies` mantém à mão sobre `analysis`.

`companies/queries.py` não pode importar `analysis` (ordem de dependência do CLAUDE.md), e
por isso repete dois valores de status como constante. Repetição sem guarda apodrece: alguém
renomeia a enum aqui, a listagem de empresas para de mostrar oportunidade, e nada quebra.

Este teste mora em `analysis` de propósito — é o app de cima, e pode importar o de baixo.
"""

from apps.analysis.models import Opportunity, WebsiteScan
from apps.companies.queries import OPPORTUNITY_OPEN, SCAN_BROKEN


def test_oportunidade_aberta_bate_com_a_enum():
    assert OPPORTUNITY_OPEN == Opportunity.Status.OPEN


def test_site_com_problema_bate_com_a_enum():
    assert set(SCAN_BROKEN) == {WebsiteScan.Status.UNREACHABLE, WebsiteScan.Status.ERROR}
    # `BLOCKED` fica fora: recusa do guard de SSRF é segurança, não site quebrado.
    assert WebsiteScan.Status.BLOCKED not in SCAN_BROKEN
