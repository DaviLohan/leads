from django.contrib import admin

from apps.crm.models import (
    Interaction,
    Lead,
    Note,
    Pipeline,
    PipelineStage,
    SuppressionEntry,
    Task,
)

CAMPOS_DA_INTERACAO = ("occurred_at", "kind", "description", "outcome", "author")


class PipelineStageInline(admin.TabularInline):
    model = PipelineStage
    extra = 0


class InteractionInline(admin.TabularInline):
    model = Interaction
    extra = 0
    # Append-only: o histórico não se reescreve, nem pelo admin.
    fields = CAMPOS_DA_INTERACAO
    readonly_fields = CAMPOS_DA_INTERACAO
    can_delete = False
    ordering = ["-occurred_at"]

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "is_default"]
    list_filter = ["organization", "is_default"]
    inlines = [PipelineStageInline]


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = [
        "company",
        "organization",
        "stage",
        "owner",
        "score_snapshot",
        "last_contacted_at",
    ]
    list_filter = ["organization", "stage"]
    search_fields = ["company__name"]
    readonly_fields = ["score_snapshot"]
    inlines = [InteractionInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("company", "organization", "stage", "owner")
        )


@admin.register(SuppressionEntry)
class SuppressionEntryAdmin(admin.ModelAdmin):
    list_display = ["identifier_kind", "identifier_value", "organization", "reason", "created_at"]
    list_filter = ["organization", "identifier_kind"]
    search_fields = ["identifier_value"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "lead", "assignee", "due_at", "status"]
    list_filter = ["status"]


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ["lead", "author", "created_at"]
    search_fields = ["body"]
