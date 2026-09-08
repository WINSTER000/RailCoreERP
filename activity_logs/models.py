"""Audit trail for every important action performed in RailCore ERP."""

from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"

    ACTION_CHOICES = [
        (CREATE, "Create"),
        (UPDATE, "Update"),
        (DELETE, "Delete"),
        (LOGIN, "Login"),
        (LOGOUT, "Logout"),
    ]

    #: action -> icon id from templates/partials/_icons.html
    ACTION_ICONS = {
        CREATE: "plus",
        UPDATE: "edit",
        DELETE: "trash",
        LOGIN: "login",
        LOGOUT: "logout",
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=60, blank=True)
    object_id = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"

    def __str__(self):
        actor = self.user.display_name if self.user else "System"
        return f"{actor} · {self.action} · {self.model_name or '-'}"

    @property
    def actor_name(self):
        return self.user.display_name if self.user else "System"

    @property
    def actor_initials(self):
        return self.user.initials if self.user else "SY"

    @property
    def icon(self):
        return self.ACTION_ICONS.get(self.action, "activity")

    @property
    def target(self):
        if self.model_name and self.object_id:
            return f"{self.model_name} #{self.object_id}"
        return self.model_name or "-"
