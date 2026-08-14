from django.contrib import admin

from apps.discovery.models import Search, SearchJob, SearchResult

# Job é registro de execução: editar à mão mentiria sobre o que a fonte devolveu, então a
# mesma sequência serve de `fields` e de `readonly_fields`.
#
# Tupla, e não lista: os dois atributos são declarados com tipos diferentes nos stubs do
# Django, e só a tupla satisfaz ambos — lista é invariante em mypy, tupla é covariante.
CAMPOS_DO_JOB = (
    "city",
    "category",
    "provider",
    "status",
    "found_count",
    "new_count",
    "last_error",
)


class SearchJobInline(admin.TabularInline):
    model = SearchJob
    extra = 0
    can_delete = False
    fields = CAMPOS_DO_JOB
    readonly_fields = CAMPOS_DO_JOB

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Search)
class SearchAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "status", "progress", "created_at"]
    list_filter = ["status", "organization"]
    search_fields = ["name"]
    readonly_fields = ["status", "started_at", "finished_at"]
    inlines = [SearchJobInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("organization")


@admin.register(SearchResult)
class SearchResultAdmin(admin.ModelAdmin):
    list_display = ["external_id", "match_type", "company", "matched_score"]
    list_filter = ["match_type"]
    search_fields = ["external_id", "company__name"]
    readonly_fields = ["normalized_payload"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("company", "search_job")
