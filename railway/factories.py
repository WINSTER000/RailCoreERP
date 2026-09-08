"""Object factories for the railway domain, shared by the test suite."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .models import Platform, Route, RouteStation, Schedule, Station, Train

_counter = {"station": 0, "route": 0, "train": 0}


def _next(key):
    _counter[key] += 1
    return _counter[key]


def create_station(name=None, station_code=None, **kwargs):
    index = _next("station")
    defaults = {
        "name": name or f"Test Station {index}",
        "station_code": station_code or f"TS{index:03d}",
        "city": kwargs.pop("city", "Test City"),
        "state": kwargs.pop("state", "Test State"),
        "is_active": kwargs.pop("is_active", True),
    }
    defaults.update(kwargs)
    return Station.objects.create(**defaults)


def create_platform(station=None, platform_number=None, **kwargs):
    station = station or create_station()
    if platform_number is None:
        platform_number = station.platforms.count() + 1
    return Platform.objects.create(
        station=station,
        platform_number=platform_number,
        is_active=kwargs.pop("is_active", True),
        **kwargs,
    )


def create_route(route_name=None, source_station=None, destination_station=None, **kwargs):
    index = _next("route")
    return Route.objects.create(
        route_name=route_name or f"Test Route {index}",
        source_station=source_station or create_station(),
        destination_station=destination_station or create_station(),
        total_distance=kwargs.pop("total_distance", Decimal("450.50")),
        is_active=kwargs.pop("is_active", True),
        **kwargs,
    )


def create_route_station(route=None, station=None, sequence_number=1, **kwargs):
    route = route or create_route()
    return RouteStation.objects.create(
        route=route,
        station=station or create_station(),
        sequence_number=sequence_number,
        arrival_offset=kwargs.pop("arrival_offset", 60 * sequence_number),
        departure_offset=kwargs.pop("departure_offset", 60 * sequence_number + 5),
        **kwargs,
    )


def create_train(train_number=None, route=None, **kwargs):
    index = _next("train")
    return Train.objects.create(
        train_number=train_number or f"{20000 + index}",
        train_name=kwargs.pop("train_name", f"Test Express {index}"),
        route=route or create_route(),
        total_coaches=kwargs.pop("total_coaches", 18),
        status=kwargs.pop("status", Train.ACTIVE),
        is_deleted=kwargs.pop("is_deleted", False),
        **kwargs,
    )


def create_schedule(train=None, platform=None, departure=None, arrival=None, **kwargs):
    departure = departure or timezone.now() + timedelta(hours=3)
    arrival = arrival or departure + timedelta(hours=8)
    return Schedule.objects.create(
        train=train or create_train(),
        platform=platform or create_platform(),
        departure_datetime=departure,
        arrival_datetime=arrival,
        delay_minutes=kwargs.pop("delay_minutes", 0),
        is_cancelled=kwargs.pop("is_cancelled", False),
        **kwargs,
    )
