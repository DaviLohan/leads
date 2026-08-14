"""Contrato comum de toda fonte de dados (ADR-0003).

Regra que dá sentido a este módulo: **provider não escreve no banco**. Ele recebe uma
consulta, fala com o mundo lá fora e devolve `RawResult` — payload cru mais o identificador
na origem. Quem valida, deduplica e persiste é `ingestion.py`.

Por isso aqui não se importa nenhum model. Se um dia aparecer `from apps.companies.models`
neste pacote, a abstração vazou — e junto com ela some a possibilidade de testar dedup,
score e CRM sem rede.

O outro lado do contrato é `retention_policy`: é ela que faz a conformidade com os termos de
cada fonte virar parte do schema em vez de regra escondida em código (ADR-0004).
"""

from __future__ import annotations

import logging
import math
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:  # evita ciclo em tempo de import; só o verificador de tipos lê
    from apps.companies.dedup import CompanyCandidate

logger = logging.getLogger(__name__)


class RetentionPolicy(models.TextChoices):
    """O que pode virar registro permanente, por fonte (ADR-0004).

    `TextChoices` e não `Enum` puro porque o model `Provider` grava exatamente isto: a
    política é coluna, não convenção.
    """

    PERSIST = "PERSIST", _("Pode ser armazenado permanentemente")
    # Só o `external_id` fica; o resto expira e a UI busca ao vivo. É o que os termos do
    # Google Places exigiriam, se um dia ele entrar.
    EPHEMERAL_30D = "EPHEMERAL_30D", _("Expira em 30 dias")


EPHEMERAL_TTL = timedelta(days=30)


class ProviderError(RuntimeError):
    """Falha ao consultar uma fonte externa."""


class RateLimitExceededError(ProviderError):
    """Cota diária da fonte esgotada."""


@dataclass(frozen=True)
class SearchQuery:
    """O que se pede a uma fonte.

    Fala em código IBGE e em tags, não em objetos do domínio: provider não importa model.
    Quem traduz `Category` para as tags da fonte é o chamador, lendo
    `Category.provider_mapping` — é isso que evita categoria hardcoded no provider.
    """

    ibge_code: str
    tags: dict[str, str]
    limit: int = 500


@dataclass(frozen=True)
class RawResult:
    """Um resultado como a fonte devolveu, sem interpretação.

    `payload` é guardado inteiro em `CompanySource.raw_payload`: campo que hoje não vale uma
    coluna pode valer amanhã, e sem o cru não há como reprocessar sem consultar de novo.
    """

    external_id: str
    payload: dict
    confidence: float = 1.0


class BaseProvider(ABC):
    """Uma fonte de dados. Sem estado entre chamadas, sem acesso ao banco."""

    slug: str
    retention_policy: str = RetentionPolicy.PERSIST
    rate_limit_per_second: float = 1.0

    def __init__(self, rate_limit_per_second: float | None = None):
        # O limite efetivo vem da linha do banco, que o `registry` repassa: afrouxar ou
        # apertar precisa valer sem deploy. O atributo de classe é só o piso de segurança
        # para quem instancia a fonte na mão, num shell ou num teste.
        if rate_limit_per_second is not None:
            self.rate_limit_per_second = float(rate_limit_per_second)

    @abstractmethod
    def search_businesses(self, query: SearchQuery) -> Iterable[RawResult]:
        """Busca estabelecimentos. Pode devolver aos poucos; não precisa carregar tudo."""

    @abstractmethod
    def normalize_result(self, raw: RawResult) -> CompanyCandidate:
        """Converte o cru no DTO comum (o `BusinessDTO` do ADR-0003).

        `CompanyCandidate` vive em `companies.dedup` e só entra sob `TYPE_CHECKING`: em
        tempo de import criaria ciclo, e este pacote não pode depender de companies.
        """

    def check_rate_limit(self) -> None:
        """Segura a chamada até haver vaga na janela desta fonte.

        A vaga é tomada no Redis com `cache.add`, que é `SETNX` — atômico. Um contador por
        processo não serviria: os workers do Celery são processos separados, e cada um
        acharia que tem a janela inteira só para si. Contra o Overpass público, isso seria
        abuso da política de uso justo (ADR-0004).

        ponytail: uma vaga por janela, sem fila nem prioridade. Enquanto o limite for ~1
        req/s isso basta. Se um dia precisar de rajada controlada, o caminho é um token
        bucket em Lua no Redis — e aí sim vale a complexidade.
        """
        intervalo = 1.0 / self.rate_limit_per_second
        chave = f"provider:ratelimit:{self.slug}"
        expiracao = max(1, math.ceil(intervalo))

        while not cache.add(chave, 1, timeout=expiracao):
            time.sleep(min(intervalo, 0.25))
