"""CRUD screens for the railway domain.

Every module follows the same five-view shape: list, create, detail (where a
detail page adds value), update and delete. The shared conventions are:

* ``@require_view`` / ``@require_manage`` from ``accounts.permissions`` guard
  each view, so an unauthorised role gets HTTP 403 instead of a redirect.
* List pages accept ``?q=``, module specific filters, ``?sort=`` and ``?page=``.
  Sorting is whitelisted in ``*_SORT_FIELDS`` so a crafted value cannot order by
  an arbitrary column.
* Destructive actions render ``partials/_confirm_delete.html`` on GET and only
  act on POST.
* Every successful write records an ``ActivityLog`` entry, and the changes an
  operator needs to know about also raise a ``Notification``.
"""

from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Role
from accounts.permissions import can_manage, can_view, require_manage, require_view
from activity_logs.services import log_create, log_delete, log_update
from notifications.models import Notification
from notifications.services import notify_roles

from .forms import (
    PlatformForm,
    RouteForm,
    RouteStationForm,
    ScheduleForm,
    StationForm,
    TrainForm,
)
from .models import Platform, Route, RouteStation, Schedule, Station, Train
from .utils import apply_search, apply_sort, paginate

# ---------------------------------------------------------------------------
# List page configuration
# ---------------------------------------------------------------------------
TRAIN_SEARCH_FIELDS = ["train_number", "train_name", "route__route_name"]
TRAIN_SORT_FIELDS = ("train_number", "train_name", "route__route_name", "total_coaches", "status")

ROUTE_SEARCH_FIELDS = [
    "route_name",
    "source_station__name",
    "source_station__station_code",
    "destination_station__name",
    "destination_station__station_code",
]
ROUTE_SORT_FIELDS = ("route_name", "source_station__name", "destination_station__name", "total_distance")

SCHEDULE_SEARCH_FIELDS = [
    "train__train_number",
    "train__train_name",
    "platform__station__name",
    "platform__station__station_code",
]
SCHEDULE_SORT_FIELDS = ("departure_datetime", "arrival_datetime", "train__train_number", "delay_minutes")

STATION_SEARCH_FIELDS = ["name", "station_code", "city", "state"]
STATION_SORT_FIELDS = ("name", "station_code", "city", "state")

PLATFORM_SEARCH_FIELDS = ["station__name", "station__station_code", "station__city"]
PLATFORM_SORT_FIELDS = ("station__name", "platform_number")

ROUTE_STATION_SEARCH_FIELDS = [
    "route__route_name",
    "station__name",
    "station__station_code",
]
ROUTE_STATION_SORT_FIELDS = ("route__route_name", "sequence_number", "station__name", "arrival_offset")

#: ``?status=`` choices shared by the station, route and platform lists.
ACTIVE_STATUS_OPTIONS = [("active", "Active"), ("inactive", "Inactive")]

#: ``?status=`` choices for the schedule list (derived, not a stored column).
SCHEDULE_STATUS_OPTIONS = [
    ("upcoming", "Upcoming"),
    ("today", "Today"),
    ("delayed", "Delayed"),
    ("cancelled", "Cancelled"),
    ("completed", "Completed"),
]


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------
def _plural(count, word, plural=None):
    """``1 train`` / ``4 trains`` for the page subtitles."""
    if count == 1:
        return f"{count} {word}"
    return f"{count} {plural or word + 's'}"


def _clean_choice(value, options):
    """Keep a ``?filter=`` value only when it is one of *options*."""
    value = (value or "").strip()
    return value if value in {key for key, _ in options} else ""


def _clean_id(value):
    """Keep a ``?route=1`` style value only when it looks like a primary key."""
    value = (value or "").strip()
    return value if value.isdigit() else ""


def _filter_active(queryset, status_filter):
    """Apply an ``active`` / ``inactive`` filter to an ``is_active`` model."""
    if status_filter == "active":
        return queryset.filter(is_active=True)
    if status_filter == "inactive":
        return queryset.filter(is_active=False)
    return queryset


def _form_context(*, form, title, description, cancel_url, submit_label, page_title, page_subtitle, active_nav, is_edit):
    """Shared context for every ``*_form.html`` template."""
    return {
        "form": form,
        "form_title": title,
        "form_description": description,
        "cancel_url": cancel_url,
        "submit_label": submit_label,
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "active_nav": active_nav,
        "is_edit": is_edit,
    }


def _delete_context(*, object_type, object_label, object_meta, warning, cancel_url, confirm_label, page_title, page_subtitle, active_nav, soft_delete=False):
    """Shared context for ``partials/_confirm_delete.html``."""
    return {
        "object_type": object_type,
        "object_label": object_label,
        "object_meta": object_meta,
        "warning": warning,
        "soft_delete": soft_delete,
        "cancel_url": cancel_url,
        "confirm_label": confirm_label,
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "active_nav": active_nav,
    }


def _halt_return_url(user, route_pk):
    """Where to send an operator after editing a halt.

    The route detail page is the natural destination, but a Station Manager owns
    the halts without being able to open the routes module. Sending them to
    ``route_detail`` would land them on a 403, so they get the halt list scoped
    to that route instead.
    """
    if can_view(user, "routes"):
        return reverse("railway:route_detail", args=[route_pk])
    return f"{reverse('railway:route_station_list')}?route={route_pk}"


def _protected_message(instance, error):
    """A readable explanation for a delete blocked by ``on_delete=PROTECT``."""
    names = sorted({obj._meta.verbose_name_plural.lower() for obj in error.protected_objects})
    listed = " and ".join(names) if names else "other records"
    return f"{instance} cannot be deleted because it is still referenced by {listed}."


