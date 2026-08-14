"""O pipeline do ADR-0003, de ponta a ponta.

    Provider → RawResult → Validação → Normalização (DTO)
            → Supressão → Deduplicação → Resolução → Persistência

Este é o único módulo do pacote que escreve no banco. Os providers devolvem DTO e não sabem
que existe ORM — é o que permite trocar de fonte sem tocar em regra de negócio, e testar
dedup, score e CRM sem rede.

A idempotência não vem de `if exists` em Python: vem da `UniqueConstraint(provider,
external_id)` em `CompanySource` mais `get_or_create`. Reprocessar a mesma busca atualiza,
não duplica — mesmo com dois workers no mesmo job.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone

from apps.companies.dedup import CompanyCandidate, MatchType, resolve
from apps.companies.models import Company, CompanyAddress, CompanyContact, CompanyWebsite
from apps.geography.models import City
from apps.providers.base import BaseProvider, RawResult, SearchQuery
from apps.providers.models import CompanySource, Provider, ProviderUsage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionRecord:
    """A decisão tomada sobre um resultado.

    Existe para que `discovery` (Etapa 8) grave `SearchResult` sem repetir o laço de
    ingestão. É dado devolvido, não callback: quem chama decide o que fazer com a lista, e
    o pipeline não passa a executar código de terceiros no meio de uma transação.
    """

    external_id: str
    match_type: str
    company_id: object | None = None
    score: float = 0.0
    payload: dict = field(default_factory=dict)


@dataclass
class IngestionReport:
    """O que a varredura produziu. Vira progresso de `SearchJob` na Etapa 8."""

    created: int = 0
    updated: int = 0
    review: int = 0
    skipped: int = 0
    reasons: Counter = field(default_factory=Counter)
    records: list[IngestionRecord] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.review + self.skipped


def ingest_city(
    *,
    provider: BaseProvider,
    provider_row: Provider,
    city: City,
    tags: dict[str, str],
    organization=None,
    limit: int = 500,
) -> IngestionReport:
    """Varre um município numa fonte e persiste o que achar.

    Cada resultado é uma transação própria, não uma só para a varredura inteira: um
    endereço torto no item 300 não pode desfazer os 299 que entraram certos. O que precisa
    ser atômico é a unidade — empresa mais satélites mais procedência.
    """
    relatorio = IngestionReport()
    consulta = SearchQuery(ibge_code=city.ibge_code, tags=tags, limit=limit)

    _contabilizar_requisicao(provider_row, organization)

    for bruto in provider.search_businesses(consulta):
        try:
            with transaction.atomic():
                _ingerir_um(provider, provider_row, bruto, city, relatorio)
        except Exception:
            # Um item ruim não derruba a varredura, mas nunca é engolido em silêncio
            # (CLAUDE.md): vai para o log com a origem, que é o que permite reprocessar.
            logger.exception(
                "Falha ao ingerir resultado",
                extra={"provider": provider.slug, "external_id": bruto.external_id},
            )
            relatorio.skipped += 1
            relatorio.reasons["erro"] += 1
            _contabilizar_erro(provider_row, organization)

    return relatorio


def _ingerir_um(
    provider: BaseProvider,
    provider_row: Provider,
    bruto: RawResult,
    city: City,
    relatorio: IngestionReport,
) -> None:
    candidato = provider.normalize_result(bruto)

    if not _valido(candidato):
        relatorio.skipped += 1
        relatorio.reasons["sem nome utilizável"] += 1
        return

    candidato = _com_cidade(candidato, city)

    # TODO(Etapa 12): a checagem de supressão da LGPD entra exatamente aqui, entre a
    # normalização e a dedup — antes de persistir e antes de enfileirar contato
    # (PROJECT_PLAN §3.4). `SuppressionEntry` ainda não existe; quando existir, é neste
    # ponto que telefone, e-mail, domínio e CNPJ suprimidos param a ingestão do registro.

    # A procedência é consultada antes da dedup: se esta fonte já viu este `external_id`,
    # a empresa dele é a resposta, sem precisar adivinhar de novo.
    fonte = (
        CompanySource.objects.select_related("company")
        .filter(provider=provider_row, external_id=bruto.external_id)
        .first()
    )
    if fonte is not None:
        _atualizar(fonte.company, candidato, city)
        _gravar_fonte(fonte.company, provider_row, bruto, candidato)
        relatorio.updated += 1
        relatorio.reasons["já conhecida por esta fonte"] += 1
        relatorio.records.append(
            IngestionRecord(
                external_id=bruto.external_id,
                match_type=MatchType.EXACT,
                company_id=fonte.company_id,
                score=1.0,
                payload=_resumo(candidato),
            )
        )
        return

    decisao = resolve(candidato)

    if decisao.match_type == MatchType.POSSIBLE:
        # Nunca funde sozinho: vira `SearchResult` com `match_type=POSSIBLE`, que é a fila
        # de revisão humana (PROJECT_PLAN §4). Nenhuma empresa é criada nem alterada.
        relatorio.records.append(
            IngestionRecord(
                external_id=bruto.external_id,
                match_type=MatchType.POSSIBLE,
                company_id=decisao.matched.pk,
                score=decisao.score,
                payload=_resumo(candidato),
            )
        )
        logger.info(
            "Correspondência possível, deixada para revisão humana",
            extra={
                "candidato": candidato.name,
                "empresa": str(decisao.matched.pk),
                "score": round(decisao.score, 3),
            },
        )
        relatorio.review += 1
        relatorio.reasons["revisão humana"] += 1
        return

    if decisao.is_new:
        empresa = _criar(candidato, city)
        relatorio.created += 1
    else:
        empresa = decisao.matched
        _atualizar(empresa, candidato, city)
        relatorio.updated += 1
        relatorio.reasons[f"reconhecida por {decisao.signal}"] += 1

    _gravar_fonte(empresa, provider_row, bruto, candidato)
    _enfileirar_analise(empresa)
    relatorio.records.append(
        IngestionRecord(
            external_id=bruto.external_id,
            match_type=decisao.match_type,
            company_id=empresa.pk,
            score=decisao.score,
            payload=_resumo(candidato),
        )
    )


def _enfileirar_analise(empresa: Company) -> None:
    """Agenda a análise do site da empresa recém-descoberta (PROJECT_PLAN §4).

    `transaction.on_commit` não é preciosismo: enfileirar dentro da transação faz a task
    começar antes do COMMIT e não encontrar a empresa. O bug é intermitente — só aparece
    quando o worker é rápido o bastante — e é dos que somem quando se vai investigar.

    O import é local porque `providers` não deve depender de `analysis` em tempo de módulo:
    a ordem do CLAUDE.md é `providers` <- `analysis`, e importar no topo inverteria a seta.
    """
    if not settings.ANALYSIS_AUTO_SCAN_ON_DISCOVERY:
        return

    from apps.analysis.tasks import scan_company_task

    transaction.on_commit(lambda: scan_company_task.delay(str(empresa.pk)))


def _resumo(candidato: CompanyCandidate) -> dict:
    """O DTO em JSON, sem a `City` — que é objeto de banco e não serializa.

    Guardado em `SearchResult.normalized_payload`: é o que a fonte disse **depois de
    normalizado**, útil para entender por que a dedup decidiu o que decidiu. O payload cru
    fica em `CompanySource`, uma vez só por fonte.
    """
    return {
        "name": candidato.name,
        "normalized_name": candidato.normalized_name,
        "tax_id": candidato.tax_id,
        "domain": candidato.domain,
        "phones": list(candidato.phones),
        "emails": list(candidato.emails),
        "street": candidato.street,
        "number": candidato.number,
        "district": candidato.district,
        "postal_code": candidato.postal_code,
        "latitude": candidato.latitude,
        "longitude": candidato.longitude,
    }


def _valido(candidato: CompanyCandidate) -> bool:
    """Validação, o passo que o ADR-0003 exige antes de normalizar virar persistir."""
    return bool(candidato.name.strip()) and bool(candidato.normalized_name)


def _com_cidade(candidato: CompanyCandidate, city: City) -> CompanyCandidate:
    """A cidade vem da busca, não da fonte: é o recorte que a dedup usa como blocking key."""
    from dataclasses import replace

    return replace(candidato, city=city)


def _criar(candidato: CompanyCandidate, city: City) -> Company:
    empresa = Company.objects.create(
        name=candidato.name,
        legal_name=candidato.legal_name,
        description=candidato.description,
        tax_id=candidato.tax_id,
        # Ausência na fonte não é ausência no mundo (ADR-0004, CLAUDE.md): a empresa nasce
        # com o site "ainda não verificado". Quem decide entre FOUND e NOT_FOUND é o
        # scanner da Etapa 9, depois de olhar.
        website_status=(
            Company.WebsiteStatus.FOUND if candidato.domain else Company.WebsiteStatus.NOT_CHECKED
        ),
        last_seen_at=timezone.now(),
    )
    _sincronizar_satelites(empresa, candidato, city)
    return empresa


def _atualizar(empresa: Company, candidato: CompanyCandidate, city: City) -> None:
    """Redescobrir enriquece, nunca sobrescreve.

    O nome e os campos já preenchidos ficam como estão: uma fonte pobre não pode apagar o
    que uma fonte boa trouxe antes. Só o que está vazio é adotado.
    """
    mudou = []
    for campo in ("legal_name", "description", "tax_id"):
        if not getattr(empresa, campo) and getattr(candidato, campo):
            setattr(empresa, campo, getattr(candidato, campo))
            mudou.append(campo)

    if candidato.domain and empresa.website_status != Company.WebsiteStatus.FOUND:
        empresa.website_status = Company.WebsiteStatus.FOUND
        mudou.append("website_status")

    empresa.last_seen_at = timezone.now()
    empresa.save(update_fields=[*mudou, "last_seen_at", "updated_at"])
    _sincronizar_satelites(empresa, candidato, city)


def _sincronizar_satelites(empresa: Company, candidato: CompanyCandidate, city: City) -> None:
    """Acrescenta o que falta. `get_or_create` sobre a constraint, não `if exists`."""
    for telefone in candidato.phones:
        CompanyContact.objects.get_or_create(
            company=empresa,
            kind=CompanyContact.Kind.PHONE,
            value_normalized=telefone,
            defaults={"value_raw": telefone, "is_primary": not empresa.contacts.exists()},
        )

    for email in candidato.emails:
        CompanyContact.objects.get_or_create(
            company=empresa,
            kind=CompanyContact.Kind.EMAIL,
            value_normalized=email,
            defaults={"value_raw": email},
        )

    if candidato.domain:
        CompanyWebsite.objects.get_or_create(
            company=empresa,
            domain=candidato.domain,
            defaults={
                "url": candidato.website_url[:500],
                "is_primary": not empresa.websites.exists(),
            },
        )

    if not empresa.addresses.filter(city=city).exists():
        localizacao = (
            Point(float(candidato.longitude), float(candidato.latitude), srid=4326)
            if candidato.latitude is not None and candidato.longitude is not None
            else None
        )
        CompanyAddress.objects.create(
            company=empresa,
            city=city,
            street=candidato.street[:200],
            number=candidato.number[:20],
            district=candidato.district[:100],
            postal_code=candidato.postal_code if len(candidato.postal_code) == 8 else "",
            location=localizacao,
            is_primary=not empresa.addresses.exists(),
        )


def _gravar_fonte(
    empresa: Company,
    provider_row: Provider,
    bruto: RawResult,
    candidato: CompanyCandidate,
) -> None:
    """Registra a procedência. `expires_at` sai da política de retenção da fonte (ADR-0004).

    Fonte efêmera guarda o payload com prazo; só o `external_id` é permanente. É isso que
    faz a conformidade ser schema, e não disciplina.
    """
    CompanySource.objects.update_or_create(
        provider=provider_row,
        external_id=bruto.external_id,
        defaults={
            "company": empresa,
            "raw_payload": bruto.payload,
            "collected_at": timezone.now(),
            "expires_at": provider_row.expires_at(),
            "confidence": bruto.confidence,
        },
    )


def _contabilizar_requisicao(provider_row: Provider, organization) -> None:
    _incrementar(provider_row, organization, "request_count")


def _contabilizar_erro(provider_row: Provider, organization) -> None:
    _incrementar(provider_row, organization, "error_count")


def _incrementar(provider_row: Provider, organization, campo: str) -> None:
    """Soma no banco, não em Python: `F()` não tem corrida entre workers."""
    if organization is None:
        # `ProviderUsage` é `TenantModel`: sem organização não há a quem contabilizar.
        # Acontece em `shell` e em teste, e não é motivo para quebrar a varredura.
        return

    from django.db.models import F

    uso, _ = ProviderUsage.objects.get_or_create(
        provider=provider_row, organization=organization, period=timezone.localdate()
    )
    ProviderUsage.objects.filter(pk=uso.pk).update(**{campo: F(campo) + 1})
