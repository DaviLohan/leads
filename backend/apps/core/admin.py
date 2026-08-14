from django.contrib import admin

from apps.core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Somente leitura: a trilha de auditoria é append-only (SECURITY.md)."""

    list_display = ["created_at", "action", "object_type", "object_id", "actor"]
    list_filter = ["action", "object_type"]
    search_fields = ["object_id", "request_id"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
