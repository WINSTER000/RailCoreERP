"""Data entry forms for the railway domain.

Each form is a plain ``ModelForm`` that lists its fields explicitly and attaches
the RailCore control classes (``rc-input``, ``rc-select`` ...) so that
``{% rc_field %}`` renders it without any per-template styling.

Validation policy: whenever ``models.py`` already checks a rule inside
``Model.clean()`` -- source vs destination station, offset ordering, arrival vs
departure, platform double-booking -- the model stays the single source of
truth. Django surfaces those messages on the right field automatically during
``_post_clean()``. The forms below only add the checks the model cannot express
that way, and they always report them as *field* errors so that a duplicate row
never reaches the database as an ``IntegrityError``.
"""

import re

from django import forms
from django.db.models import Q
from django.forms.models import ModelChoiceIterator

from .models import Platform, Route, RouteStation, Schedule, Station, Train

#: Value format produced and consumed by ``<input type="datetime-local">``.
DATETIME_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"

#: The browser format first, then the usual Django ones, so that a schedule
#: saved from the picker and one typed by hand both parse.
DATETIME_INPUT_FORMATS = [
    DATETIME_LOCAL_FORMAT,
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
]

TRAIN_NUMBER_RE = re.compile(r"^[0-9]{4,6}$")


def active_with_current(queryset, current_id):
    """Active rows only, plus the row already selected on the record being edited.

    Without the second half, opening an old record whose station or route has
    since been deactivated would silently drop the saved value from the select.
    """
    condition = Q(is_active=True)
    if current_id:
        condition |= Q(pk=current_id)
    return queryset.filter(condition)


class StationChoiceField(forms.ModelChoiceField):
    """Station select showing ``NDLS - New Delhi``."""

    def label_from_instance(self, obj):
        return f"{obj.station_code} - {obj.name}"


class RouteChoiceField(forms.ModelChoiceField):
    """Route select showing ``Delhi-Mumbai Mail (NDLS -> BCT)``."""

    def label_from_instance(self, obj):
        return f"{obj.route_name} ({obj.corridor})"


class TrainChoiceField(forms.ModelChoiceField):
    """Train select showing ``12951 - Mumbai Rajdhani``."""

    def label_from_instance(self, obj):
        return f"{obj.train_number} - {obj.train_name}"


class PlatformChoiceIterator(ModelChoiceIterator):
    """Yields platform options wrapped in one ``<optgroup>`` per station.

    A busy junction has a dozen platforms, so a flat list is hard to scan.
    The queryset must be ordered by station for the grouping to be correct.
    """

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)

        group_label = None
        group = []
        for platform in self.queryset:
            label = f"{platform.station.station_code} - {platform.station.name}"
            if group and label != group_label:
                yield (group_label, group)
                group = []
            group_label = label
            group.append(self.choice(platform))

        if group:
            yield (group_label, group)


class PlatformChoiceField(forms.ModelChoiceField):
    """Platform select grouped by station, each option ``NDLS - Platform 3``."""

    iterator = PlatformChoiceIterator

    def label_from_instance(self, obj):
        return f"{obj.station.station_code} - Platform {obj.platform_number}"


