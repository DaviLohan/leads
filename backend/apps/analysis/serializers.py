from __future__ import annotations

from rest_framework import serializers

from apps.analysis.models import (
    Opportunity,
    Score,
    ScoreComponent,
    WebsiteFinding,
    WebsiteScan,
)


class WebsiteFindingSerializer(serializers.ModelSerializer):
    # `label` colidiria com `Field.label` do DRF, que é atributo da própria classe base.
    code_label = serializers.CharField(source="get_code_display", read_only=True)

    class Meta:
        model = WebsiteFinding
        fields = ["id", "code", "code_label", "severity", "detail", "evidence"]


class WebsiteScanSerializer(serializers.ModelSerializer):
    findings = WebsiteFindingSerializer(many=True, read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = WebsiteScan
        fields = [
            "id",
            "company",
            "company_name",
            "final_url",
            "status",
            "http_status",
            "is_https",
            "has_valid_cert",
            "response_time_ms",
            "redirect_count",
            "title",
            "meta_description",
            "has_viewport",
            "has_contact_form",
            "has_whatsapp",
            "has_booking",
            "has_cart",
            "error_detail",
            "scanned_at",
            "findings",
        ]


class OpportunitySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    type_code = serializers.CharField(source="type.code", read_only=True)
    type_name = serializers.CharField(source="type.name", read_only=True)
    type_description = serializers.CharField(source="type.description", read_only=True)

    class Meta:
        model = Opportunity
        fields = [
            "id",
            "company",
            "company_name",
            "type_code",
            "type_name",
            "type_description",
            "status",
            "confidence",
            "evidence",
            "detected_at",
            "resolved_at",
        ]


class ScoreComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScoreComponent
        fields = ["rule_code", "points", "reason"]


class ScoreSerializer(serializers.ModelSerializer):
    """O score sempre acompanhado do breakdown.

    Nunca só o número: um 0 a 100 solto não convence quem vai ligar para o cliente, e não dá
    para depurar quando estiver errado (ADR-0008).
    """

    company_name = serializers.CharField(source="company.name", read_only=True)
    components = ScoreComponentSerializer(many=True, read_only=True)

    class Meta:
        model = Score
        fields = ["id", "company", "company_name", "value", "version", "computed_at", "components"]
