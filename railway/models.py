"""Core railway domain models: stations, platforms, routes, trains, schedules."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Adds bookkeeping timestamps to every railway record."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Station
# ---------------------------------------------------------------------------
class Station(TimeStampedModel):
    """A physical railway station."""

    name = models.CharField(max_length=120)
    station_code = models.CharField(
        max_length=10,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^[A-Z0-9]{2,10}$",
                message="Station code must be 2-10 characters using A-Z and 0-9 only.",
            )
        ],
        help_text="Official short code, for example NDLS or BCT.",
    )
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Station"
        verbose_name_plural = "Stations"

    def __str__(self):
        return f"{self.station_code} - {self.name}"

    def save(self, *args, **kwargs):
        if self.station_code:
            self.station_code = self.station_code.strip().upper()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("railway:station_detail", args=[self.pk])

    @property
    def location(self):
        return f"{self.city}, {self.state}"

    @property
    def platform_count(self):
        return self.platforms.count()

    @property
    def active_platform_count(self):
        return self.platforms.filter(is_active=True).count()

    @property
    def status_label(self):
        return "ACTIVE" if self.is_active else "INACTIVE"


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------
class Platform(TimeStampedModel):
    """A numbered platform belonging to a station."""

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="platforms")
    platform_number = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(99)],
        help_text="Platform number between 1 and 99.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["station__name", "platform_number"]
        verbose_name = "Platform"
        verbose_name_plural = "Platforms"
        constraints = [
            models.UniqueConstraint(
                fields=["station", "platform_number"],
                name="unique_platform_number_per_station",
                violation_error_message=(
                    "This platform number already exists for the selected station."
                ),
            )
        ]

    def __str__(self):
        return f"{self.station.station_code} - Platform {self.platform_number}"

    @property
    def label(self):
        return f"Platform {self.platform_number}"

    @property
    def status_label(self):
        return "ACTIVE" if self.is_active else "INACTIVE"

    @property
    def schedule_count(self):
        return self.schedules.count()


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
class Route(TimeStampedModel):
    """A named corridor between a source and a destination station."""

    route_name = models.CharField(max_length=120, unique=True)
    source_station = models.ForeignKey(
        Station, on_delete=models.PROTECT, related_name="routes_from"
    )
    destination_station = models.ForeignKey(
        Station, on_delete=models.PROTECT, related_name="routes_to"
    )
    total_distance = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Total route length in kilometres.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["route_name"]
        verbose_name = "Route"
        verbose_name_plural = "Routes"

    def __str__(self):
        return self.route_name

    def clean(self):
        super().clean()
        if (
            self.source_station_id
            and self.destination_station_id
            and self.source_station_id == self.destination_station_id
        ):
            raise ValidationError(
                {
                    "destination_station": "Destination station must be different "
                    "from the source station."
                }
            )

    def get_absolute_url(self):
        return reverse("railway:route_detail", args=[self.pk])

    @property
    def corridor(self):
        return f"{self.source_station.station_code} → {self.destination_station.station_code}"

    @property
    def halt_count(self):
        return self.route_stations.count()

    @property
    def train_count(self):
        return self.trains.count()

    @property
    def status_label(self):
        return "ACTIVE" if self.is_active else "INACTIVE"


# ---------------------------------------------------------------------------
# Route station (an ordered halt on a route)
# ---------------------------------------------------------------------------
class RouteStation(TimeStampedModel):
    """One ordered halt of a route, with offsets measured from the origin."""

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="route_stations")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="route_stations")
    sequence_number = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(200)],
        help_text="Position of this halt on the route, starting at 1.",
    )
    arrival_offset = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(10080)],
        help_text="Minutes after the origin departure when the train arrives here.",
    )
    departure_offset = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(10080)],
        help_text="Minutes after the origin departure when the train leaves here.",
    )

    class Meta:
        ordering = ["route__route_name", "sequence_number"]
        verbose_name = "Route Station"
        verbose_name_plural = "Route Stations"
        constraints = [
            models.UniqueConstraint(
                fields=["route", "sequence_number"],
                name="unique_sequence_number_per_route",
                violation_error_message=(
                    "This sequence number is already used on the selected route."
                ),
            ),
            models.UniqueConstraint(
                fields=["route", "station"],
                name="unique_station_per_route",
                violation_error_message=(
                    "This station is already part of the selected route."
                ),
            ),
        ]

    def __str__(self):
        return f"{self.route.route_name} · #{self.sequence_number} {self.station.station_code}"

    def clean(self):
        super().clean()
        if self.arrival_offset is not None and self.departure_offset is not None:
            if self.departure_offset < self.arrival_offset:
                raise ValidationError(
                    {
                        "departure_offset": "Departure offset cannot be earlier than "
                        "the arrival offset."
                    }
                )

    @property
    def halt_minutes(self):
        return max((self.departure_offset or 0) - (self.arrival_offset or 0), 0)


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------
class TrainQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=Train.ACTIVE)

    def maintenance(self):
        return self.filter(status=Train.MAINTENANCE)

    def deleted(self):
        return self.filter(is_deleted=True)


class TrainManager(models.Manager.from_queryset(TrainQuerySet)):
    """Default manager: soft deleted trains are never returned."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Train(TimeStampedModel):
    """Rolling stock assigned to a route."""

    ACTIVE = "ACTIVE"
    MAINTENANCE = "MAINTENANCE"
    INACTIVE = "INACTIVE"

    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (MAINTENANCE, "Maintenance"),
        (INACTIVE, "Inactive"),
    ]

    train_number = models.CharField(
        max_length=10,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^[0-9]{4,6}$",
                message="Train number must be 4 to 6 digits, for example 12951.",
            )
        ],
    )
    train_name = models.CharField(max_length=120)
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="trains")
    total_coaches = models.PositiveIntegerField(
        default=18,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Number of coaches in the rake (1-30).",
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=ACTIVE)
    is_deleted = models.BooleanField(default=False)

    objects = TrainManager()
    #: Includes soft deleted trains -- used by the archive screen and admin.
    all_objects = models.Manager.from_queryset(TrainQuerySet)()

    class Meta:
        ordering = ["train_number"]
        verbose_name = "Train"
        verbose_name_plural = "Trains"
        base_manager_name = "all_objects"
        default_manager_name = "objects"

    def __str__(self):
        return f"{self.train_number} - {self.train_name}"

    def get_absolute_url(self):
        return reverse("railway:train_detail", args=[self.pk])

    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"])

    def restore(self):
        self.is_deleted = False
        self.save(update_fields=["is_deleted", "updated_at"])

    @property
    def status_label(self):
        return self.status

    @property
    def schedule_count(self):
        return self.schedules.count()

    @property
    def upcoming_schedule_count(self):
        return self.schedules.filter(
            departure_datetime__gte=timezone.now(), is_cancelled=False
        ).count()


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------
class Schedule(TimeStampedModel):
    """A dated run of a train from a specific platform."""

    SCHEDULED = "SCHEDULED"
    DELAYED = "DELAYED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"

    train = models.ForeignKey(Train, on_delete=models.CASCADE, related_name="schedules")
    platform = models.ForeignKey(Platform, on_delete=models.PROTECT, related_name="schedules")
    departure_datetime = models.DateTimeField()
    arrival_datetime = models.DateTimeField()
    delay_minutes = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(1440)],
        help_text="Current running delay in minutes (0 when on time).",
    )
    is_cancelled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-departure_datetime"]
        verbose_name = "Schedule"
        verbose_name_plural = "Schedules"
        indexes = [
            models.Index(fields=["departure_datetime"], name="schedule_departure_idx"),
        ]

    def __str__(self):
        return f"{self.train.train_number} · {self.departure_datetime:%d %b %Y %H:%M}"

    def get_absolute_url(self):
        return reverse("railway:schedule_detail", args=[self.pk])

    def clean(self):
        super().clean()
        errors = {}

        if self.departure_datetime and self.arrival_datetime:
            if self.arrival_datetime <= self.departure_datetime:
                errors["arrival_datetime"] = (
                    "Arrival date and time must be later than the departure date and time."
                )

        if (
            not errors
            and not self.is_cancelled
            and self.platform_id
            and self.departure_datetime
            and self.arrival_datetime
        ):
            clash = Schedule.objects.filter(
                platform_id=self.platform_id,
                is_cancelled=False,
                departure_datetime__lt=self.arrival_datetime,
                arrival_datetime__gt=self.departure_datetime,
            )
            if self.pk:
                clash = clash.exclude(pk=self.pk)
            existing = clash.select_related("train").first()
            if existing is not None:
                errors["platform"] = (
                    f"This platform is already occupied by train "
                    f"{existing.train.train_number} between "
                    f"{existing.departure_datetime:%d %b %H:%M} and "
                    f"{existing.arrival_datetime:%d %b %H:%M}."
                )

        if errors:
            raise ValidationError(errors)

    # -- presentation helpers --------------------------------------------
    @property
    def display_status(self):
        if self.is_cancelled:
            return self.CANCELLED
        if self.delay_minutes:
            return self.DELAYED
        if self.arrival_datetime and self.arrival_datetime < timezone.now():
            return self.COMPLETED
        return self.SCHEDULED

    @property
    def expected_arrival(self):
        if not self.arrival_datetime:
            return None
        return self.arrival_datetime + timedelta(minutes=self.delay_minutes or 0)

    @property
    def duration_minutes(self):
        if not (self.arrival_datetime and self.departure_datetime):
            return 0
        return int((self.arrival_datetime - self.departure_datetime).total_seconds() // 60)

    @property
    def duration_display(self):
        minutes = self.duration_minutes
        return f"{minutes // 60}h {minutes % 60:02d}m"

    @property
    def journey_label(self):
        route = self.train.route
        return f"{route.source_station.station_code} → {route.destination_station.station_code}"
