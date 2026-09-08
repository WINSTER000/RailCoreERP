"""Account factories and a shared TestCase base used across the test suite."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Role

User = get_user_model()

#: Password used by every factory-built account.
PASSWORD = "TestPass!2025"

_counter = {"user": 0}


def get_role(name):
    """Fetch (or create) one of the four RailCore roles by name."""
    description = dict(Role.DEFAULT_ROLES).get(name, "")
    role, _ = Role.objects.get_or_create(name=name, defaults={"description": description})
    return role


def create_user(username=None, role_name=None, **kwargs):
    """Create an employee account, optionally holding *role_name*."""
    _counter["user"] += 1
    index = _counter["user"]
    username = username or f"user{index}"

    password = kwargs.pop("password", PASSWORD)
    role = kwargs.pop("role", None)
    if role is None and role_name is not None:
        role = get_role(role_name)

    defaults = {
        "first_name": kwargs.pop("first_name", f"Test{index}"),
        "last_name": kwargs.pop("last_name", "Employee"),
        "email": kwargs.pop("email", f"{username}@railcore.example"),
        "role": role,
        "is_active": kwargs.pop("is_active", True),
    }
    defaults.update(kwargs)

    user = User(username=username, **defaults)
    user.set_password(password)
    user.save()
    return user


def create_admin(username="admin_user", **kwargs):
    kwargs.setdefault("is_staff", True)
    kwargs.setdefault("is_superuser", True)
    return create_user(username, role_name=Role.ADMIN, **kwargs)


def create_railway_manager(username="railway_manager", **kwargs):
    return create_user(username, role_name=Role.RAILWAY_MANAGER, **kwargs)


def create_station_manager(username="station_manager", **kwargs):
    return create_user(username, role_name=Role.STATION_MANAGER, **kwargs)


def create_operations_staff(username="ops_staff", **kwargs):
    return create_user(username, role_name=Role.OPERATIONS_STAFF, **kwargs)


class RailCoreTestCase(TestCase):
    """Base class giving every test one account per role, already built."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = create_admin()
        cls.railway_manager = create_railway_manager()
        cls.station_manager = create_station_manager()
        cls.operations_staff = create_operations_staff()
        cls.password = PASSWORD

    def login(self, user):
        """Sign *user* in through the test client."""
        signed_in = self.client.login(username=user.username, password=PASSWORD)
        self.assertTrue(signed_in, f"Could not sign in as {user.username}")
        return signed_in

    def assertForbidden(self, url, user, method="get", data=None):
        """Assert *user* is refused access to *url* with HTTP 403."""
        self.login(user)
        response = getattr(self.client, method)(url, data or {})
        self.assertEqual(
            response.status_code,
            403,
            f"{user.username} ({user.role_name}) should not reach {url}",
        )
        return response

    def assertAllowed(self, url, user, expected=200):
        """Assert *user* can open *url*."""
        self.login(user)
        response = self.client.get(url)
        self.assertEqual(
            response.status_code,
            expected,
            f"{user.username} ({user.role_name}) should reach {url}",
        )
        return response
