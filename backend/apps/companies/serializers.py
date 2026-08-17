from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.companies.models import (
    Category,
    Company,
    CompanyAddress,
    CompanyContact,
    CompanySocialProfile,
    CompanyWebsite,
)
from apps.companies.queries import OPPORTUNITY_OPEN


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "slug", "name", "parent"]


class OpportunityResumoSerializer(serializers.Serializer):
    """O mínimo da oportunidade para caber numa célula de tabela.

    Não é o serializer de `analysis` (não podemos importá-lo daqui): é a leitura de dois
    campos do objeto já carregado pelo prefetch.
    """

    code = serializers.CharField(source="type.code", read_only=True)
    name = serializers.CharField(source="type.name", read_only=True)


class CompanyTableSerializer(serializers.ModelSerializer):
    """Uma linha da tabela de empresas — plana de propósito.

    Cada campo é uma coluna que alguém usa para decidir se liga ou não. Aninhar contato dentro
    de objeto dentro de lista faria a tela desempacotar em três níveis para mostrar um
    telefone, que é o dado mais importante da tela.

    Os campos sem `source` vêm das anotações de `company_table_queryset`.
    """

    phone = serializers.CharField(read_only=True, default=None)
    whatsapp = serializers.CharField(read_only=True, default=None)
    email = serializers.CharField(read_only=True, default=None)
    city = serializers.CharField(source="city_name", read_only=True, default=None)
    uf = serializers.CharField(read_only=True, default=None)
    website = serializers.CharField(read_only=True, default=None)
    category = serializers.CharField(source="category_name", read_only=True, default=None)
    score = serializers.IntegerField(source="score_value", read_only=True, default=None)
    opportunities = serializers.SerializerMethodField()
    lead_id = serializers.UUIDField(read_only=True, default=None)
    lead_stage_code = serializers.CharField(read_only=True, default=None)
    lead_stage_name = serializers.CharField(read_only=True, default=None)

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "category",
            "city",
            "uf",
            "phone",
            "whatsapp",
            "email",
            "website",
            "website_status",
            "score",
            "opportunities",
            "lead_id",
            "lead_stage_code",
            "lead_stage_name",
            "rating",
            "review_count",
            "discovered_at",
        ]

    # O tipo do schema vem do decorador, e não de anotação de retorno: `.data` devolve
    # `ReturnList`, que o mypy recusa como `list[dict]`. Sem um dos dois o drf-spectacular
    # cai para `string` — e foi assim que a checagem de deploy da CI passou a falhar.
    @extend_schema_field(OpportunityResumoSerializer(many=True))
    def get_opportunities(self, obj):
        # Filtra em Python sobre o prefetch: consultar aqui seria N+1, e o corte por status
        # no banco exigiria a enum de `analysis`.
        abertas = [o for o in obj.opportunities.all() if o.status == OPPORTUNITY_OPEN]
        return OpportunityResumoSerializer(abertas, many=True).data


class CompanyContactSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = CompanyContact
        fields = [
            "id",
            "kind",
            "kind_label",
            "value_raw",
            "value_normalized",
            "is_primary",
            "verification_status",
            "last_verified_at",
        ]


class CompanyAddressSerializer(serializers.ModelSerializer):
    city_name = serializers.CharField(source="city.name", read_only=True)
    uf = serializers.CharField(source="city.state.uf", read_only=True)

    class Meta:
        model = CompanyAddress
        fields = [
            "id",
            "street",
            "number",
            "complement",
            "district",
            "postal_code",
            "city_name",
            "uf",
            "is_primary",
        ]


class CompanyWebsiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyWebsite
        fields = ["id", "url", "domain", "is_primary", "status", "last_checked_at"]


class CompanySocialProfileSerializer(serializers.ModelSerializer):
    network_label = serializers.CharField(source="get_network_display", read_only=True)

    class Meta:
        model = CompanySocialProfile
        fields = ["id", "network", "network_label", "url", "handle"]


class CompanyDetailSerializer(CompanyTableSerializer):
    """A ficha da empresa.

    Estende a linha da tabela em vez de repetir seus campos: o cabeçalho do detalhe mostra
    exatamente o que a tabela mostrava — telefone, cidade, score, situação no CRM —, e é o
    que evita o usuário sentir que mudou de assunto ao clicar.

    Score detalhado, oportunidades com evidência e diagnóstico do site continuam em
    `/analysis/…`, onde já estavam: duplicá-los aqui criaria dois contratos para o mesmo dado.
    """

    contacts = CompanyContactSerializer(many=True, read_only=True)
    addresses = CompanyAddressSerializer(many=True, read_only=True)
    websites = CompanyWebsiteSerializer(many=True, read_only=True)
    social_profiles = CompanySocialProfileSerializer(many=True, read_only=True)
    categories = CategorySerializer(many=True, read_only=True)

    class Meta(CompanyTableSerializer.Meta):
        fields = [
            *CompanyTableSerializer.Meta.fields,
            "legal_name",
            "trade_name",
            "tax_id",
            "description",
            "status",
            "last_seen_at",
            "contacts",
            "addresses",
            "websites",
            "social_profiles",
            "categories",
        ]
