from __future__ import annotations

from rest_framework import serializers

from apps.discovery.models import Search, SearchJob, SearchResult


class SearchJobSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True)
    uf = serializers.CharField(source="city.state.uf", read_only=True)
    category = serializers.CharField(source="category.name", read_only=True)
    provider = serializers.CharField(source="provider.slug", read_only=True)

    class Meta:
        model = SearchJob
        fields = [
            "id",
            "city",
            "uf",
            "category",
            "provider",
            "status",
            "found_count",
            "new_count",
            "duplicate_count",
            "review_count",
            "error_count",
            "attempts",
            "last_error",
            "started_at",
            "finished_at",
        ]


class SearchSerializer(serializers.ModelSerializer):
    progress = serializers.IntegerField(read_only=True)
    # Ambos vêm de anotação na listagem (ver SearchViewSet.get_queryset).
    job_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Search
        fields = [
            "id",
            "name",
            "criteria",
            "status",
            "progress",
            "job_count",
            "created_at",
            "started_at",
            "finished_at",
        ]
        # A organização nunca vem do payload (CLAUDE.md): quem a define é o `TenantViewSet`,
        # a partir da sessão. `status` é derivado dos jobs, não informado.
        read_only_fields = ["status", "started_at", "finished_at"]


class CriteriaSerializer(serializers.Serializer):
    """Valida os critérios antes de virar trabalho.

    Existe separado do `SearchSerializer` porque `criteria` é `JSONField`: sem isto, um
    payload torto só falharia no planejamento, depois de a busca já existir no banco.
    """

    uf = serializers.ListField(child=serializers.CharField(max_length=2), required=False)
    city_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    category_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    provider_slugs = serializers.ListField(
        child=serializers.SlugField(max_length=50), allow_empty=False
    )

    def validate(self, attrs):
        if not attrs.get("uf") and not attrs.get("city_ids"):
            raise serializers.ValidationError(
                "Informe ao menos um estado (`uf`) ou município (`city_ids`)."
            )

        # `UUIDField` devolve objetos `UUID`, e o destino é um `JSONField` — o Postgres não
        # os serializa. Converter aqui, na fronteira, é o que mantém `criteria` sempre
        # legível como JSON puro, inclusive para quem for ler a busca meses depois.
        attrs["uf"] = [uf.upper() for uf in attrs.get("uf", [])]
        attrs["city_ids"] = [str(i) for i in attrs.get("city_ids", [])]
        attrs["category_ids"] = [str(i) for i in attrs["category_ids"]]
        return attrs


class SearchResultSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True, default=None)

    class Meta:
        model = SearchResult
        fields = [
            "id",
            "external_id",
            "match_type",
            "matched_score",
            "company",
            "company_name",
            "normalized_payload",
        ]
