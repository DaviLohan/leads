"""De `slug` para a classe que fala com a fonte.

A linha do banco (`Provider`) guarda configuração — ligada, limite, cota. A classe guarda o
comportamento. O registro é o que une as duas sem que nada fora deste pacote precise saber
qual classe atende qual fonte.

É aqui que a regra do ADR-0003 se paga: `if provider == "osm"` fora deste pacote significa
que a abstração vazou.
"""

from __future__ import annotations

from apps.providers.base import BaseProvider, ProviderError
from apps.providers.mock import MockProvider
from apps.providers.models import Provider
from apps.providers.overpass import OverpassProvider

CLASSES: dict[str, type[BaseProvider]] = {
    OverpassProvider.slug: OverpassProvider,
    MockProvider.slug: MockProvider,
}


class ProviderDisabledError(ProviderError):
    """Fonte existe mas está desligada."""


def get_provider(slug: str) -> BaseProvider:
    """Instancia a fonte pelo slug, já com os limites que estão no banco.

    Recusa fonte desligada em vez de devolvê-la: desligar precisa ter efeito imediato,
    inclusive num worker que já estava rodando.
    """
    classe = CLASSES.get(slug)
    if classe is None:
        raise ProviderError(f"Fonte desconhecida: {slug!r}. Conhecidas: {sorted(CLASSES)}.")

    linha = Provider.objects.filter(slug=slug).first()
    if linha is None:
        raise ProviderError(f"Fonte {slug!r} não está cadastrada. Rode `seed_providers`.")
    if not linha.is_enabled:
        raise ProviderDisabledError(f"Fonte {slug!r} está desabilitada.")

    return classe(rate_limit_per_second=float(linha.rate_limit_per_second))
