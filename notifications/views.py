"""Personal notification centre: list, mark as read and delete.

Every view here is scoped to ``request.user`` so one employee can never read or
change another employee's notifications.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.permissions import require_manage, require_view
from railway.utils import paginate

from .models import Notification

#: Accepted values of the ``?read=`` filter.
READ_FILTERS = ("unread", "read")


def _clean_level(value):
    """Keep the ``?level=`` value only when it is a real notification level."""
    level = (value or "").strip().upper()
    return level if level in dict(Notification.LEVEL_CHOICES) else ""


def _clean_read(value):
    """Keep the ``?read=`` value only when it is ``unread`` or ``read``."""
    state = (value or "").strip().lower()
    return state if state in READ_FILTERS else ""


def _list_subtitle(total_count, unread_total):
    """One-line summary shown under the page title."""
    if not total_count:
        return "No notifications match the current view"
    noun = "notification" if total_count == 1 else "notifications"
    if unread_total:
        return f"{total_count} {noun} in this view, {unread_total} still unread"
    return f"{total_count} {noun} in this view, all read"


def _redirect_target(url):
    """Where to send the user after reading a notification.

    ``Notification.url`` is always an in-app path produced by ``reverse()``, so
    only root-relative paths are accepted; anything else falls back to the list.
    """
    candidate = (url or "").strip()
    if candidate.startswith("/") and url_has_allowed_host_and_scheme(candidate, allowed_hosts=None):
        return candidate
    return reverse("notifications:list")


@require_view("notifications")
def notification_list(request):
    """Every notification raised for the signed in employee."""
    level_filter = _clean_level(request.GET.get("level"))
    read_filter = _clean_read(request.GET.get("read"))

    queryset = Notification.objects.filter(user=request.user)
    unread_total = queryset.filter(is_read=False).count()

    if level_filter:
        queryset = queryset.filter(level=level_filter)
    if read_filter:
        queryset = queryset.filter(is_read=read_filter == "read")

    queryset = queryset.order_by("-created_at", "-id")
    total_count = queryset.count()
    page_obj = paginate(request, queryset)

    context = {
        "notifications": page_obj.object_list,
        "page_obj": page_obj,
        "level_filter": level_filter,
        "read_filter": read_filter,
        "level_options": list(Notification.LEVEL_CHOICES),
        "total_count": total_count,
        "unread_total": unread_total,
        "page_title": "Notifications",
        "page_subtitle": _list_subtitle(total_count, unread_total),
        "active_nav": "notifications",
    }
    return render(request, "notifications/notification_list.html", context)


@require_manage("notifications")
@require_POST
def notification_mark_read(request, pk):
    """Mark one notification as read and open the record it points at."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.mark_read()
    return redirect(_redirect_target(notification.url))


@require_manage("notifications")
@require_POST
def notification_mark_all_read(request):
    """Clear the signed in employee's whole unread queue in one statement."""
    cleared = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)

    if cleared:
        noun = "notification" if cleared == 1 else "notifications"
        verb = "was" if cleared == 1 else "were"
        messages.success(request, f"{cleared} {noun} {verb} marked as read.")
    else:
        messages.info(request, "You have no unread notifications.")

    return redirect("notifications:list")


@require_manage("notifications")
@require_POST
def notification_delete(request, pk):
    """Remove one of the signed in employee's own notifications."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    title = notification.title
    notification.delete()
    messages.success(request, f"Notification '{title}' was deleted.")
    return redirect("notifications:list")