# ---------------------------------------------------------------------------
# Trains
# ---------------------------------------------------------------------------
@require_view("trains")
def train_list(request):
    """Every train in service, with search, status filter, sort and paging."""
    q = (request.GET.get("q") or "").strip()
    status_filter = _clean_choice(request.GET.get("status"), Train.STATUS_CHOICES)
    route_filter = _clean_id(request.GET.get("route"))

    trains = Train.objects.select_related("route", "route__source_station", "route__destination_station")
    trains = apply_search(trains, q, TRAIN_SEARCH_FIELDS)
    if status_filter:
        trains = trains.filter(status=status_filter)
    if route_filter:
        trains = trains.filter(route_id=int(route_filter))
    trains = apply_sort(trains, request.GET.get("sort"), TRAIN_SORT_FIELDS, "train_number")

    page_obj = paginate(request, trains)
    total_count = page_obj.paginator.count
    archived_count = Train.all_objects.deleted().count()

    context = {
        "trains": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "status_filter": status_filter,
        "route_filter": route_filter,
        "status_options": list(Train.STATUS_CHOICES),
        "route_options": Route.objects.filter(is_active=True).order_by("route_name"),
        "total_count": total_count,
        "archived_count": archived_count,
        "coach_total": trains.aggregate(total=Sum("total_coaches"))["total"] or 0,
        "page_title": "Trains",
        "page_subtitle": f"{_plural(total_count, 'train')} in the working fleet",
        "active_nav": "trains",
    }
    return render(request, "railway/train_list.html", context)


@require_manage("trains")
def train_create(request):
    """Register a new rake and tell the operations team it exists."""
    if request.method == "POST":
        form = TrainForm(request.POST)
        if form.is_valid():
            train = form.save()
            log_create(request.user, train, f"Added train {train.train_number} - {train.train_name}")
            notify_roles(
                [Role.RAILWAY_MANAGER, Role.OPERATIONS_STAFF],
                "New train added",
                f"{train.train_number} {train.train_name} was added on route {train.route.route_name}.",
                level=Notification.INFO,
                url=reverse("railway:train_detail", args=[train.pk]),
                exclude=request.user,
            )
            messages.success(request, f"Train {train.train_number} was added successfully.")
            return redirect("railway:train_detail", pk=train.pk)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = TrainForm()

    return render(
        request,
        "railway/train_form.html",
        _form_context(
            form=form,
            title="New train",
            description="Register the rake, assign its route and set its operating status.",
            cancel_url=reverse("railway:train_list"),
            submit_label="Create Train",
            page_title="Add Train",
            page_subtitle="Register a rake and assign it to a route",
            active_nav="trains",
            is_edit=False,
        ),
    )


@require_view("trains")
def train_detail(request, pk):
    """One train with its route, halts and upcoming runs."""
    train = get_object_or_404(
        Train.all_objects.select_related(
            "route", "route__source_station", "route__destination_station"
        ),
        pk=pk,
    )
    schedules = (
        Schedule.objects.select_related("platform", "platform__station")
        .filter(train=train)
        .order_by("-departure_datetime")[:10]
    )
    halts = (
        RouteStation.objects.select_related("station")
        .filter(route=train.route)
        .order_by("sequence_number")
    )

    context = {
        "train": train,
        "schedules": schedules,
        "halts": halts,
        "schedule_count": train.schedule_count,
        "upcoming_count": train.upcoming_schedule_count,
        "cancelled_count": Schedule.objects.filter(train=train, is_cancelled=True).count(),
        "page_title": f"{train.train_number} {train.train_name}",
        "page_subtitle": f"{train.route.route_name} · {train.route.corridor}",
        "active_nav": "trains",
    }
    return render(request, "railway/train_detail.html", context)


@require_manage("trains")
def train_update(request, pk):
    """Edit a train, warning operations when the status changes."""
    train = get_object_or_404(Train.all_objects.select_related("route"), pk=pk)
    previous_status = train.status

    if request.method == "POST":
        form = TrainForm(request.POST, instance=train)
        if form.is_valid():
            train = form.save()
            log_update(request.user, train, f"Updated train {train.train_number}")

            if train.status != previous_status:
                level = (
                    Notification.WARNING
                    if train.status != Train.ACTIVE
                    else Notification.SUCCESS
                )
                notify_roles(
                    [Role.RAILWAY_MANAGER, Role.OPERATIONS_STAFF],
                    f"Train {train.train_number} is now {train.get_status_display().lower()}",
                    f"{train.train_name} moved from {previous_status.lower()} to "
                    f"{train.status.lower()}.",
                    level=level,
                    url=reverse("railway:train_detail", args=[train.pk]),
                    exclude=request.user,
                )

            messages.success(request, f"Train {train.train_number} was updated successfully.")
            return redirect("railway:train_detail", pk=train.pk)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = TrainForm(instance=train)

    return render(
        request,
        "railway/train_form.html",
        _form_context(
            form=form,
            title=f"{train.train_number} {train.train_name}",
            description="Update the rake details, its route or its operating status.",
            cancel_url=reverse("railway:train_detail", args=[train.pk]),
            submit_label="Save Changes",
            page_title="Edit Train",
            page_subtitle=f"{train.train_number} · {train.train_name}",
            active_nav="trains",
            is_edit=True,
        ),
    )


