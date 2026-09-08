"""Helpers used by the views to write audit entries."""

from .models import ActivityLog


def log_activity(user, action, model_name="", object_id=None, description="", instance=None):
    """Create an :class:`ActivityLog` row.

    ``instance`` is a convenience shortcut: when given, ``model_name`` and
    ``object_id`` are derived from it.
    """
    if instance is not None:
        model_name = model_name or instance.__class__.__name__
        object_id = instance.pk if object_id is None else object_id
        description = description or str(instance)

    actor = user if (user is not None and getattr(user, "is_authenticated", False)) else None

    return ActivityLog.objects.create(
        user=actor,
        action=action,
        model_name=model_name or "",
        object_id="" if object_id in (None, "") else str(object_id),
        description=(description or "")[:255],
    )


def log_create(user, instance, description=""):
    return log_activity(
        user,
        ActivityLog.CREATE,
        instance=instance,
        description=description or f"Created {instance.__class__.__name__} {instance}",
    )


def log_update(user, instance, description=""):
    return log_activity(
        user,
        ActivityLog.UPDATE,
        instance=instance,
        description=description or f"Updated {instance.__class__.__name__} {instance}",
    )


def log_delete(user, instance, description="", object_id=None):
    """Record a DELETE action.

    Hard-deleted records lose their ``pk`` after ``.delete()`` runs, so views
    that physically remove a row pass ``object_id`` explicitly to keep the
    target of the audit entry. Soft-deleted records (trains, users) keep their
    ``pk`` and may omit it.
    """
    return log_activity(
        user,
        ActivityLog.DELETE,
        instance=instance,
        object_id=object_id,
        description=description or f"Deleted {instance.__class__.__name__} {instance}",
    )


def recent_activity(limit=8):
    """Most recent audit entries, ready for the dashboard panel."""
    return ActivityLog.objects.select_related("user")[:limit]
