from django.contrib import admin

from apps.geography.models import City, State


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ["uf", "name", "region", "ibge_code"]
    list_filter = ["region"]
    search_fields = ["uf", "name", "ibge_code"]
    ordering = ["name"]


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ["name", "state", "ibge_code"]
    list_filter = ["state__region", "state"]
    search_fields = ["name", "normalized_name", "ibge_code"]
    # 5.570 linhas: o select comum do formulário carregaria todas em cada abertura.
    autocomplete_fields = ["state"]
    ordering = ["name"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("state")