@require_manage("trains")
def train_delete(request, pk):
    """Archive a train. Its schedules and history are kept."""
    train = get_object_or_404(Train.objects.select_related("route"), pk=pk)
    schedule_count = train.schedule_count
    upcoming_count = train.upcoming_schedule_count

    if request.method == "POST":
        train.soft_delete()
        log_delete(request.user, train, f"Archived train {train.train_number}")
        notify_roles(
            [Role.RAILWAY_MANAGER, Role.OPERATIONS_STAFF],
            f"Train {train.train_number} archived",
            f"{train.train_name} was withdrawn from the working fleet.",
            level=Notification.WARNING,
            url=reverse("railway:train_archive"),
            exclude=request.user,
        )
        messages.success(request, f"Train {train.train_number} was archived successfully.")
        return redirect("railway:train_list")

    warning = ""
    if upcoming_count:
        warning = (
            f"{_plural(upcoming_count, 'upcoming run')} already booked for this "
            f"train will stay in the schedule. Cancel them separately if the "
            f"service is not running."
        )

    return render(
        request,
        "partials/_confirm_delete.html",
        _delete_context(
            object_type="Train",
            object_label=f"{train.train_number} - {train.train_name}",
            object_meta=[
                ("Route", train.route.route_name),
                ("Coaches", train.total_coaches),
                ("Status", train.get_status_display()),
                ("Schedules recorded", schedule_count),
            ],
            warning=warning,
            cancel_url=reverse("railway:train_detail", args=[train.pk]),
            confirm_label="Yes, archive train",
            page_title="Archive Train",
            page_subtitle=f"{train.train_number} · {train.train_name}",
            active_nav="trains",
            soft_delete=True,
        ),
    )


@require_view("trains")
def train_archive(request):
    """The soft deleted trains, ready to be restored."""
    q = (request.GET.get("q") or "").strip()

    trains = Train.all_objects.deleted().select_related("route")
    trains = apply_search(trains, q, TRAIN_SEARCH_FIELDS)
    trains = apply_sort(trains, request.GET.get("sort"), TRAIN_SORT_FIELDS, "train_number")

    page_obj = paginate(request, trains)
    total_count = page_obj.paginator.count

    context = {
        "trains": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "total_count": total_count,
        "can_restore": can_manage(request.user, "trains"),
        "page_title": "Archived Trains",
        "page_subtitle": f"{_plural(total_count, 'archived train')} kept for auditing",
        "active_nav": "trains",
    }
    return render(request, "railway/train_archive.html", context)


@require_manage("trains")
@require_POST
def train_restore(request, pk):
    """Bring an archived train back into the working fleet."""
    train = get_object_or_404(Train.all_objects.select_related("route"), pk=pk)

    if train.is_deleted:
        train.restore()
        log_update(request.user, train, f"Restored train {train.train_number}")
        notify_roles(
            [Role.RAILWAY_MANAGER, Role.OPERATIONS_STAFF],
            f"Train {train.train_number} restored",
            f"{train.train_name} is back in the working fleet.",
            level=Notification.SUCCESS,
            url=reverse("railway:train_detail", args=[train.pk]),
            exclude=request.user,
        )
        messages.success(request, f"Train {train.train_number} was restored successfully.")
    else:
        messages.info(request, f"Train {train.train_number} is already in service.")

    return redirect("railway:train_detail", pk=train.pk)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@require_view("routes")
def route_list(request):
    """Every corridor, with its halt and train counts."""
    q = (request.GET.get("q") or "").strip()
    status_filter = _clean_choice(request.GET.get("status"), ACTIVE_STATUS_OPTIONS)

    routes = Route.objects.select_related("source_station", "destination_station")
    routes = apply_search(routes, q, ROUTE_SEARCH_FIELDS)
    routes = _filter_active(routes, status_filter)
    routes = routes.annotate(halts=Count("route_stations", distinct=True))
    routes = apply_sort(routes, request.GET.get("sort"), ROUTE_SORT_FIELDS, "route_name")

    page_obj = paginate(request, routes)
    total_count = page_obj.paginator.count

    context = {
        "routes": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "status_filter": status_filter,
        "status_options": ACTIVE_STATUS_OPTIONS,
        "total_count": total_count,
        "page_title": "Routes",
        "page_subtitle": f"{_plural(total_count, 'route')} across the network",
        "active_nav": "routes",
    }
    return render(request, "railway/route_list.html", context)


@require_manage("routes")
def route_create(request):
    """Open a new corridor between two stations."""
    if request.method == "POST":
        form = RouteForm(request.POST)
        if form.is_valid():
            route = form.save()
            log_create(request.user, route, f"Added route {route.route_name} ({route.corridor})")
            notify_roles(
                [Role.RAILWAY_MANAGER, Role.STATION_MANAGER],
                "New route added",
                f"{route.route_name} now connects {route.corridor} over "
                f"{route.total_distance} km.",
                level=Notification.INFO,
                url=reverse("railway:route_detail", args=[route.pk]),
                exclude=request.user,
            )
            messages.success(request, f"Route {route.route_name} was added successfully.")
            return redirect("railway:route_detail", pk=route.pk)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = RouteForm()

    return render(
        request,
        "railway/route_form.html",
        _form_context(
            form=form,
            title="New route",
            description="Name the corridor, pick its endpoints and record its length.",
            cancel_url=reverse("railway:route_list"),
            submit_label="Create Route",
            page_title="Add Route",
            page_subtitle="Define a corridor between two stations",
            active_nav="routes",
            is_edit=False,
        ),
    )


@require_view("routes")
def route_detail(request, pk):
    """One corridor with its ordered halts and the trains that work it."""
    route = get_object_or_404(
        Route.objects.select_related("source_station", "destination_station"), pk=pk
    )
    halts = (
        RouteStation.objects.select_related("station")
        .filter(route=route)
        .order_by("sequence_number")
    )
    trains = Train.objects.filter(route=route).order_by("train_number")

    context = {
        "route": route,
        "halts": halts,
        "trains": trains,
        "halt_count": halts.count(),
        "train_count": trains.count(),
        "add_halt_url": f"{reverse('railway:route_station_add')}?route={route.pk}",
        "page_title": route.route_name,
        "page_subtitle": f"{route.corridor} · {route.total_distance} km",
        "active_nav": "routes",
    }
    return render(request, "railway/route_detail.html", context)


