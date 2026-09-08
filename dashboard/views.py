"""The operations dashboard.

Every figure on this page is computed from the database on each request. The
view stays deliberately query-light: six aggregate counts, one grouped count
per chart and two small slices for the activity feed and next departures.
"""

from datetime import timedelta

from django.db.models import Count, Sum
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.permissions import can_manage, can_view
from activity_logs.models import ActivityLog
from notifications.models import Notification
from railway.models import Platform, Route, RouteStation, Schedule, Station, Train

#: ActivityLog action -> (feed icon, feed tone)
FEED_STYLES = {
    ActivityLog.CREATE: ("plus", "success"),
    ActivityLog.UPDATE: ("edit", "info"),
    ActivityLog.DELETE: ("trash", "danger"),
    ActivityLog.LOGIN: ("login", "neutral"),
    ActivityLog.LOGOUT: ("logout", "neutral"),
}

#: Train status -> (label, chart/legend tone)
TRAIN_STATUS_STYLES = {
    Train.ACTIVE: ("Active", "success"),
    Train.MAINTENANCE: ("Maintenance", "warning"),
    Train.INACTIVE: ("Inactive", "neutral"),
}

#: Circumference of the donut ring drawn in dashboard.html (r = 68).
DONUT_CIRCUMFERENCE = 427.26


def _percent(value, total):
    """A rounded share of *total*, safe when *total* is zero."""
    if not total:
        return 0
    return round(value / total * 100, 1)


def _day_bounds(offset_days=0):
    """Local midnight boundaries for the day *offset_days* from today."""
    start = timezone.localtime(timezone.now()).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(days=offset_days)
    return start, start + timedelta(days=1)


def _stat_cards(user, today_start, today_end):
    """The six headline counters, in display order.

    ``url`` is blanked when *user* may not open the target list, so the card
    renders as plain text instead of a link that would 403.
    """
    active_stations = Station.objects.filter(is_active=True).count()
    total_stations = Station.objects.count()
    total_trains = Train.objects.count()
    active_trains = Train.objects.active().count()
    active_routes = Route.objects.filter(is_active=True).count()
    total_routes = Route.objects.count()
    today_schedules = Schedule.objects.filter(
        departure_datetime__gte=today_start, departure_datetime__lt=today_end
    ).count()
    cancelled_today = Schedule.objects.filter(
        departure_datetime__gte=today_start,
        departure_datetime__lt=today_end,
        is_cancelled=True,
    ).count()

    cards = [
        {
            "label": "Active Stations",
            "value": active_stations,
            "icon": "building",
            "tone": "primary",
            "meta": f"{total_stations} recorded in total",
            "url": reverse("railway:station_list"),
            "module": "stations",
        },
        {
            "label": "Total Trains",
            "value": total_trains,
            "icon": "train",
            "tone": "info",
            "meta": f"{Train.all_objects.deleted().count()} archived",
            "url": reverse("railway:train_list"),
            "module": "trains",
        },
        {
            "label": "Active Trains",
            "value": active_trains,
            "icon": "signal",
            "tone": "success",
            "meta": f"{_percent(active_trains, total_trains)}% of the fleet in service",
            "url": f"{reverse('railway:train_list')}?status={Train.ACTIVE}",
            "module": "trains",
        },
        {
            "label": "Active Routes",
            "value": active_routes,
            "icon": "route",
            "tone": "primary",
            "meta": f"{total_routes} defined in total",
            "url": reverse("railway:route_list"),
            "module": "routes",
        },
        {
            "label": "Today's Schedules",
            "value": today_schedules,
            "icon": "calendar",
            "tone": "info",
            "meta": "Departures dated today",
            "url": f"{reverse('railway:schedule_list')}?status=today",
            "module": "schedules",
        },
        {
            "label": "Cancelled Schedules",
            "value": cancelled_today,
            "icon": "calendar-x",
            "tone": "danger" if cancelled_today else "neutral",
            "meta": f"{_percent(cancelled_today, today_schedules)}% of today's runs",
            "url": f"{reverse('railway:schedule_list')}?status=cancelled",
            "module": "schedules",
        },
    ]

    for card in cards:
        if not can_view(user, card["module"]):
            card["url"] = ""
    return cards


