"""Notification badge shown in the top header of every page."""

from .models import Notification


def notification_badge(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"unread_notification_count": 0, "header_notifications": []}

    unread = Notification.objects.filter(user=user, is_read=False)
    return {
        "unread_notification_count": unread.count(),
        "header_notifications": list(unread[:5]),
    }
