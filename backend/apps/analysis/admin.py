from django.contrib import admin

from apps.analysis.models import WebsiteFinding, WebsiteScan

CAMPOS_DO_ACHADO = ("code", "severity", "detail")


class WebsiteFindingInline(admin.TabularInline):
    model = WebsiteFinding
    extra = 0
    # Achado é observação registrada: editar à mão falsearia o diagnóstico.
    fields = CAMPOS_DO_ACHADO
    readonly_fields = CAMPOS_DO_ACHADO
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(WebsiteScan)
class WebsiteScanAdmin(admin.ModelAdmin):
    list_display = ["company", "status", "http_status", "is_https", "has_viewport", "scanned_at"]
    list_filter = ["status", "is_https", "has_viewport", "has_booking", "has_whatsapp"]
    search_fields = ["company__name", "final_url", "title"]
    readonly_fields = ["signals", "scanned_at"]
    inlines = [WebsiteFindingInline]

    def has_add_permission(self, request) -> bool:
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("company")