@require_manage("routes")
def route_update(request, pk):
    """Edit a corridor's name, endpoints, length or service flag."""
    route = get_object_or_404(
        Route.objects.select_related("source_station", "destination_station"), pk=pk
    )

    if request.method == "POST":
        form = RouteForm(request.POST, instance=route)
        if form.is_valid():
            route = form.save()
            log_update(request.user, route, f"Updated route {route.route_name}")
            messages.success(request, f"Route {route.route_name} was updated successfully.")
            return redirect("railway:route_detail", pk=route.pk)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = RouteForm(instance=route)

    return render(
        request,
        "railway/route_form.html",
        _form_context(
            form=form,
            title=route.route_name,
            description="Update the corridor endpoints, its length or its service status.",
            cancel_url=reverse("railway:route_detail", args=[route.pk]),
            submit_label="Save Changes",
            page_title="Edit Route",
            page_subtitle=f"{route.route_name} · {route.corridor}",
            active_nav="routes",
            is_edit=True,
        ),
    )


@require_manage("routes")
def route_delete(request, pk):
    """Delete a corridor once no train depends on it."""
    route = get_object_or_404(
        Route.objects.select_related("source_station", "destination_station"), pk=pk
    )
    train_count = route.train_count
    halt_count = route.halt_count

    if request.method == "POST":
        label = route.route_name
        try:
            route.delete()
        except ProtectedError as error:
            messages.error(request, _protected_message(route, error))
            return redirect("railway:route_detail", pk=route.pk)

        log_delete(request.user, route, f"Deleted route {label}", object_id=pk)
        messages.success(request, f"Route {label} was deleted successfully.")
        return redirect("railway:route_list")

    warning = ""
    if train_count:
        warning = (
            f"{_plural(train_count, 'train')} still run on this route. Reassign or "
            f"archive them first: the delete will be refused while they exist."
        )
    elif halt_count:
        warning = (
            f"The {_plural(halt_count, 'halt')} defined on this route will be "
            f"removed with it."
        )

    return render(
        request,
        "partials/_confirm_delete.html",
        _delete_context(
            object_type="Route",
            object_label=route.route_name,
            object_meta=[
                ("Corridor", route.corridor),
                ("Distance", f"{route.total_distance} km"),
                ("Halts defined", halt_count),
                ("Trains assigned", train_count),
            ],
            warning=warning,
            cancel_url=reverse("railway:route_detail", args=[route.pk]),
            confirm_label="Yes, delete route",
            page_title="Delete Route",
            page_subtitle=f"{route.route_name} · {route.corridor}",
            active_nav="routes",
        ),
    )


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------
def _filter_schedules(queryset, status_filter):
    """Apply the derived status filter of the schedule list."""
    now = timezone.now()

    if status_filter == "upcoming":
        return queryset.filter(departure_datetime__gte=now, is_cancelled=False)
    if status_filter == "today":
        start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        return queryset.filter(
            departure_datetime__gte=start, departure_datetime__lt=start + timedelta(days=1)
        )
    if status_filter == "delayed":
        return queryset.filter(delay_minutes__gt=0, is_cancelled=False)
    if status_filter == "cancelled":
        return queryset.filter(is_cancelled=True)
    if status_filter == "completed":
        return queryset.filter(arrival_datetime__lt=now, is_cancelled=False)
    return queryset


@require_view("schedules")
def schedule_list(request):
    """Every dated run, filtered by derived status, train or platform."""
    q = (request.GET.get("q") or "").strip()
    status_filter = _clean_choice(request.GET.get("status"), SCHEDULE_STATUS_OPTIONS)
    train_filter = _clean_id(request.GET.get("train"))

    schedules = Schedule.objects.select_related(
        "train", "train__route", "platform", "platform__station"
    )
    schedules = apply_search(schedules, q, SCHEDULE_SEARCH_FIELDS)
    schedules = _filter_schedules(schedules, status_filter)
    if train_filter:
        schedules = schedules.filter(train_id=int(train_filter))
    schedules = apply_sort(
        schedules, request.GET.get("sort"), SCHEDULE_SORT_FIELDS, "-departure_datetime"
    )

    page_obj = paginate(request, schedules)
    total_count = page_obj.paginator.count

    context = {
        "schedules": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "status_filter": status_filter,
        "train_filter": train_filter,
        "status_options": SCHEDULE_STATUS_OPTIONS,
        "train_options": Train.objects.order_by("train_number"),
        "total_count": total_count,
        "delayed_count": schedules.filter(delay_minutes__gt=0, is_cancelled=False).count(),
        "cancelled_count": schedules.filter(is_cancelled=True).count(),
        "page_title": "Schedules",
        "page_subtitle": f"{_plural(total_count, 'run')} in this view",
        "active_nav": "schedules",
    }
    return render(request, "railway/schedule_list.html", context)


@require_manage("schedules")
def schedule_create(request):
    """Book a train onto a platform for one dated run."""
    if request.method == "POST":
        form = ScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save()
            log_create(
                request.user,
                schedule,
                f"Scheduled train {schedule.train.train_number} from "
                f"{schedule.platform} at {schedule.departure_datetime:%d %b %Y %H:%M}",
            )
            messages.success(
                request,
                f"Schedule for train {schedule.train.train_number} was added successfully.",
            )
            return redirect("railway:schedule_detail", pk=schedule.pk)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        initial = {}
        train_id = _clean_id(request.GET.get("train"))
        if train_id:
            initial["train"] = int(train_id)
        form = ScheduleForm(initial=initial)

    return render(
        request,
        "railway/schedule_form.html",
        _form_context(
            form=form,
            title="New schedule",
            description="Pick the train and platform, then set the departure and arrival.",
            cancel_url=reverse("railway:schedule_list"),
            submit_label="Create Schedule",
            page_title="Add Schedule",
            page_subtitle="Book a train onto a platform",
            active_nav="schedules",
            is_edit=False,
        ),
    )


