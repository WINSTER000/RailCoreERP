"""Template context shared by every authenticated page."""

from django.urls import reverse

from .permissions import can_view, permission_map

#: Sidebar definition: (section title, [(module, label, url name, icon id)])
NAV_SECTIONS = [
    (
        "Overview",
        [
            ("dashboard", "Dashboard", "dashboard:home", "gauge"),
        ],
    ),
    (
        "Operations",
        [
            ("trains", "Trains", "railway:train_list", "train"),
            ("routes", "Routes", "railway:route_list", "route"),
            ("schedules", "Schedules", "railway:schedule_list", "calendar"),
        ],
    ),
    (
        "Network",
        [
            ("stations", "Stations", "railway:station_list", "building"),
            ("platforms", "Platforms", "railway:platform_list", "layers"),
            ("route_stations", "Route Stations", "railway:route_station_list", "list"),
        ],
    ),
    (
        "System",
        [
            ("notifications", "Notifications", "notifications:list", "bell"),
            ("activity_logs", "Activity Log", "activity_logs:list", "history"),
            ("users", "Users", "accounts:user_list", "users"),
            ("profile", "Profile", "accounts:profile", "user"),
        ],
    ),
]


def navigation(request):
    """Sidebar entries and the permission map used to hide action buttons."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"nav_sections": [], "rc_perms": {}}

    sections = []
    for title, items in NAV_SECTIONS:
        visible = [
            {
                "key": key,
                "label": label,
                "url": reverse(url_name),
                "icon": icon,
            }
            for key, label, url_name, icon in items
            if can_view(user, key)
        ]
        if visible:
            sections.append({"title": title, "items": visible})

    return {"nav_sections": sections, "rc_perms": permission_map(user)}
