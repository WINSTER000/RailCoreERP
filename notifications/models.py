"""In-app notifications delivered to individual employees."""

from django.conf import settings
from django.db import models


class Notification(models.Model):
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    DANGER = "DANGER"

    LEVEL_CHOICES = [
        (INFO, "Information"),
        (SUCCESS, "Success"),
        (WARNING, "Warning"),
        (DANGER, "Critical"),
    ]

    #: level -> icon id from templates/partials/_icons.html
    LEVEL_ICONS = {
        INFO: "info",
        SUCCESS: "check",
        WARNING: "alert",
        DANGER: "ban",
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=140)
    message = models.TextField()
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default=INFO)
    url = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional in-app link opened when the notification is clicked.",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return self.title

    @property
    def icon(self):
        return self.LEVEL_ICONS.get(self.level, "bell")

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=["is_read"])