@require_view("schedules")
def schedule_detail(request, pk):
    """One run with its timings, platform and the halts along the way."""
    schedule = get_object_or_404(
        Schedule.objects.select_related(
            "train",
            "train__route",
            "train__route__source_station",
            "train__route__destination_station",
            "platform",
            "platform__station",
        ),
        pk=pk,
    )
    halts = (
        RouteStation.objects.select_related("station")
        .filter(route=schedule.train.route)
        .order_by("sequence_number")
    )

    context = {
        "schedule": schedule,
        "train": schedule.train,
        "halts": halts,
        "page_title": f"Run · {schedule.train.train_number}",
        "page_subtitle": (
            f"{schedule.departure_datetime:%d %b %Y %H:%M} · {schedule.journey_label}"
        ),
        "active_nav": "schedules",
    }
    return render(request, "railway/schedule_detail.html", context)


@require_manage("schedules")
def schedule_update(request, pk):
    """Edit a run, notifying everyone when a delay is recorded."""
    schedule = get_object_or_404(
        Schedule.objects.select_related("train", "platform", "platform__station"), pk=pk
    )
    previous_delay = schedule.delay_minutes

    if request.method == "POST":
        form = ScheduleForm(request.POST, instance=schedule)
        if form.is_valid():
            schedule = form.save()
            log_update(
                request.user,
                schedule,
                f"Updated schedule for train {schedule.train.train_number}",
            )

            if schedule.delay_minutes and schedule.delay_minutes != previous_delay:
                notify_roles(
                    [Role.RAILWAY_MANAGER, Role.STATION_MANAGER, Role.OPERATIONS_STAFF],
                    f"Train {schedule.train.train_number} delayed "
                    f"{schedule.delay_minutes} minutes",
                    f"The run departing {schedule.departure_datetime:%d %b %H:%M} from "
                    f"{schedule.platform} is now expected at "
                    f"{schedule.expected_arrival:%d %b %H:%M}.",
                    level=Notification.WARNING,
                    url=reverse("railway:schedule_detail", args=[schedule.pk]),
                    exclude=request.user,
                )

            messages.success(request, "Schedule was updated successfully.")
            return redirect("railway:schedule_detail", pk=schedule.pk)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = ScheduleForm(instance=schedule)

    return render(
        request,
        "railway/schedule_form.html",
        _form_context(
            form=form,
            title=f"Run · {schedule.train.train_number}",
            description="Adjust the platform, the timings or the running delay.",
            cancel_url=reverse("railway:schedule_detail", args=[schedule.pk]),
            submit_label="Save Changes",
            page_title="Edit Schedule",
            page_subtitle=(
                f"{schedule.train.train_number} · "
                f"{schedule.departure_datetime:%d %b %Y %H:%M}"
            ),
            active_nav="schedules",
            is_edit=True,
        ),
    )


@require_manage("schedules")
@require_POST
def schedule_toggle_cancel(request, pk):
    """Cancel a run, or reinstate one that was cancelled by mistake."""
    schedule = get_object_or_404(
        Schedule.objects.select_related("train", "platform", "platform__station"), pk=pk
    )

    if schedule.is_cancelled:
        # Reinstating has to respect the platform double-booking rule, so run
        # the model's own validation before committing.
        schedule.is_cancelled = False
        try:
            schedule.full_clean()
        except ValidationError:
            messages.error(
                request,
                "This run cannot be reinstated: the platform is now occupied by "
                "another train for that period. Edit the schedule instead.",
            )
            return redirect("railway:schedule_detail", pk=schedule.pk)

        schedule.save(update_fields=["is_cancelled", "updated_at"])
        log_update(
            request.user,
            schedule,
            f"Reinstated schedule for train {schedule.train.train_number}",
        )
        notify_roles(
            [Role.RAILWAY_MANAGER, Role.STATION_MANAGER, Role.OPERATIONS_STAFF],
            f"Train {schedule.train.train_number} reinstated",
            f"The run departing {schedule.departure_datetime:%d %b %H:%M} from "
            f"{schedule.platform} is running again.",
            level=Notification.SUCCESS,
            url=reverse("railway:schedule_detail", args=[schedule.pk]),
            exclude=request.user,
        )
        messages.success(request, "Schedule was reinstated successfully.")
    else:
        schedule.is_cancelled = True
        schedule.save(update_fields=["is_cancelled", "updated_at"])
        log_update(
            request.user,
            schedule,
            f"Cancelled schedule for train {schedule.train.train_number}",
        )
        notify_roles(
            [Role.RAILWAY_MANAGER, Role.STATION_MANAGER, Role.OPERATIONS_STAFF],
            f"Train {schedule.train.train_number} cancelled",
            f"The run departing {schedule.departure_datetime:%d %b %H:%M} from "
            f"{schedule.platform} has been cancelled.",
            level=Notification.DANGER,
            url=reverse("railway:schedule_detail", args=[schedule.pk]),
            exclude=request.user,
        )
        messages.success(request, "Schedule was cancelled and the platform released.")

    return redirect("railway:schedule_detail", pk=schedule.pk)


@require_manage("schedules")
def schedule_delete(request, pk):
    """Remove a run from the timetable."""
    schedule = get_object_or_404(
        Schedule.objects.select_related("train", "platform", "platform__station"), pk=pk
    )

    if request.method == "POST":
        label = f"{schedule.train.train_number} at {schedule.departure_datetime:%d %b %Y %H:%M}"
        schedule.delete()
        log_delete(request.user, schedule, f"Deleted schedule for {label}", object_id=pk)
        messages.success(request, "Schedule was deleted successfully.")
        return redirect("railway:schedule_list")

    return render(
        request,
        "partials/_confirm_delete.html",
        _delete_context(
            object_type="Schedule",
            object_label=(
                f"{schedule.train.train_number} {schedule.train.train_name} · "
                f"{schedule.departure_datetime:%d %b %Y %H:%M}"
            ),
            object_meta=[
                ("Platform", str(schedule.platform)),
                ("Departure", f"{schedule.departure_datetime:%d %b %Y %H:%M}"),
                ("Arrival", f"{schedule.arrival_datetime:%d %b %Y %H:%M}"),
                ("Duration", schedule.duration_display),
                ("Delay", f"{schedule.delay_minutes} min"),
            ],
            warning=(
                "Cancelling the run keeps it on record for reporting. Delete it "
                "only when it was entered by mistake."
            ),
            cancel_url=reverse("railway:schedule_detail", args=[schedule.pk]),
            confirm_label="Yes, delete schedule",
            page_title="Delete Schedule",
            page_subtitle=(
                f"{schedule.train.train_number} · "
                f"{schedule.departure_datetime:%d %b %Y %H:%M}"
            ),
            active_nav="schedules",
        ),
    )


# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------
@require_view("stations")
def station_list(request):
    """Every station, with its platform count."""
    q = (request.GET.get("q") or "").strip()
    status_filter = _clean_choice(request.GET.get("status"), ACTIVE_STATUS_OPTIONS)
    state_filter = (request.GET.get("state") or "").strip()

    stations = Station.objects.all()
    stations = apply_search(stations, q, STATION_SEARCH_FIELDS)
    stations = _filter_active(stations, status_filter)

    states = list(
        Station.objects.order_by("state").values_list("state", flat=True).distinct()
    )
    if state_filter in states:
        stations = stations.filter(state=state_filter)
    else:
        state_filter = ""

    stations = stations.annotate(platforms_total=Count("platforms", distinct=True))
    stations = apply_sort(stations, request.GET.get("sort"), STATION_SORT_FIELDS, "name")

    page_obj = paginate(request, stations)
    total_count = page_obj.paginator.count

    context = {
        "stations": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "status_filter": status_filter,
        "state_filter": state_filter,
        "status_options": ACTIVE_STATUS_OPTIONS,
        "state_options": [(state, state) for state in states],
        "total_count": total_count,
        "page_title": "Stations",
        "page_subtitle": f"{_plural(total_count, 'station')} in this view",
        "active_nav": "stations",
    }
    return render(request, "railway/station_list.html", context)


@require_manage("stations")
def station_create(request):
    """Open a new station."""
    if request.method == "POST":
        form = StationForm(request.POST)
        if form.is_valid():
            station = form.save()
            log_create(
                request.user,
                station,
                f"Added station {station.station_code} - {station.name}",
            )
            notify_roles(
                [Role.STATION_MANAGER, Role.RAILWAY_MANAGER],
                "New station added",
                f"{station.name} ({station.station_code}) was added in {station.location}.",
                level=Notification.INFO,
                url=reverse("railway:station_detail", args=[station.pk]),
                exclude=request.user,
            )
            messages.success(request, f"Station {station.station_code} was added successfully.")
            return redirect("railway:station_detail", pk=station.pk)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = StationForm()

    return render(
        request,
        "railway/station_form.html",
        _form_context(
            form=form,
            title="New station",
            description="Record the station name, its official code and where it is.",
            cancel_url=reverse("railway:station_list"),
            submit_label="Create Station",
            page_title="Add Station",
            page_subtitle="Add a station to the network",
            active_nav="stations",
            is_edit=False,
        ),
    )


@require_view("stations")
def station_detail(request, pk):
    """One station with its platforms, routes and upcoming departures."""
    station = get_object_or_404(Station, pk=pk)
    platforms = Platform.objects.filter(station=station).order_by("platform_number")
    halts = (
        RouteStation.objects.select_related("route")
        .filter(station=station)
        .order_by("route__route_name", "sequence_number")
    )
    routes = Route.objects.filter(
        Q(source_station=station) | Q(destination_station=station)
    ).select_related("source_station", "destination_station").order_by("route_name")
    departures = (
        Schedule.objects.select_related("train", "platform")
        .filter(platform__station=station, departure_datetime__gte=timezone.now())
        .order_by("departure_datetime")[:8]
    )

    context = {
        "station": station,
        "platforms": platforms,
        "halts": halts,
        "routes": routes,
        "departures": departures,
        "platform_count": station.platform_count,
        "active_platform_count": station.active_platform_count,
        "add_platform_url": f"{reverse('railway:platform_add')}?station={station.pk}",
        "page_title": station.name,
        "page_subtitle": f"{station.station_code} · {station.location}",
        "active_nav": "stations",
    }
    return render(request, "railway/station_detail.html", context)


@require_manage("stations")
def station_update(request, pk):
    """Edit a station's details or retire it from service."""
    station = get_object_or_404(Station, pk=pk)

    if request.method == "POST":
        form = StationForm(request.POST, instance=station)
        if form.is_valid():
            station = form.save()
            log_update(request.user, station, f"Updated station {station.station_code}")
            messages.success(
                request, f"Station {station.station_code} was updated successfully."
            )
            return redirect("railway:station_detail", pk=station.pk)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = StationForm(instance=station)

    return render(
        request,
        "railway/station_form.html",
        _form_context(
            form=form,
            title=station.name,
            description="Update the station details or take it out of service.",
            cancel_url=reverse("railway:station_detail", args=[station.pk]),
            submit_label="Save Changes",
            page_title="Edit Station",
            page_subtitle=f"{station.station_code} · {station.location}",
            active_nav="stations",
            is_edit=True,
        ),
    )


