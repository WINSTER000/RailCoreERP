from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "model_name", "object_id", "description")
    list_filter = ("action", "model_name", "created_at")
    search_fields = ("description", "model_name", "object_id", "user__username")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    readonly_fields = ("user", "action", "model_name", "object_id", "description", "created_at")

    def has_add_permission(self, request):
        # Audit rows are written by the application, never by hand.
        return False
