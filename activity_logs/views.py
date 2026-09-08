"""Read-only audit trail screen (Admin and Railway Manager only)."""

from django.db.models import Count
from django.shortcuts import render

from accounts.models import User
from accounts.permissions import require_view
from railway.utils import apply_search, apply_sort, paginate

from .models import ActivityLog

#: Fields scanned by the ``?q=`` search box.
SEARCH_FIELDS = ["description", "model_name", "user__username", "user__first_name"]

#: Whitelisted ``?sort=`` targets, matching the sortable table headers.
SORT_FIELDS = {"created_at", "action", "model_name", "user__first_name"}


def _clean_action(value):
    """Keep the ``?action=`` value only when it is a real audit action."""
    action = (value or "").strip().upper()
    return action if action in dict(ActivityLog.ACTION_CHOICES) else ""


def _actor_options():
    """Only the employees who actually appear in the audit trail."""
    actor_ids = (
        ActivityLog.objects.exclude(user=None)
        .order_by()
        .values_list("user_id", flat=True)
        .distinct()
    )
    return User.objects.filter(pk__in=actor_ids).order_by("first_name", "last_name", "username")


def _action_summary(queryset, total_count):
    """Per-action counts and bar percentages for the filtered audit trail."""
    counts = {
        row["action"]: row["total"]
        for row in queryset.order_by().values("action").annotate(total=Count("id"))
    }

    summary = []
    for action, label in ActivityLog.ACTION_CHOICES:
        count = counts.get(action, 0)
        summary.append(
            {
                "action": action,
                "label": label,
                "count": count,
                "percent": round(count * 100 / total_count, 1) if total_count else 0,
                "icon": ActivityLog.ACTION_ICONS.get(action, "activity"),
            }
        )
    return summary


def _list_subtitle(total_count):
    """One-line summary shown under the page title."""
    if not total_count:
        return "No audit entries match the current view"
    noun = "entry" if total_count == 1 else "entries"
    return f"{total_count} audit {noun} in this view, newest first"


@require_view("activity_logs")
def activity_log_list(request):
    """Searchable, filterable history of every recorded action."""
    q = (request.GET.get("q") or "").strip()
    action_filter = _clean_action(request.GET.get("action"))
    user_filter = (request.GET.get("user") or "").strip()

    queryset = ActivityLog.objects.select_related("user")
    queryset = apply_search(queryset, q, SEARCH_FIELDS)

    if action_filter:
        queryset = queryset.filter(action=action_filter)
    if user_filter.isdigit():
        queryset = queryset.filter(user_id=int(user_filter))
    else:
        user_filter = ""

    total_count = queryset.count()
    action_summary = _action_summary(queryset, total_count)

    queryset = apply_sort(queryset, request.GET.get("sort"), SORT_FIELDS, "-created_at")
    page_obj = paginate(request, queryset)

    context = {
        "logs": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "action_filter": action_filter,
        "user_filter": user_filter,
        "action_options": list(ActivityLog.ACTION_CHOICES),
        "user_options": _actor_options(),
        "action_summary": action_summary,
        "total_count": total_count,
        "page_title": "Activity Logs",
        "page_subtitle": _list_subtitle(total_count),
        "active_nav": "activity_logs",
    }
    return render(request, "activity_logs/activity_log_list.html", context)