def _week_chart():
    """Departures per day for the next seven days, as bar-chart rows."""
    rows = []
    peak = 0

    for offset in range(7):
        start, end = _day_bounds(offset)
        window = Schedule.objects.filter(
            departure_datetime__gte=start, departure_datetime__lt=end
        )
        total = window.count()
        cancelled = window.filter(is_cancelled=True).count()
        peak = max(peak, total)

        if offset == 0:
            label = "Today"
        elif offset == 1:
            label = "Tomorrow"
        else:
            label = f"{start:%a %d %b}"

        rows.append(
            {
                "label": label,
                "total": total,
                "cancelled": cancelled,
                "tone": "danger" if cancelled and cancelled == total else "primary",
            }
        )

    for row in rows:
        row["percent"] = _percent(row["total"], peak) if peak else 0

    return rows, peak


def _fleet_breakdown():
    """Train counts per status, plus the donut segments that draw them."""
    counts = {
        row["status"]: row["total"]
        for row in Train.objects.values("status").annotate(total=Count("id"))
    }
    total = sum(counts.values())

    segments = []
    offset = 0.0
    for status, (label, tone) in TRAIN_STATUS_STYLES.items():
        value = counts.get(status, 0)
        share = _percent(value, total)
        length = DONUT_CIRCUMFERENCE * (share / 100)
        segments.append(
            {
                "status": status,
                "label": label,
                "tone": tone,
                "value": value,
                "percent": share,
                "dash": f"{length:.2f} {DONUT_CIRCUMFERENCE - length:.2f}",
                "offset": f"{-offset:.2f}",
            }
        )
        offset += length

    return {
        "segments": segments,
        "total": total,
        "circumference": f"{DONUT_CIRCUMFERENCE:.2f}",
        "active_percent": _percent(counts.get(Train.ACTIVE, 0), total),
    }


def _busiest_routes(limit=5):
    """Routes ranked by the number of trains working them."""
    routes = list(
        Route.objects.select_related("source_station", "destination_station")
        .annotate(trains_total=Count("trains", distinct=True))
        .filter(trains_total__gt=0)
        .order_by("-trains_total", "route_name")[:limit]
    )
    peak = routes[0].trains_total if routes else 0
    return [
        {
            "route": route,
            "count": route.trains_total,
            "percent": _percent(route.trains_total, peak) if peak else 0,
        }
        for route in routes
    ]


def _punctuality(window_days=7):
    """On-time share of the runs departing in the last *window_days* days."""
    since = timezone.now() - timedelta(days=window_days)
    window = Schedule.objects.filter(departure_datetime__gte=since)

    total = window.count()
    cancelled = window.filter(is_cancelled=True).count()
    delayed = window.filter(is_cancelled=False, delay_minutes__gt=0).count()
    on_time = total - cancelled - delayed
    delay_total = (
        window.filter(is_cancelled=False).aggregate(total=Sum("delay_minutes"))["total"] or 0
    )

    return {
        "window_days": window_days,
        "total": total,
        "on_time": on_time,
        "delayed": delayed,
        "cancelled": cancelled,
        "on_time_percent": _percent(on_time, total),
        "delayed_percent": _percent(delayed, total),
        "cancelled_percent": _percent(cancelled, total),
        "average_delay": round(delay_total / delayed, 1) if delayed else 0,
        "tone": (
            "success"
            if _percent(on_time, total) >= 85
            else "warning"
            if _percent(on_time, total) >= 60
            else "danger"
        ),
    }


def _activity_feed(limit=8):
    """Recent audit entries decorated with their feed icon and tone."""
    feed = []
    for log in ActivityLog.objects.select_related("user")[:limit]:
        icon, tone = FEED_STYLES.get(log.action, ("activity", "neutral"))
        feed.append(
            {
                "log": log,
                "icon": icon,
                "tone": tone,
                "actor": log.user.get_full_name() if log.user else "System",
            }
        )
    return feed


