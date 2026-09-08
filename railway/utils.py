"""Shared list-page helpers: pagination, search and sorting."""

from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q


def paginate(request, queryset, per_page=None):
    """Return a ``Page`` for *queryset* using the ``?page=`` query parameter."""
    per_page = per_page or getattr(settings, "RAILCORE_PAGE_SIZE", 10)
    paginator = Paginator(queryset, per_page)
    try:
        return paginator.page(request.GET.get("page") or 1)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def apply_search(queryset, term, fields):
    """Case-insensitive OR search of *term* across *fields*."""
    term = (term or "").strip()
    if not term or not fields:
        return queryset
    condition = Q()
    for field in fields:
        condition |= Q(**{f"{field}__icontains": term})
    return queryset.filter(condition)


def clean_sort(value, allowed, default):
    """Validate a ``?sort=`` value against *allowed*, falling back to *default*."""
    value = (value or "").strip()
    if value and value.lstrip("-") in allowed:
        return value
    return default


def apply_sort(queryset, value, allowed, default):
    """Order *queryset* by a whitelisted ``?sort=`` value."""
    return queryset.order_by(clean_sort(value, allowed, default))