# ---------------------------------------------------------------------------
# Station
# ---------------------------------------------------------------------------
class StationForm(forms.ModelForm):
    """Create or edit a station."""

    class Meta:
        model = Station
        fields = ["name", "station_code", "city", "state", "is_active"]
        labels = {
            "name": "Station name",
            "station_code": "Station code",
            "city": "City",
            "state": "State",
            "is_active": "Station is open for operations",
        }
        help_texts = {
            "name": "Full name as printed on the timetable.",
            "station_code": (
                "2-10 uppercase letters or digits, for example NDLS. "
                "Lower case is converted automatically."
            ),
            "is_active": (
                "Turn this off to retire the station. Existing routes and "
                "platforms are kept, but the station stops appearing in new "
                "route and platform forms."
            ),
        }
        error_messages = {
            "station_code": {
                "unique": (
                    "Another station already uses this code. Station codes must "
                    "be unique across the network."
                ),
            },
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "rc-input",
                    "placeholder": "New Delhi",
                    "autofocus": True,
                    "autocomplete": "off",
                }
            ),
            "station_code": forms.TextInput(
                attrs={
                    "class": "rc-input",
                    "placeholder": "NDLS",
                    "autocapitalize": "characters",
                    "autocomplete": "off",
                    "spellcheck": "false",
                }
            ),
            "city": forms.TextInput(
                attrs={"class": "rc-input", "placeholder": "Delhi", "autocomplete": "off"}
            ),
            "state": forms.TextInput(
                attrs={"class": "rc-input", "placeholder": "Delhi", "autocomplete": "off"}
            ),
        }

    def clean_station_code(self):
        """Normalise to upper case so the model's A-Z/0-9 rule can pass."""
        code = (self.cleaned_data.get("station_code") or "").strip().upper()
        if " " in code:
            raise forms.ValidationError("Station code cannot contain spaces.")
        return code


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------
class PlatformForm(forms.ModelForm):
    """Add a numbered platform to a station."""

    station = StationChoiceField(
        queryset=Station.objects.none(),
        label="Station",
        empty_label="Select a station",
        help_text="Only stations that are currently open are listed.",
        widget=forms.Select(attrs={"class": "rc-select", "autofocus": True}),
    )

    class Meta:
        model = Platform
        fields = ["station", "platform_number", "is_active"]
        labels = {
            "platform_number": "Platform number",
            "is_active": "Platform is available for boarding",
        }
        help_texts = {
            "platform_number": "Any number from 1 to 99, unique within the station.",
            "is_active": (
                "Turn this off while the platform is closed for maintenance. "
                "Closed platforms cannot be picked for new schedules."
            ),
        }
        widgets = {
            "platform_number": forms.NumberInput(
                attrs={"class": "rc-input", "min": 1, "max": 99, "step": 1, "placeholder": "1"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["station"].queryset = active_with_current(
            Station.objects.all(), self.instance.station_id
        ).order_by("name")

    def clean(self):
        """Report a duplicate platform number on the field, not as a 500."""
        cleaned_data = super().clean()
        station = cleaned_data.get("station")
        number = cleaned_data.get("platform_number")

        if station and number:
            clash = Platform.objects.filter(station=station, platform_number=number)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error(
                    "platform_number",
                    f"{station.station_code} already has a platform {number}. "
                    f"Choose a different number.",
                )

        return cleaned_data


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
class RouteForm(forms.ModelForm):
    """Define a corridor between two stations."""

    source_station = StationChoiceField(
        queryset=Station.objects.none(),
        label="Source station",
        empty_label="Select the origin",
        help_text="Where the run begins.",
        widget=forms.Select(attrs={"class": "rc-select"}),
    )
    destination_station = StationChoiceField(
        queryset=Station.objects.none(),
        label="Destination station",
        empty_label="Select the destination",
        help_text="Where the run ends. Must be different from the source.",
        widget=forms.Select(attrs={"class": "rc-select"}),
    )

    class Meta:
        model = Route
        fields = [
            "route_name",
            "source_station",
            "destination_station",
            "total_distance",
            "is_active",
        ]
        labels = {
            "route_name": "Route name",
            "total_distance": "Total distance (km)",
            "is_active": "Route is in service",
        }
        help_texts = {
            "route_name": "A name operators recognise, for example Delhi - Mumbai Central.",
            "total_distance": "Total run length in kilometres, to two decimal places.",
            "is_active": (
                "Turn this off to withdraw the route. Trains already assigned to "
                "it are kept, but the route stops appearing in new train forms."
            ),
        }
        error_messages = {
            "route_name": {
                "unique": "A route with this name already exists. Pick a different name.",
            },
        }
        widgets = {
            "route_name": forms.TextInput(
                attrs={
                    "class": "rc-input",
                    "placeholder": "Delhi - Mumbai Central",
                    "autofocus": True,
                    "autocomplete": "off",
                }
            ),
            "total_distance": forms.NumberInput(
                attrs={
                    "class": "rc-input",
                    "step": "0.01",
                    "min": "0.01",
                    "placeholder": "1384.00",
                    "inputmode": "decimal",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        stations = Station.objects.all()
        self.fields["source_station"].queryset = active_with_current(
            stations, self.instance.source_station_id
        ).order_by("name")
        self.fields["destination_station"].queryset = active_with_current(
            stations, self.instance.destination_station_id
        ).order_by("name")

    # ``Route.clean()`` rejects source == destination and already reports it on
    # ``destination_station``; repeating the check here would double the message.


# ---------------------------------------------------------------------------
# Route station (an ordered halt)
# ---------------------------------------------------------------------------
class RouteStationForm(forms.ModelForm):
    """Place one halt on a route, timed from the origin departure."""

    route = RouteChoiceField(
        queryset=Route.objects.none(),
        label="Route",
        empty_label="Select a route",
        help_text="The corridor this halt belongs to.",
        widget=forms.Select(attrs={"class": "rc-select", "autofocus": True}),
    )
    station = StationChoiceField(
        queryset=Station.objects.none(),
        label="Station",
        empty_label="Select a station",
        help_text="Each station may appear only once on a route.",
        widget=forms.Select(attrs={"class": "rc-select"}),
    )

    class Meta:
        model = RouteStation
        fields = [
            "route",
            "station",
            "sequence_number",
            "arrival_offset",
            "departure_offset",
        ]
        labels = {
            "sequence_number": "Stop number",
            "arrival_offset": "Arrival offset (minutes)",
            "departure_offset": "Departure offset (minutes)",
        }
        help_texts = {
            "sequence_number": (
                "Position of this halt along the route, starting at 1 for the "
                "origin. Each number is used once per route."
            ),
            "arrival_offset": (
                "Minutes from the origin departure until the train arrives here. "
                "Use 0 for the originating station."
            ),
            "departure_offset": (
                "Minutes from the origin departure until the train leaves here. "
                "The gap from the arrival offset is the halt time."
            ),
        }
        widgets = {
            "sequence_number": forms.NumberInput(
                attrs={"class": "rc-input", "min": 1, "max": 200, "step": 1, "placeholder": "1"}
            ),
            "arrival_offset": forms.NumberInput(
                attrs={"class": "rc-input", "min": 0, "max": 10080, "step": 1, "placeholder": "0"}
            ),
            "departure_offset": forms.NumberInput(
                attrs={"class": "rc-input", "min": 0, "max": 10080, "step": 1, "placeholder": "0"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["route"].queryset = (
            active_with_current(Route.objects.all(), self.instance.route_id)
            .select_related("source_station", "destination_station")
            .order_by("route_name")
        )
        self.fields["station"].queryset = active_with_current(
            Station.objects.all(), self.instance.station_id
        ).order_by("name")

    def clean(self):
        """Turn both route uniqueness rules into readable field errors."""
        cleaned_data = super().clean()
        route = cleaned_data.get("route")
        station = cleaned_data.get("station")
        sequence = cleaned_data.get("sequence_number")

        if route is None:
            return cleaned_data

        halts = RouteStation.objects.filter(route=route)
        if self.instance.pk:
            halts = halts.exclude(pk=self.instance.pk)

        if sequence is not None:
            taken = halts.filter(sequence_number=sequence).select_related("station").first()
            if taken is not None:
                self.add_error(
                    "sequence_number",
                    f"Stop number {sequence} on {route.route_name} is already "
                    f"{taken.station.station_code}. Choose another number.",
                )

        if station is not None and halts.filter(station=station).exists():
            self.add_error(
                "station",
                f"{station.station_code} is already a halt on "
                f"{route.route_name}. Edit that halt instead of adding it twice.",
            )

        return cleaned_data

    # ``RouteStation.clean()`` rejects a departure offset earlier than the
    # arrival offset and reports it on ``departure_offset``.


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------
class TrainForm(forms.ModelForm):
    """Register a rake and assign it to a route."""

    route = RouteChoiceField(
        queryset=Route.objects.none(),
        label="Route",
        empty_label="Select a route",
        help_text="Only routes that are in service are listed.",
        widget=forms.Select(attrs={"class": "rc-select"}),
    )

    class Meta:
        model = Train
        fields = ["train_number", "train_name", "route", "total_coaches", "status"]
        labels = {
            "train_number": "Train number",
            "train_name": "Train name",
            "total_coaches": "Coaches in the rake",
            "status": "Operating status",
        }
        help_texts = {
            "train_number": "4 to 6 digits, for example 12951.",
            "train_name": "Public name, for example Mumbai Rajdhani Express.",
            "total_coaches": "Number of coaches in the rake, between 1 and 30.",
            "status": (
                "Maintenance keeps the train on the books but flags it as "
                "unavailable for service."
            ),
        }
        widgets = {
            "train_number": forms.TextInput(
                attrs={
                    "class": "rc-input",
                    "placeholder": "12951",
                    "autofocus": True,
                    "inputmode": "numeric",
                    "autocomplete": "off",
                }
            ),
            "train_name": forms.TextInput(
                attrs={
                    "class": "rc-input",
                    "placeholder": "Mumbai Rajdhani Express",
                    "autocomplete": "off",
                }
            ),
            "total_coaches": forms.NumberInput(
                attrs={"class": "rc-input", "min": 1, "max": 30, "step": 1, "placeholder": "18"}
            ),
            "status": forms.Select(attrs={"class": "rc-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["route"].queryset = (
            active_with_current(Route.objects.all(), self.instance.route_id)
            .select_related("source_station", "destination_station")
            .order_by("route_name")
        )

    def clean_train_number(self):
        """Check the format and the number's availability across the archive.

        ``Train.objects`` hides soft deleted rows, so Django's own uniqueness
        check cannot see an archived train holding this number -- saving would
        fail at the database instead. ``all_objects`` closes that gap.
        """
        number = (self.cleaned_data.get("train_number") or "").strip()

        if not TRAIN_NUMBER_RE.match(number):
            raise forms.ValidationError(
                "Train number must be 4 to 6 digits, for example 12951."
            )

        taken = Train.all_objects.filter(train_number=number)
        if self.instance.pk:
            taken = taken.exclude(pk=self.instance.pk)

        existing = taken.first()
        if existing is not None:
            if existing.is_deleted:
                raise forms.ValidationError(
                    f"Train number {number} belongs to an archived train "
                    f"({existing.train_name}). Restore that train instead of "
                    f"creating a duplicate."
                )
            raise forms.ValidationError(
                f"Train number {number} is already used by {existing.train_name}."
            )

        return number


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------
class ScheduleForm(forms.ModelForm):
    """Book a train onto a platform for one dated run."""

    train = TrainChoiceField(
        queryset=Train.objects.none(),
        label="Train",
        empty_label="Select a train",
        help_text="Archived trains are not listed.",
        widget=forms.Select(attrs={"class": "rc-select", "autofocus": True}),
    )
    platform = PlatformChoiceField(
        queryset=Platform.objects.none(),
        label="Platform",
        empty_label="Select a platform",
        help_text="Grouped by station. A platform can hold only one run at a time.",
        widget=forms.Select(attrs={"class": "rc-select"}),
    )

    class Meta:
        model = Schedule
        fields = [
            "train",
            "platform",
            "departure_datetime",
            "arrival_datetime",
            "delay_minutes",
            "is_cancelled",
        ]
        labels = {
            "departure_datetime": "Departure date and time",
            "arrival_datetime": "Arrival date and time",
            "delay_minutes": "Running delay (minutes)",
            "is_cancelled": "This run is cancelled",
        }
        help_texts = {
            "departure_datetime": "Scheduled departure from the platform above.",
            "arrival_datetime": "Scheduled arrival, which must be after the departure.",
            "delay_minutes": (
                "Current running delay in minutes, up to 1440 (one full day). "
                "Leave it at 0 when the train is on time."
            ),
            "is_cancelled": (
                "A cancelled run keeps its record for reporting and releases "
                "the platform for other trains."
            ),
        }
        widgets = {
            "departure_datetime": forms.DateTimeInput(
                attrs={"class": "rc-input", "type": "datetime-local"},
                format=DATETIME_LOCAL_FORMAT,
            ),
            "arrival_datetime": forms.DateTimeInput(
                attrs={"class": "rc-input", "type": "datetime-local"},
                format=DATETIME_LOCAL_FORMAT,
            ),
            "delay_minutes": forms.NumberInput(
                attrs={"class": "rc-input", "min": 0, "max": 1440, "step": 1, "placeholder": "0"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        trains = Train.objects.all()
        if self.instance.train_id:
            # Keep the saved train selectable even if it was archived later.
            trains = Train.all_objects.filter(
                Q(is_deleted=False) | Q(pk=self.instance.train_id)
            )
        self.fields["train"].queryset = trains.select_related("route").order_by(
            "train_number"
        )

        self.fields["platform"].queryset = (
            active_with_current(Platform.objects.all(), self.instance.platform_id)
            .select_related("station")
            .order_by("station__station_code", "platform_number")
        )

        for name in ("departure_datetime", "arrival_datetime"):
            self.fields[name].input_formats = DATETIME_INPUT_FORMATS

    def clean_delay_minutes(self):
        delay = self.cleaned_data.get("delay_minutes")
        if delay is not None and delay > 1440:
            raise forms.ValidationError(
                "A delay cannot exceed 1440 minutes (24 hours). Cancel the run "
                "instead of recording a longer delay."
            )
        return delay

    # ``Schedule.clean()`` rejects an arrival that is not after the departure
    # and detects platform double-booking, reporting each on its own field.
