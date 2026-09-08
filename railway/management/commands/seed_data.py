"""Populate RailCore ERP with a realistic, self-consistent demo network.

    python manage.py seed_data              # create or update the demo data
    python manage.py seed_data --flush      # wipe the demo data first, then seed

The command is idempotent: running it twice leaves the database in the same
state, so it is safe to re-run after migrations. Every record it writes is a
normal row created through the ORM -- nothing in the application reads from
this module at runtime.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Role
from activity_logs.models import ActivityLog
from notifications.models import Notification
from railway.models import Platform, Route, RouteStation, Schedule, Station, Train

User = get_user_model()

#: Shared password for every seeded account. Demo data only.
DEMO_PASSWORD = "RailCore@2025"

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
STATIONS = [
    # (code, name, city, state, platform_count, is_active)
    ("NDLS", "New Delhi", "New Delhi", "Delhi", 8, True),
    ("BCT", "Mumbai Central", "Mumbai", "Maharashtra", 7, True),
    ("MAS", "Chennai Central", "Chennai", "Tamil Nadu", 6, True),
    ("HWH", "Howrah Junction", "Kolkata", "West Bengal", 8, True),
    ("SBC", "KSR Bengaluru", "Bengaluru", "Karnataka", 6, True),
    ("ADI", "Ahmedabad Junction", "Ahmedabad", "Gujarat", 5, True),
    ("PUNE", "Pune Junction", "Pune", "Maharashtra", 4, True),
    ("BPL", "Bhopal Junction", "Bhopal", "Madhya Pradesh", 4, True),
    ("NGP", "Nagpur Junction", "Nagpur", "Maharashtra", 4, True),
    ("JP", "Jaipur Junction", "Jaipur", "Rajasthan", 4, True),
    ("LKO", "Lucknow Charbagh", "Lucknow", "Uttar Pradesh", 5, True),
    ("TVC", "Thiruvananthapuram Central", "Thiruvananthapuram", "Kerala", 4, True),
    ("CBE", "Coimbatore Junction", "Coimbatore", "Tamil Nadu", 3, True),
    ("VSKP", "Visakhapatnam", "Visakhapatnam", "Andhra Pradesh", 4, True),
    ("KOTA", "Kota Junction", "Kota", "Rajasthan", 3, False),
]

ROUTES = [
    # (route_name, source, destination, distance_km, is_active, [halt codes])
    (
        "Delhi - Mumbai Western Corridor",
        "NDLS",
        "BCT",
        Decimal("1384.00"),
        True,
        ["JP", "KOTA", "ADI"],
    ),
    (
        "Delhi - Chennai Grand Trunk",
        "NDLS",
        "MAS",
        Decimal("2180.00"),
        True,
        ["BPL", "NGP", "VSKP"],
    ),
    (
        "Howrah - Delhi Eastern Mainline",
        "HWH",
        "NDLS",
        Decimal("1451.00"),
        True,
        ["LKO"],
    ),
    (
        "Mumbai - Bengaluru Deccan Link",
        "BCT",
        "SBC",
        Decimal("981.00"),
        True,
        ["PUNE"],
    ),
    (
        "Chennai - Thiruvananthapuram Coastal",
        "MAS",
        "TVC",
        Decimal("922.00"),
        True,
        ["CBE"],
    ),
    (
        "Bengaluru - Ahmedabad Cross Country",
        "SBC",
        "ADI",
        Decimal("1712.00"),
        True,
        ["PUNE", "BCT"],
    ),
    (
        "Nagpur - Kolkata Central Link",
        "NGP",
        "HWH",
        Decimal("1103.00"),
        False,
        [],
    ),
]

TRAINS = [
    # (number, name, route_name, coaches, status)
    ("12951", "Mumbai Rajdhani Express", "Delhi - Mumbai Western Corridor", 20, Train.ACTIVE),
    ("12953", "August Kranti Rajdhani", "Delhi - Mumbai Western Corridor", 19, Train.ACTIVE),
    ("12615", "Grand Trunk Express", "Delhi - Chennai Grand Trunk", 22, Train.ACTIVE),
    ("12621", "Tamil Nadu Express", "Delhi - Chennai Grand Trunk", 21, Train.MAINTENANCE),
    ("12301", "Howrah Rajdhani Express", "Howrah - Delhi Eastern Mainline", 20, Train.ACTIVE),
    ("12313", "Sealdah Duronto Express", "Howrah - Delhi Eastern Mainline", 18, Train.ACTIVE),
    ("11301", "Udyan Express", "Mumbai - Bengaluru Deccan Link", 24, Train.ACTIVE),
    ("12027", "Deccan Shatabdi Express", "Mumbai - Bengaluru Deccan Link", 14, Train.ACTIVE),
    ("12695", "Kerala Superfast Express", "Chennai - Thiruvananthapuram Coastal", 20, Train.ACTIVE),
    ("12697", "Coastal Sampark Express", "Chennai - Thiruvananthapuram Coastal", 17, Train.INACTIVE),
    ("16501", "Ahmedabad Express", "Bengaluru - Ahmedabad Cross Country", 23, Train.ACTIVE),
    ("12833", "Deccan Cross Country Express", "Bengaluru - Ahmedabad Cross Country", 19, Train.MAINTENANCE),
    ("18029", "Shalimar Express", "Nagpur - Kolkata Central Link", 22, Train.INACTIVE),
]

#: (username, first, last, role, phone) -- one manager plus staff per function.
USERS = [
    ("admin", "Aarav", "Mehta", Role.ADMIN, "+91 98200 10001"),
    ("rmanager", "Kavya", "Iyer", Role.RAILWAY_MANAGER, "+91 98200 10002"),
    ("rmanager2", "Rohan", "Deshpande", Role.RAILWAY_MANAGER, "+91 98200 10003"),
    ("smanager", "Neha", "Sharma", Role.STATION_MANAGER, "+91 98200 10004"),
    ("smanager2", "Vikram", "Rao", Role.STATION_MANAGER, "+91 98200 10005"),
    ("opsstaff", "Ishaan", "Nair", Role.OPERATIONS_STAFF, "+91 98200 10006"),
    ("opsstaff2", "Meera", "Krishnan", Role.OPERATIONS_STAFF, "+91 98200 10007"),
]

#: Runs booked per train: (day offset from today, departure hour, journey hours).
RUN_PATTERN = [
    (-2, 16, 16),
    (-1, 16, 16),
    (0, 16, 16),
    (1, 16, 16),
    (2, 16, 16),
]


class Command(BaseCommand):
    help = "Seed RailCore ERP with a realistic demo railway network."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing railway data, notifications and logs before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        roles = self._seed_roles()
        users = self._seed_users(roles)
        stations = self._seed_stations()
        platforms = self._seed_platforms(stations)
        routes = self._seed_routes(stations)
        self._seed_route_stations(routes, stations)
        trains = self._seed_trains(routes)
        schedules = self._seed_schedules(trains, platforms, stations)
        self._seed_notifications(users, schedules)
        self._seed_activity(users, trains, stations)

        self._report(users)

    # -- flush -----------------------------------------------------------
    def _flush(self):
        self.stdout.write("Flushing existing demo data...")
        Notification.objects.all().delete()
        ActivityLog.objects.all().delete()
        Schedule.objects.all().delete()
        Train.all_objects.all().delete()
        RouteStation.objects.all().delete()
        Route.objects.all().delete()
        Platform.objects.all().delete()
        Station.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

    # -- roles and users -------------------------------------------------
    def _seed_roles(self):
        roles = {}
        for name, description in Role.DEFAULT_ROLES:
            role, created = Role.objects.get_or_create(
                name=name,
                defaults={"description": description, "is_active": True},
            )
            if not created and role.description != description:
                role.description = description
                role.save(update_fields=["description", "updated_at"])
            roles[name] = role
        self.stdout.write(f"Roles ready: {len(roles)}")
        return roles

    def _seed_users(self, roles):
        users = {}
        for username, first_name, last_name, role_name, phone in USERS:
            defaults = {
                "first_name": first_name,
                "last_name": last_name,
                "email": f"{username}@railcore.example",
                "role": roles[role_name],
                "phone": phone,
                "is_active": True,
                "is_staff": role_name == Role.ADMIN,
                "is_superuser": role_name == Role.ADMIN,
            }
            user, created = User.objects.get_or_create(username=username, defaults=defaults)
            if not created:
                for field, value in defaults.items():
                    setattr(user, field, value)
                user.is_deleted = False
            user.set_password(DEMO_PASSWORD)
            user.save()
            users[username] = user
        self.stdout.write(f"Employees ready: {len(users)}")
        return users

    # -- network ---------------------------------------------------------
    def _seed_stations(self):
        stations = {}
        for code, name, city, state, _platforms, is_active in STATIONS:
            station, _ = Station.objects.update_or_create(
                station_code=code,
                defaults={
                    "name": name,
                    "city": city,
                    "state": state,
                    "is_active": is_active,
                },
            )
            stations[code] = station
        self.stdout.write(f"Stations ready: {len(stations)}")
        return stations

    def _seed_platforms(self, stations):
        platforms = {}
        created = 0
        for code, _name, _city, _state, platform_count, _is_active in STATIONS:
            station = stations[code]
            for number in range(1, platform_count + 1):
                # The highest numbered platform of each big station is closed for works.
                is_active = not (platform_count >= 6 and number == platform_count)
                platform, made = Platform.objects.update_or_create(
                    station=station,
                    platform_number=number,
                    defaults={"is_active": is_active},
                )
                platforms.setdefault(code, []).append(platform)
                created += int(made)
        total = sum(len(items) for items in platforms.values())
        self.stdout.write(f"Platforms ready: {total} ({created} new)")
        return platforms

    def _seed_routes(self, stations):
        routes = {}
        for route_name, source, destination, distance, is_active, _halts in ROUTES:
            route, _ = Route.objects.update_or_create(
                route_name=route_name,
                defaults={
                    "source_station": stations[source],
                    "destination_station": stations[destination],
                    "total_distance": distance,
                    "is_active": is_active,
                },
            )
            routes[route_name] = route
        self.stdout.write(f"Routes ready: {len(routes)}")
        return routes

    def _seed_route_stations(self, routes, stations):
        """Lay out each route as origin -> intermediate halts -> destination."""
        total = 0
        for route_name, source, destination, _distance, _is_active, halt_codes in ROUTES:
            route = routes[route_name]
            leg_codes = [source, *halt_codes, destination]
            # Spread the halts evenly across the journey; 95 minutes per leg.
            for index, code in enumerate(leg_codes):
                arrival = 0 if index == 0 else index * 95
                departure = arrival if index == len(leg_codes) - 1 else arrival + 5
                RouteStation.objects.update_or_create(
                    route=route,
                    station=stations[code],
                    defaults={
                        "sequence_number": index + 1,
                        "arrival_offset": arrival,
                        "departure_offset": departure,
                    },
                )
                total += 1
        self.stdout.write(f"Route halts ready: {total}")

    def _seed_trains(self, routes):
        trains = {}
        for number, name, route_name, coaches, status in TRAINS:
            train, _ = Train.all_objects.update_or_create(
                train_number=number,
                defaults={
                    "train_name": name,
                    "route": routes[route_name],
                    "total_coaches": coaches,
                    "status": status,
                    "is_deleted": False,
                },
            )
            trains[number] = train

        # One archived rake, so the archive screen has something to show.
        archived, _ = Train.all_objects.update_or_create(
            train_number="19019",
            defaults={
                "train_name": "Dehradun Express (withdrawn)",
                "route": routes["Howrah - Delhi Eastern Mainline"],
                "total_coaches": 16,
                "status": Train.INACTIVE,
                "is_deleted": True,
            },
        )
        trains[archived.train_number] = archived

        self.stdout.write(f"Trains ready: {len(trains)} (1 archived)")
        return trains

    def _seed_schedules(self, trains, platforms, stations):
        """Book every in-service train onto its origin platform for five days."""
        today = timezone.localtime(timezone.now()).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        created = []

        for slot, (number, _name, route_name, _coaches, status) in enumerate(TRAINS):
            if status != Train.ACTIVE:
                continue
            train = trains[number]
            source_code = next(row[1] for row in ROUTES if row[0] == route_name)
            station_platforms = [p for p in platforms[source_code] if p.is_active]
            platform = station_platforms[slot % len(station_platforms)]

            for run_index, (day_offset, hour, journey_hours) in enumerate(RUN_PATTERN):
                # Stagger departures so two trains never share a platform window.
                departure = today + timedelta(
                    days=day_offset, hours=hour, minutes=(slot % 6) * 7
                )
                arrival = departure + timedelta(hours=journey_hours)

                cancelled = run_index == 0 and slot % 5 == 0
                delay = 0
                if not cancelled and run_index == 1 and slot % 3 == 0:
                    delay = 20 + (slot % 4) * 15

                schedule, _ = Schedule.objects.update_or_create(
                    train=train,
                    departure_datetime=departure,
                    defaults={
                        "platform": platform,
                        "arrival_datetime": arrival,
                        "delay_minutes": delay,
                        "is_cancelled": cancelled,
                    },
                )
                created.append(schedule)

        self.stdout.write(f"Schedules ready: {len(created)}")
        return created

    # -- notifications and audit trail -----------------------------------
    def _seed_notifications(self, users, schedules):
        if Notification.objects.exists():
            self.stdout.write("Notifications already present, leaving them untouched.")
            return

        cancelled = [s for s in schedules if s.is_cancelled][:2]
        delayed = [s for s in schedules if s.delay_minutes and not s.is_cancelled][:3]

        rows = []
        for account in users.values():
            for schedule in cancelled:
                rows.append(
                    Notification(
                        user=account,
                        title=f"Run cancelled: {schedule.train.train_number}",
                        message=(
                            f"{schedule.train.train_name} departing "
                            f"{schedule.departure_datetime:%d %b %Y at %H:%M} from "
                            f"{schedule.platform} has been cancelled."
                        ),
                        level=Notification.DANGER,
                        url=f"/railway/schedules/{schedule.pk}/",
                    )
                )
            for schedule in delayed:
                rows.append(
                    Notification(
                        user=account,
                        title=f"Delay recorded: {schedule.train.train_number}",
                        message=(
                            f"{schedule.train.train_name} is running "
                            f"{schedule.delay_minutes} minutes late from "
                            f"{schedule.platform}."
                        ),
                        level=Notification.WARNING,
                        url=f"/railway/schedules/{schedule.pk}/",
                    )
                )
            rows.append(
                Notification(
                    user=account,
                    title="Welcome to RailCore ERP",
                    message=(
                        "Your account is ready. Open the dashboard for today's "
                        "timetable, fleet status and network statistics."
                    ),
                    level=Notification.INFO,
                    url="/dashboard/",
                    is_read=True,
                )
            )

        Notification.objects.bulk_create(rows)
        self.stdout.write(f"Notifications ready: {len(rows)}")

    def _seed_activity(self, users, trains, stations):
        if ActivityLog.objects.exists():
            self.stdout.write("Activity log already present, leaving it untouched.")
            return

        admin = users["admin"]
        railway_manager = users["rmanager"]
        station_manager = users["smanager"]
        ops = users["opsstaff"]

        entries = [
            (admin, ActivityLog.LOGIN, "", "", "Signed in to RailCore ERP"),
            (
                station_manager,
                ActivityLog.CREATE,
                "Station",
                stations["NDLS"].pk,
                f"Created Station {stations['NDLS']}",
            ),
            (
                station_manager,
                ActivityLog.UPDATE,
                "Station",
                stations["KOTA"].pk,
                f"Updated Station {stations['KOTA']}",
            ),
            (
                railway_manager,
                ActivityLog.CREATE,
                "Train",
                trains["12951"].pk,
                f"Created Train {trains['12951']}",
            ),
            (
                railway_manager,
                ActivityLog.UPDATE,
                "Train",
                trains["12621"].pk,
                f"Moved Train {trains['12621']} into maintenance",
            ),
            (
                railway_manager,
                ActivityLog.DELETE,
                "Train",
                trains["19019"].pk,
                f"Archived Train {trains['19019']}",
            ),
            (ops, ActivityLog.LOGIN, "", "", "Signed in to RailCore ERP"),
            (ops, ActivityLog.LOGOUT, "", "", "Signed out of RailCore ERP"),
        ]

        for actor, action, model_name, object_id, description in entries:
            ActivityLog.objects.create(
                user=actor,
                action=action,
                model_name=model_name,
                object_id="" if object_id in (None, "") else str(object_id),
                description=description,
            )

        self.stdout.write(f"Activity log ready: {len(entries)}")

    # -- summary ---------------------------------------------------------
    def _report(self, users):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("RailCore ERP demo data is ready."))
        self.stdout.write("")
        self.stdout.write("Sign in with any of these accounts:")
        for username, first_name, last_name, role_name, _phone in USERS:
            self.stdout.write(f"  {username:<11} {role_name:<17} {first_name} {last_name}")
        self.stdout.write("")
        self.stdout.write(f"Password for every demo account: {DEMO_PASSWORD}")
        self.stdout.write(
            self.style.WARNING("Change these passwords before deploying anywhere real.")
        )
