"""Reusable presentation helpers shared by every RailCore ERP template.

Load with ``{% load rc_tags %}``.
"""

from django import template
from django.http import QueryDict
from django.utils.html import format_html

register = template.Library()

#: status value -> badge tone (see ``.rc-badge--*`` in static/css/railcore.css)
BADGE_TONES = {
    # Train
    "ACTIVE": "success",
    "MAINTENANCE": "warning",
    "INACTIVE": "neutral",
    # Schedule
    "SCHEDULED": "info",
    "DELAYED": "warning",
    "CANCELLED": "danger",
    "COMPLETED": "neutral",
    # Activity log
    "CREATE": "success",
    "UPDATE": "info",
    "DELETE": "danger",
    "LOGIN": "info",
    "LOGOUT": "neutral",
    # Notifications / generic
    "PRIMARY": "primary",
    "NEUTRAL": "neutral",
    "INFO": "info",
    "SUCCESS": "success",
    "WARNING": "warning",
    "DANGER": "danger",
    "READ": "neutral",
    "UNREAD": "info",
    "ONLINE": "success",
    "OPERATIONAL": "success",
    "DEGRADED": "warning",
    "OFFLINE": "danger",
    "YES": "success",
    "NO": "neutral",
}

BADGE_LABELS = {
    "ACTIVE": "Active",
    "MAINTENANCE": "Maintenance",
    "INACTIVE": "Inactive",
    "SCHEDULED": "Scheduled",
    "DELAYED": "Delayed",
    "CANCELLED": "Cancelled",
    "COMPLETED": "Completed",
    "CREATE": "Create",
    "UPDATE": "Update",
    "DELETE": "Delete",
    "LOGIN": "Login",
    "LOGOUT": "Logout",
    "INFO": "Information",
    "SUCCESS": "Success",
    "WARNING": "Warning",
    "DANGER": "Critical",
    "OPERATIONAL": "Operational",
    "DEGRADED": "Degraded",
    "OFFLINE": "Offline",
}


# ---------------------------------------------------------------------------
# Icons
# ---------------------------------------------------------------------------
@register.simple_tag
def rc_icon(name, css_class="rc-icon"):
    """Render an icon from the inline SVG sprite (templates/partials/_icons.html)."""
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false"><use href="#icon-{}"></use></svg>',
        css_class,
        name,
    )


# ---------------------------------------------------------------------------
# Status badges
# ---------------------------------------------------------------------------
@register.filter
def badge_tone(value):
    return BADGE_TONES.get(str(value or "").strip().upper(), "neutral")


@register.inclusion_tag("partials/_badge.html")
def rc_badge(value, label=None):
    """``{% rc_badge train.status %}`` -> a coloured, always-labelled status pill."""
    key = str(value or "").strip().upper()
    return {
        "tone": BADGE_TONES.get(key, "neutral"),
        "label": label or BADGE_LABELS.get(key) or key.replace("_", " ").title() or "Unknown",
    }


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------
def _widget_name(field):
    try:
        return field.field.widget.__class__.__name__
    except AttributeError:  # pragma: no cover - defensive
        return ""


@register.filter
def is_checkbox(field):
    return _widget_name(field) == "CheckboxInput"


@register.filter
def is_select(field):
    return _widget_name(field) in {"Select", "SelectMultiple", "NullBooleanSelect"}


@register.filter
def is_textarea(field):
    return _widget_name(field) == "Textarea"


@register.filter
def is_file(field):
    return _widget_name(field) in {"ClearableFileInput", "FileInput"}


@register.inclusion_tag("partials/_field.html")
def rc_field(field, icon=""):
    """Render one bound form field with label, help text and error messages."""
    return {"field": field, "icon": icon}


# ---------------------------------------------------------------------------
# Sortable table headers
# ---------------------------------------------------------------------------
@register.inclusion_tag("partials/_sort_header.html", takes_context=True)
def rc_sort_header(context, field, label, align="left"):
    """A ``<th>`` whose link toggles ascending/descending ordering."""
    request = context.get("request")
    params = request.GET.copy() if request is not None else QueryDict(mutable=True)
    current = (params.get("sort") or "").strip()

    if current == field:
        state, next_value, icon = "asc", f"-{field}", "sort-asc"
    elif current == f"-{field}":
        state, next_value, icon = "desc", field, "sort-desc"
    else:
        state, next_value, icon = "none", field, "sort"

    params["sort"] = next_value
    params.pop("page", None)
    query = params.urlencode()

    return {
        "label": label,
        "url": f"?{query}" if query else "?",
        "state": state,
        "icon": icon,
        "align": align,
    }


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------
@register.filter
def minutes_display(value):
    """``95`` -> ``1h 35m``; ``0`` -> ``On time``."""
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return "-"
    if minutes <= 0:
        return "On time"
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h {remainder}m"
    if hours:
        return f"{hours}h"
    return f"{remainder}m"


@register.filter
def offset_display(value):
    """Route-station offsets: ``0`` -> ``Origin``, ``95`` -> ``+1h 35m``."""
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return "-"
    if minutes == 0:
        return "Origin"
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"+{hours}h {remainder}m"
    if hours:
        return f"+{hours}h"
    return f"+{remainder}m"


@register.simple_tag
def rc_percent(value, total, maximum=100):
    """Safe percentage used for CSS bar widths."""
    try:
        value = float(value or 0)
        total = float(total or 0)
    except (TypeError, ValueError):
        return 0
    if total <= 0:
        return 0
    return round(min(value / total * 100, maximum), 1)
