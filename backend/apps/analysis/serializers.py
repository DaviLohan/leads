from __future__ import annotations

from rest_framework import serializers

from apps.analysis.models import WebsiteFinding, WebsiteScan


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