@require_manage("stations")
def station_delete(request, pk):
    """Delete a station once no route or halt depends on it."""
    station = get_object_or_404(Station, pk=pk)
    platform_count = station.platform_count
    route_count = Route.objects.filter(
        Q(source_station=station) | Q(destination_station=station)
    ).count()
    halt_count = RouteStation.objects.filter(station=station).count()

    if request.method == "POST":
        label = f"{station.station_code} - {station.name}"
        try:
            station.delete()
        except ProtectedError as error:
            messages.error(request, _protected_message(station, error))
            return redirect("railway:station_detail", pk=station.pk)

        log_delete(request.user, station, f"Deleted station {label}", object_id=pk)
        messages.success(request, f"Station {station.station_code} was deleted successfully.")
        return redirect("railway:station_list")

    if route_count or halt_count:
        warning = (
            f"This station is used by {_plural(route_count, 'route')} and "
            f"{_plural(halt_count, 'route halt')}. The delete will be refused "
            f"until those references are removed. Deactivate the station instead "
            f"to retire it safely."
        )
    elif platform_count:
        warning = (
            f"The {_plural(platform_count, 'platform')} at this station will be "
            f"deleted with it."
        )
    else:
        warning = ""

    return render(
        request,
        "partials/_confirm_delete.html",
        _delete_context(
            object_type="Station",
            object_label=f"{station.station_code} - {station.name}",
            object_meta=[
                ("Location", station.location),
                ("Status", "Active" if station.is_active else "Inactive"),
                ("Platforms", platform_count),
                ("Routes referencing it", route_count),
                ("Route halts", halt_count),
            ],
            warning=warning,
            cancel_url=reverse("railway:station_detail", args=[station.pk]),
            confirm_label="Yes, delete station",
            page_title="Delete Station",
            page_subtitle=f"{station.station_code} · {station.location}",
            active_nav="stations",
        ),
    )


# ---------------------------------------------------------------------------
# Platforms
# ---------------------------------------------------------------------------
@require_view("platforms")
def platform_list(request):
    """Every platform on the network, grouped by station in the ordering."""
    q = (request.GET.get("q") or "").strip()
    status_filter = _clean_choice(request.GET.get("status"), ACTIVE_STATUS_OPTIONS)
    station_filter = _clean_id(request.GET.get("station"))

    platforms = Platform.objects.select_related("station")
    platforms = apply_search(platforms, q, PLATFORM_SEARCH_FIELDS)
    platforms = _filter_active(platforms, status_filter)
    if station_filter:
        platforms = platforms.filter(station_id=int(station_filter))
    platforms = platforms.annotate(schedules_total=Count("schedules", distinct=True))
    platforms = apply_sort(
        platforms, request.GET.get("sort"), PLATFORM_SORT_FIELDS, "station__name"
    )

    page_obj = paginate(request, platforms)
    total_count = page_obj.paginator.count

    context = {
        "platforms": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "status_filter": status_filter,
        "station_filter": station_filter,
        "status_options": ACTIVE_STATUS_OPTIONS,
        "station_options": Station.objects.order_by("name"),
        "total_count": total_count,
        "page_title": "Platforms",
        "page_subtitle": f"{_plural(total_count, 'platform')} in this view",
        "active_nav": "platforms",
    }
    return render(request, "railway/platform_list.html", context)


@require_manage("platforms")
def platform_create(request):
    """Add a numbered platform to a station."""
    if request.method == "POST":
        form = PlatformForm(request.POST)
        if form.is_valid():
            platform = form.save()
            log_create(
                request.user,
                platform,
                f"Added platform {platform.platform_number} at "
                f"{platform.station.station_code}",
            )
            messages.success(
                request,
                f"Platform {platform.platform_number} at "
                f"{platform.station.station_code} was added successfully.",
            )
            return redirect("railway:platform_list")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        initial = {}
        station_id = _clean_id(request.GET.get("station"))
        if station_id:
            initial["station"] = int(station_id)
        form = PlatformForm(initial=initial)

    return render(
        request,
        "railway/platform_form.html",
        _form_context(
            form=form,
            title="New platform",
            description="Pick the station and give the platform its number.",
            cancel_url=reverse("railway:platform_list"),
            submit_label="Create Platform",
            page_title="Add Platform",
            page_subtitle="Add a numbered platform to a station",
            active_nav="platforms",
            is_edit=False,
        ),
    )


@require_manage("platforms")
def platform_update(request, pk):
    """Edit a platform's number, station or availability."""
    platform = get_object_or_404(Platform.objects.select_related("station"), pk=pk)

    if request.method == "POST":
        form = PlatformForm(request.POST, instance=platform)
        if form.is_valid():
            platform = form.save()
            log_update(
                request.user,
                platform,
                f"Updated platform {platform.platform_number} at "
                f"{platform.station.station_code}",
            )
            messages.success(request, "Platform was updated successfully.")
            return redirect("railway:platform_list")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = PlatformForm(instance=platform)

    return render(
        request,
        "railway/platform_form.html",
        _form_context(
            form=form,
            title=str(platform),
            description="Move the platform, renumber it or close it for maintenance.",
            cancel_url=reverse("railway:platform_list"),
            submit_label="Save Changes",
            page_title="Edit Platform",
            page_subtitle=f"{platform.station.station_code} · {platform.label}",
            active_nav="platforms",
            is_edit=True,
        ),
    )


@require_manage("platforms")
def platform_delete(request, pk):
    """Delete a platform once no schedule uses it."""
    platform = get_object_or_404(Platform.objects.select_related("station"), pk=pk)
    schedule_count = platform.schedule_count

    if request.method == "POST":
        label = str(platform)
        try:
            platform.delete()
        except ProtectedError as error:
            messages.error(request, _protected_message(platform, error))
            return redirect("railway:platform_list")

        log_delete(request.user, platform, f"Deleted platform {label}", object_id=pk)
        messages.success(request, f"Platform {label} was deleted successfully.")
        return redirect("railway:platform_list")

    warning = ""
    if schedule_count:
        warning = (
            f"{_plural(schedule_count, 'schedule')} still reference this platform. "
            f"The delete will be refused until they are moved or removed. Close "
            f"the platform instead to take it out of use."
        )

    return render(
        request,
        "partials/_confirm_delete.html",
        _delete_context(
            object_type="Platform",
            object_label=str(platform),
            object_meta=[
                ("Station", f"{platform.station.station_code} - {platform.station.name}"),
                ("Platform number", platform.platform_number),
                ("Status", "Active" if platform.is_active else "Inactive"),
                ("Schedules using it", schedule_count),
            ],
            warning=warning,
            cancel_url=reverse("railway:platform_list"),
            confirm_label="Yes, delete platform",
            page_title="Delete Platform",
            page_subtitle=f"{platform.station.station_code} · {platform.label}",
            active_nav="platforms",
        ),
    )


