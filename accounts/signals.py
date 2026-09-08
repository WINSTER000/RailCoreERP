"""Authentication signal receivers that feed the activity log."""

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from activity_logs.models import ActivityLog
from activity_logs.services import log_activity


@receiver(user_logged_in)
def record_login(sender, request, user, **kwargs):
    log_activity(
        user=user,
        action=ActivityLog.LOGIN,
        model_name="User",
        object_id=user.pk,
        description=f"{user.display_name} signed in to RailCore ERP.",
    )


@receiver(user_logged_out)
def record_logout(sender, request, user, **kwargs):
    if user is None:
        return
    log_activity(
        user=user,
        action=ActivityLog.LOGOUT,
        model_name="User",
        object_id=user.pk,
        description=f"{user.display_name} signed out of RailCore ERP.",
    )
