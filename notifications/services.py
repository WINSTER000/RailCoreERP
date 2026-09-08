"""Fan-out helpers used by the railway views to raise notifications."""

from django.contrib.auth import get_user_model

from .models import Notification


def notify_users(users, title, message, level=Notification.INFO, url=""):
    """Create one notification per user in *users*. Returns the number created."""
    recipients = [u for u in users if u is not None and u.pk]
    if not recipients:
        return 0
    Notification.objects.bulk_create(
        [
            Notification(
                user=user,
                title=title[:140],
                message=message,
                level=level,
                url=url,
            )
            for user in recipients
        ]
    )
    return len(recipients)


def notify_roles(role_names, title, message, level=Notification.INFO, url="", exclude=None):
    """Notify every active employee holding one of *role_names*.

    Administrators always receive these notifications as well.
    """
    User = get_user_model()
    names = set(role_names or [])
    names.add("Admin")
    queryset = User.active_objects.filter(is_active=True, role__name__in=names)
    if exclude is not None and exclude.pk:
        queryset = queryset.exclude(pk=exclude.pk)
    return notify_users(list(queryset), title, message, level=level, url=url)


def notify_all(title, message, level=Notification.INFO, url="", exclude=None):
    """Notify every active employee."""
    User = get_user_model()
    queryset = User.active_objects.filter(is_active=True)
    if exclude is not None and exclude.pk:
        queryset = queryset.exclude(pk=exclude.pk)
    return notify_users(list(queryset), title, message, level=level, url=url)


def unread_count(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return Notification.objects.filter(user=user, is_read=False).count()
