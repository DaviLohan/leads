"""API de procedência.

Existe para uma pergunta só, feita na ficha da empresa: **de onde veio este dado, e quando?**
Sem resposta, o diagnóstico é uma afirmação sem lastro — e este produto se sustenta em não
afirmar o que não sabe.

Só leitura, e sem o `raw_payload`: o bruto da fonte serve para depurar ingestão, não para a
tela, e devolvê-lo por padrão jogaria quilobytes de JSON no navegador a cada abertura de
empresa.
"""

from __future__ import annotations

from rest_framework import serializers, viewsets

from apps.providers.models import CompanySource


class CompanySourceSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.name", read_only=True)
    provider_slug = serializers.CharField(source="provider.slug", read_only=True)

    class Meta:
        model = CompanySource
        fields = [
            "id",
            "company",
            "provider_name",
            "provider_slug",
            "external_id",
            "collected_at",
            "confidence",
        ]


class CompanySourceViewSet(viewsets.ReadOnlyModelViewSet):
    """Procedência das empresas. Global (ADR-0007): de onde veio o dado é o mesmo para todos."""

    serializer_class = CompanySourceSerializer
    filterset_fields = ["company", "provider__slug"]

    def get_queryset(self):
        return CompanySource.objects.select_related("provider").order_by("-collected_at")