def _system_status(today_start, today_end):
    """The live health rows shown in the System Status panel."""
    now = timezone.now()

    maintenance = Train.objects.maintenance().count()
    inactive_platforms = Platform.objects.filter(is_active=False).count()
    delayed_now = Schedule.objects.filter(
        is_cancelled=False,
        delay_minutes__gt=0,
        arrival_datetime__gte=now,
    ).count()
    cancelled_today = Schedule.objects.filter(
        departure_datetime__gte=today_start,
        departure_datetime__lt=today_end,
        is_cancelled=True,
    ).count()
    routes_without_halts = (
        Route.objects.annotate(halts=Count("route_stations")).filter(halts=0).count()
    )

    def row(label, value, state):
        return {"label": label, "value": value, "state": state}

    return [
        row("Database", "Connected", "ok"),
        row(
            "Rakes in maintenance",
            f"{maintenance} train{'' if maintenance == 1 else 's'}",
            "warn" if maintenance else "ok",
        ),
        row(
            "Platforms closed",
            f"{inactive_platforms} platform{'' if inactive_platforms == 1 else 's'}",
            "warn" if inactive_platforms else "ok",
        ),
        row(
            "Runs delayed now",
            f"{delayed_now} run{'' if delayed_now == 1 else 's'}",
            "warn" if delayed_now else "ok",
        ),
        row(
            "Cancellations today",
            f"{cancelled_today} run{'' if cancelled_today == 1 else 's'}",
            "down" if cancelled_today else "ok",
        ),
        row(
            "Routes without halts",
            f"{routes_without_halts} route{'' if routes_without_halts == 1 else 's'}",
            "warn" if routes_without_halts else "ok",
        ),
    ]


def _quick_actions(user):
    """Shortcut tiles, filtered to what this role may actually do."""
    candidates = [
        ("trains", "manage", "Add Train", "train", reverse("railway:train_add")),
        ("schedules", "manage", "Add Schedule", "calendar", reverse("railway:schedule_add")),
        ("routes", "manage", "Add Route", "route", reverse("railway:route_add")),
        ("stations", "manage", "Add Station", "building", reverse("railway:station_add")),
        ("platforms", "manage", "Add Platform", "layers", reverse("railway:platform_add")),
        (
            "route_stations",
            "manage",
            "Add Route Halt",
            "map-pin",
            reverse("railway:route_station_add"),
        ),
        ("users", "manage", "Add Employee", "users", reverse("accounts:user_add")),
        (
            "activity_logs",
            "view",
            "Activity Log",
            "history",
            reverse("activity_logs:list"),
        ),
    ]

    actions = []
    for module, capability, label, icon, url in candidates:
        allowed = can_manage(user, module) if capability == "manage" else can_view(user, module)
        if allowed:
            actions.append({"label": label, "icon": icon, "url": url})
    return actions


def dashboard(request):
    """The signed-in landing page. Reachable by every role."""
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(request.get_full_path())

    today_start, today_end = _day_bounds()
    now = timezone.now()

    week_rows, week_peak = _week_chart()

    next_departures = (
        Schedule.objects.select_related("train", "platform", "platform__station")
        .filter(departure_datetime__gte=now, is_cancelled=False)
        .order_by("departure_datetime")[:6]
    )

    context = {
        "stat_cards": _stat_cards(request.user, today_start, today_end),
        "week_rows": week_rows,
        "week_peak": week_peak,
        "week_total": sum(row["total"] for row in week_rows),
        "fleet": _fleet_breakdown(),
        "busiest_routes": _busiest_routes(),
        "punctuality": _punctuality(),
        "activity_feed": _activity_feed(),
        "system_status": _system_status(today_start, today_end),
        "quick_actions": _quick_actions(request.user),
        "next_departures": next_departures,
        "network": {
            "stations": Station.objects.count(),
            "platforms": Platform.objects.count(),
            "routes": Route.objects.count(),
            "halts": RouteStation.objects.count(),
            "trains": Train.objects.count(),
            "schedules": Schedule.objects.count(),
            "distance": Route.objects.filter(is_active=True).aggregate(
                total=Sum("total_distance")
            )["total"]
            or 0,
            "coaches": Train.objects.aggregate(total=Sum("total_coaches"))["total"] or 0,
            "employees": User.active_objects.filter(is_active=True).count(),
        },
        "unread_notifications": Notification.objects.filter(
            user=request.user, is_read=False
        ).count(),
        "page_title": "Dashboard",
        "page_subtitle": (
            f"Network overview for {timezone.localtime(now):%A, %d %B %Y}"
        ),
        "active_nav": "dashboard",
    }
    return render(request, "dashboard/dashboard.html", context)