# ---------------------------------------------------------------------------
# Route stations (ordered halts)
# ---------------------------------------------------------------------------
@require_view("route_stations")
def route_station_list(request):
    """Every halt across every route, in route and stop order."""
    q = (request.GET.get("q") or "").strip()
    route_filter = _clean_id(request.GET.get("route"))
    station_filter = _clean_id(request.GET.get("station"))

    halts = RouteStation.objects.select_related("route", "station")
    halts = apply_search(halts, q, ROUTE_STATION_SEARCH_FIELDS)
    if route_filter:
        halts = halts.filter(route_id=int(route_filter))
    if station_filter:
        halts = halts.filter(station_id=int(station_filter))
    halts = apply_sort(
        halts, request.GET.get("sort"), ROUTE_STATION_SORT_FIELDS, "route__route_name"
    )

    page_obj = paginate(request, halts)
    total_count = page_obj.paginator.count

    context = {
        "halts": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "route_filter": route_filter,
        "station_filter": station_filter,
        "route_options": Route.objects.order_by("route_name"),
        "station_options": Station.objects.order_by("name"),
        "total_count": total_count,
        "page_title": "Route Stations",
        "page_subtitle": f"{_plural(total_count, 'halt')} in this view",
        "active_nav": "route_stations",
    }
    return render(request, "railway/route_station_list.html", context)


@require_manage("route_stations")
def route_station_create(request):
    """Place one halt on a route."""
    if request.method == "POST":
        form = RouteStationForm(request.POST)
        if form.is_valid():
            halt = form.save()
            log_create(
                request.user,
                halt,
                f"Added halt {halt.station.station_code} as stop "
                f"{halt.sequence_number} on {halt.route.route_name}",
            )
            messages.success(
                request,
                f"{halt.station.station_code} was added to {halt.route.route_name} "
                f"as stop {halt.sequence_number}.",
            )
            return redirect(_halt_return_url(request.user, halt.route_id))
        messages.error(request, "Please correct the highlighted fields.")
    else:
        initial = {}
        route_id = _clean_id(request.GET.get("route"))
        if route_id:
            initial["route"] = int(route_id)
            # Suggest the next free stop number on that route.
            last = (
                RouteStation.objects.filter(route_id=int(route_id))
                .order_by("-sequence_number")
                .first()
            )
            initial["sequence_number"] = (last.sequence_number + 1) if last else 1
        form = RouteStationForm(initial=initial)

    return render(
        request,
        "railway/route_station_form.html",
        _form_context(
            form=form,
            title="New route halt",
            description=(
                "Choose the route and station, then time the halt in minutes from "
                "the origin departure."
            ),
            cancel_url=reverse("railway:route_station_list"),
            submit_label="Create Halt",
            page_title="Add Route Station",
            page_subtitle="Place a station on a route in running order",
            active_nav="route_stations",
            is_edit=False,
        ),
    )


@require_manage("route_stations")
def route_station_update(request, pk):
    """Edit one halt's position or timings."""
    halt = get_object_or_404(RouteStation.objects.select_related("route", "station"), pk=pk)

    if request.method == "POST":
        form = RouteStationForm(request.POST, instance=halt)
        if form.is_valid():
            halt = form.save()
            log_update(
                request.user,
                halt,
                f"Updated halt {halt.station.station_code} on {halt.route.route_name}",
            )
            messages.success(request, "Route halt was updated successfully.")
            return redirect(_halt_return_url(request.user, halt.route_id))
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = RouteStationForm(instance=halt)

    return render(
        request,
        "railway/route_station_form.html",
        _form_context(
            form=form,
            title=f"Stop {halt.sequence_number} · {halt.station.name}",
            description="Move the halt in the running order or retime it.",
            cancel_url=_halt_return_url(request.user, halt.route_id),
            submit_label="Save Changes",
            page_title="Edit Route Station",
            page_subtitle=f"{halt.route.route_name} · {halt.station.station_code}",
            active_nav="route_stations",
            is_edit=True,
        ),
    )


@require_manage("route_stations")
def route_station_delete(request, pk):
    """Remove one halt from a route."""
    halt = get_object_or_404(RouteStation.objects.select_related("route", "station"), pk=pk)

    if request.method == "POST":
        label = f"{halt.station.station_code} on {halt.route.route_name}"
        route_pk = halt.route_id
        halt.delete()
        log_delete(request.user, halt, f"Deleted halt {label}", object_id=pk)
        messages.success(request, f"Halt {label} was deleted successfully.")
        return redirect(_halt_return_url(request.user, route_pk))

    return render(
        request,
        "partials/_confirm_delete.html",
        _delete_context(
            object_type="Route halt",
            object_label=f"Stop {halt.sequence_number} · {halt.station.name}",
            object_meta=[
                ("Route", halt.route.route_name),
                ("Station", f"{halt.station.station_code} - {halt.station.name}"),
                ("Stop number", halt.sequence_number),
                ("Arrival offset", f"{halt.arrival_offset} min"),
                ("Departure offset", f"{halt.departure_offset} min"),
            ],
            warning=(
                "Removing a halt leaves a gap in the stop numbering. Renumber the "
                "remaining halts if the sequence must stay continuous."
            ),
            cancel_url=_halt_return_url(request.user, halt.route_id),
            confirm_label="Yes, delete halt",
            page_title="Delete Route Station",
            page_subtitle=f"{halt.route.route_name} · {halt.station.station_code}",
            active_nav="route_stations",
        ),
    )
