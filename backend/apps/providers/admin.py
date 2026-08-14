from django.contrib import admin

from apps.providers.models import CompanySource, Provider, ProviderUsage


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_enabled", "retention_policy", "rate_limit_per_second"]
    list_filter = ["is_enabled", "retention_policy"]
    search_fields = ["slug", "name"]


@admin.register(ProviderUsage)
class ProviderUsageAdmin(admin.ModelAdmin):
    list_display = ["period", "provider", "organization", "request_count", "error_count"]
    list_filter = ["provider", "period"]
    # Consumo é registro de fato: editar à mão apagaria a evidência de custo.
    readonly_fields = ["provider", "organization", "period", "request_count", "error_count"]

    def has_add_permission(self, request) -> bool:
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("provider", "organization")


@admin.register(CompanySource)
class CompanySourceAdmin(admin.ModelAdmin):
    list_display = ["external_id", "provider", "company", "collected_at", "expires_at"]
    list_filter = ["provider"]
    search_fields = ["external_id", "company__name"]
    readonly_fields = ["raw_payload"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("provider", "company")
