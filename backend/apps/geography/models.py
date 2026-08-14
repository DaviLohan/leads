"""Geografia: unidades federativas e municípios do IBGE.

Dado público e global — não pertence a nenhuma organização (ADR-0007), então herda de
`BaseModel` e não de `TenantModel`.

O código IBGE é a chave natural: dois dígitos para o estado (`41` = Paraná) e sete para o
município (`4113700` = Londrina), sendo os dois primeiros do município os do seu estado.
É ele, e não o nome, que dá idempotência ao importador — município é renomeado, código não.
"""

from __future__ import annotations

# O módulo do GIS reexporta tudo de `django.db.models` e acrescenta os campos geográficos.
from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.core.text import normalize_name


class Region(models.TextChoices):
    """Grandes regiões do IBGE. As siglas são as que a própria API devolve."""

    NORTE = "N", _("Norte")
    NORDESTE = "NE", _("Nordeste")
    SUDESTE = "SE", _("Sudeste")
    SUL = "S", _("Sul")
    CENTRO_OESTE = "CO", _("Centro-Oeste")


class State(BaseModel):
    """Unidade federativa. Vinte e sete linhas, estáveis."""

    ibge_code = models.CharField(_("código IBGE"), max_length=2, unique=True)
    uf = models.CharField(_("UF"), max_length=2, unique=True)
    name = models.CharField(_("nome"), max_length=64)
    region = models.CharField(_("região"), max_length=2, choices=Region.choices)

    class Meta:
        verbose_name = _("estado")
        verbose_name_plural = _("estados")
        ordering = ["name"]
        constraints = [
            # Integridade no banco, não só na aplicação (CLAUDE.md). Um importador com bug
            # não consegue gravar "PR " nem "41x".
            models.CheckConstraint(
                condition=models.Q(ibge_code__regex=r"^\d{2}$"),
                name="state_ibge_code_2_digitos",
            ),
            models.CheckConstraint(
                condition=models.Q(uf__regex=r"^[A-Z]{2}$"),
                name="state_uf_2_maiusculas",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.uf})"


class City(BaseModel):
    """Município.

    `centroid` fica nulo na Etapa 4: a API de localidades do IBGE não devolve coordenada, e
    quem precisa dela é o particionamento geográfico das buscas (Etapa 8). Preencher antes
    disso custaria 27 downloads de malha para um dado que ninguém lê ainda.

    `boundary` (multipolygon) não existe: o ERD o marca como opcional, "com necessidade real
    de contorno". Nenhuma ainda.
    """

    state = models.ForeignKey(
        State,
        on_delete=models.PROTECT,
        related_name="cities",
        verbose_name=_("estado"),
    )
    ibge_code = models.CharField(_("código IBGE"), max_length=7, unique=True)
    name = models.CharField(_("nome"), max_length=128)
    normalized_name = models.CharField(_("nome normalizado"), max_length=128, editable=False)
    centroid = models.PointField(_("centroide"), srid=4326, null=True, blank=True)

    class Meta:
        verbose_name = _("município")
        verbose_name_plural = _("municípios")
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ibge_code__regex=r"^\d{7}$"),
                name="city_ibge_code_7_digitos",
            ),
        ]
        indexes = [
            # Busca por nome na tela do Radar: sempre dentro de um estado ou não.
            models.Index(fields=["normalized_name"]),
            models.Index(fields=["state", "normalized_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name}/{self.state.uf}"

    def save(self, *args, **kwargs):
        # Derivado, nunca informado: manter no `save` garante que admin, importador e shell
        # produzam a mesma forma normalizada.
        self.normalized_name = normalize_name(self.name)

        # Quem grava com `update_fields` (o `update_or_create` do Django faz isso) listaria
        # só `name`, e o UPDATE deixaria `normalized_name` com o valor antigo — município
        # renomeado sumiria da busca. O campo derivado acompanha sua origem.
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "name" in update_fields:
            kwargs["update_fields"] = {*update_fields, "normalized_name"}

        super().save(*args, **kwargs)
