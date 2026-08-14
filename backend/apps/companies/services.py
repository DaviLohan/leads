"""Operações de escrita sobre empresas.

Merge é a operação mais destrutiva do sistema: junta o histórico de dois registros e
aposenta um deles. Roda em `transaction.atomic` e grava auditoria (CLAUDE.md) — se quebrar
no meio, nada acontece; se der certo, fica registrado quem fez e o que moveu.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import models, transaction
from django.http import HttpRequest

from apps.companies.models import (
    Company,
    CompanyAddress,
    CompanyCategory,
    CompanyContact,
    CompanySocialProfile,
    CompanyWebsite,
)
from apps.core.audit import record_audit
from apps.core.models import AuditLog


class MergeError(ValueError):
    """Merge que não pode acontecer."""


@dataclass(frozen=True)
class MergeResult:
    survivor: Company
    merged: Company
    moved: dict[str, int]
    discarded: dict[str, int]


# Satélite -> campos que já são únicos por empresa no banco. Mover um satélite que colide
# com um que a sobrevivente já tem violaria a UniqueConstraint e derrubaria o merge inteiro.
#
# Guarda o manager, não a classe: `Model` base não declara `objects` (quem o injeta é a
# metaclasse do Django), e o manager já traz junto o `.model` para o nome do satélite.
SATELITES: list[tuple[models.Manager, tuple[str, ...]]] = [
    (CompanyContact.objects, ("kind", "value_normalized")),
    (CompanyWebsite.objects, ("domain",)),
    (CompanySocialProfile.objects, ("network", "url")),
    (CompanyCategory.objects, ("category_id",)),
    # Endereço não tem unicidade: dois endereços são dois endereços.
    (CompanyAddress.objects, ()),
]


def _chave(obj, campos: tuple[str, ...]) -> tuple:
    return tuple(getattr(obj, campo) for campo in campos)


@transaction.atomic
def merge_companies(
    *,
    survivor: Company,
    duplicate: Company,
    actor=None,
    request: HttpRequest | None = None,
) -> MergeResult:
    """Funde `duplicate` em `survivor`. Idempotente por constraint, não por checagem.

    A duplicata não é apagada: vira `status=MERGED` apontando para a sobrevivente. Apagar
    perderia o rastro de quem chegasse pelo id antigo — link salvo, `external_id` de fonte,
    relatório velho.

    Satélite que colide com um que a sobrevivente já tem é **descartado**, não movido: o
    mesmo telefone nas duas empresas é o mesmo telefone, e insistir violaria a
    UniqueConstraint e derrubaria a transação inteira.
    """
    if survivor.pk == duplicate.pk:
        raise MergeError("Uma empresa não pode ser fundida em si mesma.")

    # Bloqueia as duas linhas ANTES de validar. Duas razões, e as duas doem:
    #
    # 1. O objeto que chega pode estar velho. Quem já fundiu esta empresa numa transação
    #    anterior continua com `status=ACTIVE` na memória, e validar contra isso deixaria
    #    fundir duas vezes.
    # 2. Validar e depois agir sem lock é TOCTOU: dois workers passariam os dois pela
    #    verificação e produziriam satélites duplicados e duas auditorias contraditórias.
    #
    # Com o lock antes, quem chega em segundo espera e lê o estado já gravado.
    locked = {
        c.pk: c
        for c in Company.objects.select_for_update().filter(pk__in=[survivor.pk, duplicate.pk])
    }
    if len(locked) != 2:
        raise MergeError("Uma das empresas não existe mais.")
    survivor, duplicate = locked[survivor.pk], locked[duplicate.pk]

    if duplicate.status == Company.Status.MERGED:
        raise MergeError(f"{duplicate} já foi fundida anteriormente.")
    if survivor.status == Company.Status.MERGED:
        raise MergeError(f"{survivor} já foi fundida e não pode receber outra.")

    # Dois CNPJs válidos e diferentes são duas pessoas jurídicas. Pode haver caso legítimo
    # (matriz absorvendo filial), mas ele é raro o bastante para exigir decisão explícita:
    # quem quiser mesmo, limpa um dos dois antes. O padrão recusa.
    if survivor.tax_id and duplicate.tax_id and survivor.tax_id != duplicate.tax_id:
        raise MergeError(
            f"CNPJs diferentes ({survivor.tax_id} e {duplicate.tax_id}): são pessoas "
            "jurídicas distintas. Limpe um dos dois antes se o merge for mesmo intencional."
        )

    moved: dict[str, int] = {}
    discarded: dict[str, int] = {}

    for satelites, campos_unicos in SATELITES:
        nome = satelites.model.__name__
        existentes = (
            {_chave(o, campos_unicos) for o in satelites.filter(company=survivor)}
            if campos_unicos
            else set()
        )

        for obj in satelites.filter(company=duplicate):
            if campos_unicos and _chave(obj, campos_unicos) in existentes:
                obj.delete()
                discarded[nome] = discarded.get(nome, 0) + 1
                continue
            # `is_primary` da duplicata não pode disputar com o da sobrevivente: quem já
            # era principal continua sendo.
            if hasattr(obj, "is_primary"):
                obj.is_primary = False
            obj.company = survivor
            obj.save()
            moved[nome] = moved.get(nome, 0) + 1

    _herdar_campos_vazios(survivor, duplicate)

    # Quem já apontava para a duplicata passa a apontar para a sobrevivente: senão a cadeia
    # vira A -> B -> C e quem chegar em A precisa seguir dois saltos.
    Company.objects.filter(merged_into=duplicate).update(merged_into=survivor)

    duplicate.status = Company.Status.MERGED
    duplicate.merged_into = survivor
    duplicate.save(update_fields=["status", "merged_into", "updated_at"])
    survivor.save()

    record_audit(
        action=AuditLog.Action.MERGE,
        object_type="companies.Company",
        object_id=survivor.pk,
        actor=actor,
        request=request,
        changes={
            "survivor": str(survivor.pk),
            "merged": str(duplicate.pk),
            "merged_name": duplicate.name,
            "moved": moved,
            "discarded": discarded,
        },
    )

    return MergeResult(survivor=survivor, merged=duplicate, moved=moved, discarded=discarded)


# Campos onde "a duplicata sabia e a sobrevivente não" é ganho puro. `name` e `status` ficam
# de fora de propósito: são identidade, e sobrescrevê-los é decisão humana, não automática.
CAMPOS_HERDAVEIS = ("legal_name", "trade_name", "description")


def _herdar_campos_vazios(survivor: Company, duplicate: Company) -> None:
    """A sobrevivente adota o que ela não tem e a duplicata tinha. Nunca sobrescreve."""
    for campo in CAMPOS_HERDAVEIS:
        if not getattr(survivor, campo) and getattr(duplicate, campo):
            setattr(survivor, campo, getattr(duplicate, campo))

    # CNPJ à parte: é único no banco, então a duplicata precisa largá-lo na mesma transação
    # antes de a sobrevivente assumir. O caso de CNPJs diferentes já foi recusado lá em cima.
    if duplicate.tax_id and not survivor.tax_id:
        survivor.tax_id = duplicate.tax_id
        duplicate.tax_id = None
        duplicate.save(update_fields=["tax_id"])

    if duplicate.review_count > survivor.review_count:
        survivor.rating = duplicate.rating
        survivor.review_count = duplicate.review_count

    if duplicate.last_seen_at and (
        survivor.last_seen_at is None or duplicate.last_seen_at > survivor.last_seen_at
    ):
        survivor.last_seen_at = duplicate.last_seen_at
