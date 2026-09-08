"""Role based access control for RailCore ERP.

Every screen in the application belongs to a *module*. Two capabilities are
defined per module:

``view``    -- may open list/detail pages.
``manage``  -- may create, edit or delete records.

Administrators (and Django superusers) always have both capabilities.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Role

ADMIN = Role.ADMIN
RAILWAY_MANAGER = Role.RAILWAY_MANAGER
STATION_MANAGER = Role.STATION_MANAGER
OPERATIONS_STAFF = Role.OPERATIONS_STAFF

ALL_ROLES = frozenset({ADMIN, RAILWAY_MANAGER, STATION_MANAGER, OPERATIONS_STAFF})

#: module -> {"view": {roles}, "manage": {roles}}
MODULE_PERMISSIONS = {
    "dashboard": {"view": ALL_ROLES, "manage": frozenset()},
    "trains": {
        "view": frozenset({ADMIN, RAILWAY_MANAGER, OPERATIONS_STAFF}),
        "manage": frozenset({ADMIN, RAILWAY_MANAGER}),
    },
    "routes": {
        "view": frozenset({ADMIN, RAILWAY_MANAGER, OPERATIONS_STAFF}),
        "manage": frozenset({ADMIN, RAILWAY_MANAGER}),
    },
    "schedules": {
        "view": ALL_ROLES,
        "manage": frozenset({ADMIN, RAILWAY_MANAGER, OPERATIONS_STAFF}),
    },
    "stations": {
        "view": ALL_ROLES,
        "manage": frozenset({ADMIN, STATION_MANAGER}),
    },
    "platforms": {
        "view": ALL_ROLES,
        "manage": frozenset({ADMIN, STATION_MANAGER}),
    },
    "route_stations": {
        "view": ALL_ROLES,
        "manage": frozenset({ADMIN, STATION_MANAGER}),
    },
    "activity_logs": {
        "view": frozenset({ADMIN, RAILWAY_MANAGER}),
        "manage": frozenset(),
    },
    "users": {"view": frozenset({ADMIN}), "manage": frozenset({ADMIN})},
    # Personal screens every signed in employee can reach.
    "notifications": {"view": ALL_ROLES, "manage": ALL_ROLES},
    "profile": {"view": ALL_ROLES, "manage": ALL_ROLES},
}

#: Modules that stay reachable even when an account has no role assigned yet.
ROLE_FREE_MODULES = frozenset({"dashboard", "notifications", "profile"})


def _capability(user, module, capability):
    rules = MODULE_PERMISSIONS.get(module)
    if rules is None:
        raise KeyError(f"Unknown RailCore module: {module!r}")
    if not user.is_authenticated:
        return False
    if user.is_superuser or getattr(user, "is_admin", False):
        return True
    role_name = user.role.name if getattr(user, "role_id", None) else None
    if role_name is None:
        return module in ROLE_FREE_MODULES
    return role_name in rules[capability]


def can_view(user, module):
    """True when *user* may open the read-only screens of *module*."""
    return _capability(user, module, "view")


def can_manage(user, module):
    """True when *user* may create/edit/delete inside *module*."""
    return _capability(user, module, "manage")


def permission_map(user):
    """Every capability for *user*, ready to be used from templates."""
    return {
        module: {"view": can_view(user, module), "manage": can_manage(user, module)}
        for module in MODULE_PERMISSIONS
    }


def _guard(module, capability):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not _capability(request.user, module, capability):
                raise PermissionDenied(
                    f"Your role ({request.user.role_name}) cannot "
                    f"{'manage' if capability == 'manage' else 'open'} the "
                    f"{module.replace('_', ' ')} module."
                )
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def require_view(module):
    """Login + read access to *module*, otherwise HTTP 403."""
    return _guard(module, "view")


def require_manage(module):
    """Login + write access to *module*, otherwise HTTP 403."""
    return _guard(module, "manage")
