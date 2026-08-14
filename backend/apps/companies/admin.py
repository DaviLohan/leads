"""Admin de empresas.

É por aqui que o modelo se inspeciona enquanto não existe frontend (Etapa 13). Os satélites
entram como inline: endereço e telefone soltos, sem a empresa ao lado, não dizem nada.
"""

from django.contrib import admin

from apps.companies.models import (
    Category,
    Company,
    CompanyAddress,
    CompanyCategory,
    CompanyContact,
    CompanySocialProfile,
    CompanyWebsite,
)


class CompanyAddressInline(admin.TabularInline):
    model = CompanyAddress
    extra = 0
    autocomplete_fields = ["city"]  # 5.571 municípios: select comum carregaria todos


class CompanyContactInline(admin.TabularInline):
    model = CompanyContact
    extra = 0


class CompanyWebsiteInline(admin.TabularInline):
    model = CompanyWebsite
    extra = 0


class CompanySocialProfileInline(admin.TabularInline):
    model = CompanySocialProfile
    extra = 0


class CompanyCategoryInline(admin.TabularInline):
    model = CompanyCategory
    extra = 0
    autocomplete_fields = ["category"]


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "tax_id", "status", "website_status", "discovered_at"]
    list_filter = ["status", "website_status"]
    search_fields = ["name", "normalized_name", "legal_name", "trade_name", "tax_id"]
    readonly_fields = ["normalized_name", "discovered_at"]
    ordering = ["name"]
    inlines = [
        CompanyAddressInline,
        CompanyContactInline,
        CompanyWebsiteInline,
        CompanySocialProfileInline,
        CompanyCategoryInline,
    ]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "parent", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}
    autocomplete_fields = ["parent"]
    ordering = ["name"]
