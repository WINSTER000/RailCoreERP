# RailCore ERP — internal build specification

**This file is the single source of truth for every agent working on this project.**
Read it fully before writing code. Follow it literally: class names, context keys,
URL names and template blocks are a contract between files written by different
agents. Inventing your own names breaks the build.

---

## 0. Ground rules

1. **No external network dependencies.** No CDN links, no Bootstrap, no Font Awesome,
   no Google Fonts, no Chart.js. Icons come from the inline SVG sprite. Charts are
   hand-rolled CSS/SVG. Fonts are a system stack.
2. **Never hardcode URLs.** Always `{% url 'namespace:name' %}` / `reverse()`.
3. **Never hardcode data.** Every number, name and label on screen comes from the DB.
4. Python: 4-space indent, double quotes, `snake_case`, imports grouped
   stdlib / django / local. Keep functions short and readable — this is a college
   submission that must be easy to explain, not a framework.
5. Templates: 2-space indent, `{% extends 'base.html' %}` first line,
   `{% load rc_tags %}` (and `{% load humanize %}` when needed) second.
6. Accessibility is mandatory: every input has a `<label>`, every icon-only control
   has `aria-label` or `.rc-sr-only` text, status is never colour-only (always text),
   focus styles are visible, tables use `<th scope="col">`.
7. Only write the files you are assigned. Do not create, edit or "fix" files owned by
   another agent. Do not add new dependencies to `requirements.txt`.
8. No `TODO`, no placeholder text, no dummy data, no commented-out code.

---

## 1. Project layout (already created)

```
config/            settings.py, urls.py, wsgi.py, asgi.py
accounts/          User + Role, RBAC, auth views, profile, user admin
dashboard/         aggregate dashboard view
railway/           Station, Platform, Route, RouteStation, Train, Schedule
notifications/     Notification + fan-out services
activity_logs/     ActivityLog + logging services
templates/         all templates (project-level, no app template dirs)
static/css/        railcore.css   (single stylesheet)
static/js/         railcore.js    (single script)
```

### Files that already exist and MUST NOT be modified

`config/*`, `accounts/models.py`, `accounts/permissions.py`,
`accounts/context_processors.py`, `accounts/signals.py`, `accounts/admin.py`,
`accounts/urls.py`, `accounts/factories.py`, `railway/models.py`,
`railway/admin.py`, `railway/urls.py`, `railway/utils.py`, `railway/factories.py`,
`railway/templatetags/rc_tags.py`, `activity_logs/*` (except `views.py`),
`notifications/*` (except `views.py`), `templates/partials/_icons.html`,
`templates/partials/_field.html`, `templates/partials/_badge.html`,
`templates/partials/_sort_header.html`, `requirements.txt`, `.env`, `.env.example`.

Read them — they define the models, the RBAC helpers and the UI atoms you must use.

---

## 2. Models quick reference

| Model | Key fields |
|---|---|
| `accounts.Role` | `name` (choices: Admin / Railway Manager / Station Manager / Operations Staff), `description`, `is_active`, timestamps. Constants: `Role.ADMIN`, `Role.RAILWAY_MANAGER`, `Role.STATION_MANAGER`, `Role.OPERATIONS_STAFF`, `Role.DEFAULT_ROLES` |
| `accounts.User` | AbstractUser + `role` FK, `phone`, `profile_image`, `is_deleted`, `created_at`, `updated_at`. Managers: `objects` (all), `active_objects` (not deleted). Props: `display_name`, `full_name`, `initials`, `role_name`, `is_admin`, `is_railway_manager`, `is_station_manager`, `is_operations_staff`. Methods: `soft_delete()`, `restore()` |
| `railway.Station` | `name`, `station_code` (unique, upper), `city`, `state`, `is_active`, timestamps. Props: `location`, `platform_count`, `active_platform_count`, `status_label` |
| `railway.Platform` | `station` FK (`related_name="platforms"`), `platform_number` (int 1-99), `is_active`. Unique together `(station, platform_number)`. Props: `label`, `status_label`, `schedule_count` |
| `railway.Route` | `route_name` (unique), `source_station` FK (`routes_from`), `destination_station` FK (`routes_to`), `total_distance` Decimal km, `is_active`. `clean()` rejects source == destination. Props: `corridor`, `halt_count`, `train_count`, `status_label` |
| `railway.RouteStation` | `route` FK (`route_stations`), `station` FK (`route_stations`), `sequence_number`, `arrival_offset`, `departure_offset` (minutes from origin). Unique `(route, sequence_number)` and `(route, station)`. `clean()` rejects departure < arrival. Prop: `halt_minutes` |
| `railway.Train` | `train_number` (unique, 4-6 digits), `train_name`, `route` FK (`trains`, PROTECT), `total_coaches` (1-30), `status` (`Train.ACTIVE` / `MAINTENANCE` / `INACTIVE`), `is_deleted`. `Train.objects` hides soft-deleted rows; `Train.all_objects` shows everything. Methods `soft_delete()`, `restore()`. Props: `schedule_count`, `upcoming_schedule_count` |
| `railway.Schedule` | `train` FK (`schedules`, CASCADE), `platform` FK (`schedules`, PROTECT), `departure_datetime`, `arrival_datetime`, `delay_minutes`, `is_cancelled`. `clean()` rejects arrival <= departure and platform double-booking. Props: `display_status` (`SCHEDULED`/`DELAYED`/`CANCELLED`/`COMPLETED`), `expected_arrival`, `duration_minutes`, `duration_display`, `journey_label` |
| `activity_logs.ActivityLog` | `user`, `action` (`CREATE`/`UPDATE`/`DELETE`/`LOGIN`/`LOGOUT`), `model_name`, `object_id`, `description`, `created_at`. Props: `actor_name`, `actor_initials`, `icon`, `target` |
| `notifications.Notification` | `user` FK, `title`, `message`, `level` (`INFO`/`SUCCESS`/`WARNING`/`DANGER`), `url`, `is_read`, `created_at`. Prop `icon`, method `mark_read()` |

---

## 3. RBAC — how to protect a view

```python
from accounts.permissions import require_manage, require_view

@require_view("trains")      # login + read access, else HTTP 403
def train_list(request): ...

@require_manage("trains")    # login + write access, else HTTP 403
def train_create(request): ...
```

Modules: `dashboard`, `trains`, `routes`, `schedules`, `stations`, `platforms`,
`route_stations`, `activity_logs`, `users`, `notifications`, `profile`.

| Module | view | manage |
|---|---|---|
| trains, routes | Admin, Railway Manager, Operations Staff | Admin, Railway Manager |
| schedules | everyone | Admin, Railway Manager, Operations Staff |
| stations, platforms, route_stations | everyone | Admin, Station Manager |
| activity_logs | Admin, Railway Manager | — |
| users | Admin | Admin |
| dashboard, notifications, profile | everyone | everyone |

In templates use the `rc_perms` context variable (provided automatically):

```html
{% if rc_perms.trains.manage %}<a class="rc-btn rc-btn--primary" href="{% url 'railway:train_add' %}">…</a>{% endif %}
```

---

## 4. Activity logs & notifications — how to record events

```python
from activity_logs.services import log_create, log_update, log_delete
from notifications.services import notify_roles
from notifications.models import Notification
from accounts.models import Role

log_create(request.user, train, f"Added train {train.train_number} - {train.train_name}")
log_update(request.user, train, f"Updated train {train.train_number}")
log_delete(request.user, train, f"Archived train {train.train_number}")

notify_roles(
    [Role.RAILWAY_MANAGER, Role.OPERATIONS_STAFF],
    "Schedule cancelled",
    f"Train {schedule.train.train_number} on {date} has been cancelled.",
    level=Notification.DANGER,
    url=reverse("railway:schedule_detail", args=[schedule.pk]),
    exclude=request.user,
)
```

Rules: **every** create/update/delete view writes exactly one activity log.
Notifications are raised for: schedule cancelled (`DANGER`), schedule delay set or
changed (`WARNING`), train status moved to `MAINTENANCE` (`WARNING`), new train added
(`INFO`), station deactivated (`WARNING`), new user account created (`INFO`, to Admins).

---

## 5. URL names (complete, do not invent others)

```
root                              /
accounts:login                    /accounts/login/
accounts:logout                   /accounts/logout/            (POST only)
accounts:profile                  /accounts/profile/
accounts:password_change          /accounts/profile/password/
accounts:user_list                /accounts/users/
accounts:user_add                 /accounts/users/add/
accounts:user_detail              /accounts/users/<pk>/
accounts:user_edit                /accounts/users/<pk>/edit/
accounts:user_delete              /accounts/users/<pk>/delete/
accounts:user_restore             /accounts/users/<pk>/restore/   (POST)
dashboard:home                    /dashboard/
railway:train_list                /railway/trains/
railway:train_add                 /railway/trains/add/
railway:train_archive             /railway/trains/archive/
railway:train_detail              /railway/trains/<pk>/
railway:train_edit                /railway/trains/<pk>/edit/
railway:train_delete              /railway/trains/<pk>/delete/
railway:train_restore             /railway/trains/<pk>/restore/   (POST)
railway:route_list  route_add  route_detail  route_edit  route_delete
railway:schedule_list  schedule_add  schedule_detail  schedule_edit  schedule_delete
railway:schedule_cancel           /railway/schedules/<pk>/cancel/  (POST, toggles)
railway:station_list  station_add  station_detail  station_edit  station_delete
railway:platform_list  platform_add  platform_edit  platform_delete
railway:route_station_list  route_station_add  route_station_edit  route_station_delete
notifications:list                /notifications/
notifications:mark_read           /notifications/<pk>/read/        (POST)
notifications:mark_all_read       /notifications/read-all/         (POST)
notifications:delete              /notifications/<pk>/delete/      (POST)
activity_logs:list                /activity/
```

---

## 6. Template contract

### 6.1 Two base templates

* **`templates/base.html`** — the authenticated app shell (sidebar + top header +
  content). Every signed-in page extends it.
* **`templates/base_public.html`** — centred single-card layout with no sidebar, used
  by `accounts/login.html`, `403.html`, `404.html`, `500.html`.
  It must not rely on context processors (the 500 handler renders with an empty
  context), so use only `{% load static %}`/`{% load rc_tags %}` and literal markup.

### 6.2 Blocks provided by `base.html`

| Block | Purpose |
|---|---|
| `title` | overrides the `<title>`; default `{{ page_title }}` |
| `breadcrumb` | contents of the top-bar breadcrumb; default `{{ page_title }}` |
| `page_actions` | buttons rendered on the right of the in-page header |
| `content` | the page body (**required**) |
| `extra_css` | extra `<style>` for a single page (avoid; prefer railcore.css) |
| `extra_js` | extra `<script>` for a single page |

`base.html` itself renders, in order: skip link, icon sprite include, sidebar,
overlay, top header, messages container, `.rc-page__header`
(`{{ page_title }}` + `{{ page_subtitle }}` + `{% block page_actions %}`),
then `{% block content %}`.

### 6.3 Context every authenticated view must provide

```python
{
    "page_title": "Trains",                    # H1 + <title>
    "page_subtitle": "12 trains across 4 routes",   # optional one-liner, may be ""
    "active_nav": "trains",                    # sidebar highlight key
}
```

`active_nav` values: `dashboard`, `trains`, `routes`, `schedules`, `stations`,
`platforms`, `route_stations`, `notifications`, `activity_logs`, `users`, `profile`.

Context processors already supply `nav_sections`, `rc_perms`,
`unread_notification_count` and `header_notifications`.

### 6.4 Template files and their owners

```
templates/base.html                        templates/base_public.html
templates/403.html  404.html  500.html
templates/partials/_sidebar.html           _header.html
templates/partials/_messages.html          _pagination.html
templates/partials/_empty_state.html       _confirm_delete.html
templates/partials/_icons.html  _field.html  _badge.html  _sort_header.html   (DONE)
templates/dashboard/dashboard.html
templates/accounts/login.html  profile.html  password_change.html
templates/accounts/user_list.html  user_form.html  user_detail.html
templates/railway/train_list.html  train_form.html  train_detail.html  train_archive.html
templates/railway/route_list.html  route_form.html  route_detail.html
templates/railway/schedule_list.html  schedule_form.html  schedule_detail.html
templates/railway/station_list.html  station_form.html  station_detail.html
templates/railway/platform_list.html  platform_form.html
templates/railway/route_station_list.html  route_station_form.html
templates/notifications/notification_list.html
templates/activity_logs/activity_log_list.html
```

Delete confirmation is **one shared template**: `templates/partials/_confirm_delete.html`,
rendered directly by every delete view. Its context:

```python
{
    "page_title": "Delete Train",
    "active_nav": "trains",
    "object_type": "Train",                       # human label
    "object_label": "12951 - Mumbai Rajdhani",    # the record being removed
    "object_meta": [("Route", "…"), ("Coaches", "18")],   # list of (label, value)
    "warning": "3 schedules reference this train and will also be removed.",  # or ""
    "soft_delete": True,     # renders the "can be restored" note
    "cancel_url": "/railway/trains/",
    "confirm_label": "Yes, delete train",
}
```

### 6.5 Reusable partials contract

`partials/_pagination.html` expects `page_obj` in context and preserves all other
query parameters using the built-in `{% querystring %}` tag (Django 5.1+):

```html
<a class="rc-pagination__link" href="{% querystring page=page_obj.next_page_number %}">…</a>
```

`partials/_empty_state.html` is included with explicit arguments:

```html
{% include 'partials/_empty_state.html' with icon='train' title='No trains found' text='There are currently no trains available.' action_url=add_url action_label='Add Train' %}
```

(`action_url`/`action_label` optional — omit for read-only screens.)

---

## 7. Design system

### 7.1 Tokens (declared once in `static/css/railcore.css` under `:root`)

```
--rc-navy-900:#0a1f38  --rc-navy-800:#0e2a4a  --rc-navy-700:#14375f
--rc-primary:#1a4f8a   --rc-primary-600:#17497f --rc-primary-700:#143c6b
--rc-primary-100:#e6eef8 --rc-primary-50:#f2f7fc
--rc-accent:#0f8a7e
--rc-success:#1a7f4b --rc-success-bg:#e7f6ed
--rc-warning:#a9620a --rc-warning-bg:#fdf1e0
--rc-danger:#b3261e  --rc-danger-bg:#fdeceb
--rc-info:#1a5fb4    --rc-info-bg:#e8f0fc
--rc-neutral:#4f5a70 --rc-neutral-bg:#eef1f6
--rc-bg:#f5f7fb --rc-surface:#ffffff --rc-surface-2:#fafbfd
--rc-border:#e3e8f0 --rc-border-strong:#cfd7e5
--rc-text:#16233a --rc-text-muted:#5c6980 --rc-text-soft:#8b96ac
--rc-radius-sm:8px --rc-radius:12px --rc-radius-lg:16px --rc-radius-pill:999px
--rc-shadow-xs:0 1px 2px rgba(16,35,63,.06)
--rc-shadow-sm:0 1px 3px rgba(16,35,63,.07),0 1px 2px rgba(16,35,63,.04)
--rc-shadow:0 4px 14px rgba(16,35,63,.08)
--rc-shadow-lg:0 14px 34px rgba(16,35,63,.12)
--rc-sidebar-w:264px --rc-sidebar-collapsed-w:76px --rc-header-h:66px
--rc-transition:160ms cubic-bezier(.4,0,.2,1)
--rc-font: -apple-system, BlinkMacSystemFont, "Segoe UI Variable Text", "Segoe UI",
           Roboto, "Helvetica Neue", Arial, sans-serif
--rc-mono: ui-monospace, SFMono-Regular, "Cascadia Code", Consolas, monospace
```

Visual language: white cards on a very light blue-grey canvas, deep-navy sidebar,
1px hairline borders, `--rc-shadow-sm` at rest and `--rc-shadow` on hover, 12–16px
radii, generous 20–24px card padding, 14px base font, tabular numerals for figures.
No gradients other than an optional very subtle navy one in the sidebar/logo tile.
Transitions only on `background-color`, `border-color`, `box-shadow`, `transform`
(≤200ms). No keyframe animation except the `.rc-alert` slide-in and `.rc-skeleton`.

### 7.2 Complete CSS class contract

Every class below must exist in `railcore.css` and is the only vocabulary templates
may use (plus the `is-*` state classes listed).

**Shell** `.rc-shell` `.rc-overlay` `.rc-main` `.rc-content`
`body.rc-sidebar-collapsed` `body.rc-sidebar-open` (states)

**Sidebar** `.rc-sidebar` `.rc-sidebar__top` `.rc-sidebar__brand` `.rc-sidebar__logo`
`.rc-sidebar__brand-text` `.rc-sidebar__name` `.rc-sidebar__tag` `.rc-sidebar__close`
`.rc-sidebar__nav` `.rc-sidebar__section` `.rc-sidebar__section-title`
`.rc-sidebar__link` (`.is-active`) `.rc-sidebar__link-icon` `.rc-sidebar__link-label`
`.rc-sidebar__count` `.rc-sidebar__footer` `.rc-sidebar__user` `.rc-sidebar__logout`

**Header** `.rc-header` `.rc-header__left` `.rc-header__toggle` `.rc-header__right`
`.rc-breadcrumb` `.rc-breadcrumb__item` `.rc-breadcrumb__sep`
`.rc-header__action` `.rc-header__bell` `.rc-header__bell-count`
`.rc-notif-menu` (`.is-open`) `.rc-notif-menu__head` `.rc-notif-menu__list`
`.rc-notif-menu__item` `.rc-notif-menu__title` `.rc-notif-menu__meta`
`.rc-notif-menu__empty` `.rc-notif-menu__foot`
`.rc-user` `.rc-user__avatar` `.rc-user__meta` `.rc-user__name` `.rc-user__role`

**Page** `.rc-page__header` `.rc-page__heading` `.rc-page__title` `.rc-page__subtitle`
`.rc-page__actions`

**Cards** `.rc-card` (`.rc-card--flush` `.rc-card--form` `.rc-card--accent`)
`.rc-card__header` `.rc-card__titles` `.rc-card__title` `.rc-card__subtitle`
`.rc-card__actions` `.rc-card__body` `.rc-card__footer`

**Layout helpers** `.rc-grid` `.rc-grid--2` `.rc-grid--3` `.rc-grid--4`
`.rc-grid--split` (2fr/1fr) `.rc-stack` `.rc-stack--sm` `.rc-stack--lg`
`.rc-row` `.rc-row--between` `.rc-row--end` `.rc-row--center` `.rc-row--wrap`
`.rc-divider`

**Stat cards** `.rc-stats` `.rc-stat` `.rc-stat__top` `.rc-stat__icon`
(`--primary --success --warning --danger --info --neutral`) `.rc-stat__value`
`.rc-stat__label` `.rc-stat__meta` `.rc-stat__trend` (`--up --down --flat`)

**Buttons** `.rc-btn` (`--primary --secondary --ghost --danger --success --sm --lg --block`)
`.rc-icon-btn` (`--view --edit --delete --restore`) `.rc-actions`

**Tables** `.rc-toolbar` `.rc-toolbar__search` `.rc-toolbar__filters` `.rc-toolbar__meta`
`.rc-search` `.rc-search__icon` `.rc-search__input` `.rc-filter` `.rc-filter__label`
`.rc-table-wrap` `.rc-table` `.rc-th` (`--sortable --left --center --right`)
`.rc-th__sort` (`.is-active`) `.rc-th__icon` `.rc-td` (`--center --right --actions --tight`)
`.rc-cell` `.rc-cell__primary` `.rc-cell__secondary` `.rc-code` `.rc-mono`
`.rc-avatar` (`--sm --lg`) `.rc-chip`

**Badges** `.rc-badge` (`--success --warning --danger --info --neutral --primary`)
`.rc-badge__dot`

**Forms** `.rc-form` `.rc-form__grid` `.rc-form__section` `.rc-form__section-title`
`.rc-form__section-text` `.rc-form__actions` `.rc-form-errors` `.rc-form-errors__item`
`.rc-field` (`.is-invalid` `--wide` `--switch`) `.rc-field__label` `.rc-field__required`
`.rc-field__control` (`--icon`) `.rc-field__icon` `.rc-field__help` `.rc-field__error`
`.rc-input` `.rc-select` `.rc-textarea` `.rc-file`
`.rc-switch` `.rc-switch__track` `.rc-switch__thumb` `.rc-switch__body` `.rc-switch__label`

**Empty state** `.rc-empty` `.rc-empty__icon` `.rc-empty__title` `.rc-empty__text`
`.rc-empty__actions`

**Alerts** `.rc-alerts` `.rc-alert` (`--success --danger --warning --info`)
`.rc-alert__icon` `.rc-alert__body` `.rc-alert__title` `.rc-alert__text` `.rc-alert__close`

**Pagination** `.rc-pagination` `.rc-pagination__info` `.rc-pagination__pages`
`.rc-pagination__link` (`.is-active` `.is-disabled`)

**Detail view** `.rc-detail` `.rc-detail__item` `.rc-detail__label` `.rc-detail__value`
`.rc-timeline` `.rc-timeline__item` `.rc-timeline__marker` `.rc-timeline__body`
`.rc-timeline__title` `.rc-timeline__meta`

**Dashboard panels** `.rc-feed` `.rc-feed__item` `.rc-feed__icon`
(`--success --info --danger --warning --neutral`) `.rc-feed__body` `.rc-feed__text`
`.rc-feed__meta` `.rc-status-list` `.rc-status-item` `.rc-status-item__label`
`.rc-status-item__value` `.rc-status-dot` (`--ok --warn --down`)
`.rc-quick` `.rc-quick__item` `.rc-quick__icon` `.rc-quick__label`

**Charts (CSS/SVG only)** `.rc-chart` `.rc-chart__bars` `.rc-chart__bar`
`.rc-chart__track` `.rc-chart__fill` `.rc-chart__value` `.rc-chart__label`
`.rc-legend` `.rc-legend__item` `.rc-legend__dot` `.rc-donut` `.rc-donut__svg`
`.rc-donut__center` `.rc-donut__value` `.rc-donut__label` `.rc-meter` `.rc-meter__fill`

**Auth / public** `.rc-auth` `.rc-auth__aside` `.rc-auth__aside-inner` `.rc-auth__brand`
`.rc-auth__headline` `.rc-auth__text` `.rc-auth__points` `.rc-auth__point`
`.rc-auth__main` `.rc-auth__card` `.rc-auth__title` `.rc-auth__subtitle`
`.rc-auth__footer` `.rc-auth__demo` `.rc-auth__demo-row`
`.rc-public` `.rc-public__card` `.rc-public__code` `.rc-public__title` `.rc-public__text`
`.rc-public__actions`

**Confirm delete** `.rc-confirm` `.rc-confirm__icon` `.rc-confirm__title`
`.rc-confirm__text` `.rc-confirm__target` `.rc-confirm__meta` `.rc-confirm__note`
`.rc-confirm__actions`

**Profile** `.rc-profile` `.rc-profile__hero` `.rc-profile__avatar` `.rc-profile__id`
`.rc-profile__name` `.rc-profile__role` `.rc-profile__meta`

**Utilities** `.rc-sr-only` `.rc-skip` `.rc-muted` `.rc-strong` `.rc-nowrap`
`.rc-truncate` `.rc-text-right` `.rc-text-center` `.rc-hide-md` `.rc-hide-sm`
`.rc-icon` (`--xs --sm --lg --xl`) `.rc-tabular`

### 7.3 Responsive rules

* `> 1200px` — sidebar 264px fixed, content max-width 1440px, stats 3 across.
* `992–1200px` — stats 2 across, `.rc-grid--split` collapses to one column.
* `768–992px` — sidebar becomes an off-canvas drawer (`body.rc-sidebar-open`),
  hamburger visible, header user meta text hidden (avatar only).
* `< 768px` — single column everywhere, `.rc-toolbar` stacks, `.rc-table-wrap`
  scrolls horizontally, `.rc-form__grid` one column, `.rc-page__actions` full width.

---

## 8. Canonical markup patterns — copy these

### 8.1 List page skeleton

```html
{% extends 'base.html' %}
{% load rc_tags %}

{% block page_actions %}
  {% if rc_perms.trains.manage %}
    <a class="rc-btn rc-btn--primary" href="{% url 'railway:train_add' %}">{% rc_icon "plus" "rc-icon rc-icon--sm" %}<span>Add Train</span></a>
  {% endif %}
{% endblock %}

{% block content %}
<div class="rc-card rc-card--flush">
  <div class="rc-toolbar">
    <form class="rc-toolbar__search" method="get" role="search">
      <div class="rc-search">
        {% rc_icon "search" "rc-icon rc-search__icon" %}
        <label class="rc-sr-only" for="train-search">Search trains</label>
        <input class="rc-search__input" id="train-search" type="search" name="q" value="{{ q }}" placeholder="Search train number or name…">
      </div>
      <div class="rc-toolbar__filters">
        <label class="rc-filter">
          <span class="rc-filter__label">Status</span>
          <select class="rc-select" name="status" data-rc-autosubmit>
            <option value="">All statuses</option>
            {% for value, label in status_options %}
              <option value="{{ value }}" {% if status_filter == value %}selected{% endif %}>{{ label }}</option>
            {% endfor %}
          </select>
        </label>
        <button class="rc-btn rc-btn--secondary rc-btn--sm" type="submit">Apply</button>
        {% if q or status_filter %}<a class="rc-btn rc-btn--ghost rc-btn--sm" href="{% url 'railway:train_list' %}">Clear</a>{% endif %}
      </div>
    </form>
    <p class="rc-toolbar__meta">{{ total_count }} record{{ total_count|pluralize }}</p>
  </div>

  {% if trains %}
  <div class="rc-table-wrap">
    <table class="rc-table">
      <thead>
        <tr>
          {% rc_sort_header 'train_number' 'Train Number' %}
          {% rc_sort_header 'train_name' 'Train Name' %}
          <th scope="col" class="rc-th">Route</th>
          {% rc_sort_header 'total_coaches' 'Coaches' 'center' %}
          {% rc_sort_header 'status' 'Status' %}
          <th scope="col" class="rc-th rc-th--right">Actions</th>
        </tr>
      </thead>
      <tbody>
        {% for train in trains %}
        <tr>
          <td class="rc-td"><span class="rc-code">{{ train.train_number }}</span></td>
          <td class="rc-td">
            <div class="rc-cell">
              <span class="rc-cell__primary">{{ train.train_name }}</span>
              <span class="rc-cell__secondary">{{ train.total_coaches }} coaches</span>
            </div>
          </td>
          <td class="rc-td">…</td>
          <td class="rc-td rc-td--center rc-tabular">{{ train.total_coaches }}</td>
          <td class="rc-td">{% rc_badge train.status %}</td>
          <td class="rc-td rc-td--actions">
            <div class="rc-actions">
              <a class="rc-icon-btn rc-icon-btn--view" href="{% url 'railway:train_detail' train.pk %}" aria-label="View train {{ train.train_number }}">{% rc_icon "eye" %}</a>
              {% if rc_perms.trains.manage %}
                <a class="rc-icon-btn rc-icon-btn--edit" href="{% url 'railway:train_edit' train.pk %}" aria-label="Edit train {{ train.train_number }}">{% rc_icon "edit" %}</a>
                <a class="rc-icon-btn rc-icon-btn--delete" href="{% url 'railway:train_delete' train.pk %}" aria-label="Delete train {{ train.train_number }}">{% rc_icon "trash" %}</a>
              {% endif %}
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% include 'partials/_pagination.html' %}
  {% else %}
  <div class="rc-card__body">
    {% include 'partials/_empty_state.html' with icon='train' title='No trains found' text='There are currently no trains available.' action_url=add_url action_label='Add Train' %}
  </div>
  {% endif %}
</div>
{% endblock %}
```

`{% rc_sort_header %}` takes `(field, label[, align])` — it reads `request` from
context automatically.

### 8.2 Form page skeleton

```html
{% extends 'base.html' %}
{% load rc_tags %}

{% block content %}
<div class="rc-card rc-card--form">
  <div class="rc-card__header">
    <div class="rc-card__titles">
      <h2 class="rc-card__title">{{ form_title }}</h2>
      <p class="rc-card__subtitle">{{ form_description }}</p>
    </div>
  </div>
  <form class="rc-form" method="post" novalidate>
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div class="rc-form-errors" role="alert">
        {% for error in form.non_field_errors %}<p class="rc-form-errors__item">{% rc_icon "alert" "rc-icon rc-icon--sm" %}<span>{{ error }}</span></p>{% endfor %}
      </div>
    {% endif %}
    <div class="rc-card__body">
      <div class="rc-form__grid">
        {% rc_field form.train_number "train" %}
        {% rc_field form.train_name %}
        {% rc_field form.route "route" %}
        {% rc_field form.total_coaches %}
        {% rc_field form.status %}
      </div>
    </div>
    <div class="rc-form__actions">
      <a class="rc-btn rc-btn--ghost" href="{{ cancel_url }}">Cancel</a>
      <button class="rc-btn rc-btn--primary" type="submit">{% rc_icon "save" "rc-icon rc-icon--sm" %}<span>{{ submit_label }}</span></button>
    </div>
  </form>
</div>
{% endblock %}
```

Forms are always `method="post" novalidate` with `{% csrf_token %}`; validation is
server-side. File-upload forms add `enctype="multipart/form-data"`.

### 8.3 Destructive action = POST form

```html
<form method="post" action="{% url 'railway:train_delete' train.pk %}">
  {% csrf_token %}
  <button class="rc-btn rc-btn--danger" type="submit">Yes, delete train</button>
</form>
```

Delete views accept `GET` (render `partials/_confirm_delete.html`) and `POST`
(perform the deletion, add a message, redirect to the list).

---

## 9. View conventions

* Function-based views only. One view per URL. Decorate with `require_view` /
  `require_manage`.
* `render(request, template, context)` — never `HttpResponse` with inline HTML.
* Create/update: `if request.method == "POST"` → validate → save → `log_*` →
  optional `notify_*` → `messages.success` → `redirect(...)`; else render the form.
* Success/error messages are sentence case, mention the record, e.g.
  `messages.success(request, f"Train {train.train_number} was added successfully.")`
  and on invalid submit `messages.error(request, "Please correct the highlighted fields.")`.
* Lists use the helpers in `railway/utils.py`: `apply_search`, `apply_sort`,
  `paginate`, and always `select_related` the FKs shown in the table.
* Sortable fields must be whitelisted; the whitelist has to match the
  `{% rc_sort_header %}` field names used in the template.
* Every list view puts the "add" URL in context as `add_url` for the empty state.

### 9.1 Exact list-view context keys

| View | object list key | filter keys in context |
|---|---|---|
| `train_list` | `trains` | `q`, `status_filter`, `route_filter`, `status_options`, `route_options`, `total_count`, `add_url` |
| `train_archive` | `trains` | `q`, `total_count` |
| `route_list` | `routes` | `q`, `status_filter`, `station_filter`, `station_options`, `total_count`, `add_url` |
| `schedule_list` | `schedules` | `q`, `status_filter`, `train_filter`, `date_filter`, `status_options`, `train_options`, `total_count`, `add_url` |
| `station_list` | `stations` | `q`, `status_filter`, `state_filter`, `state_options`, `total_count`, `add_url` |
| `platform_list` | `platforms` | `q`, `status_filter`, `station_filter`, `station_options`, `total_count`, `add_url` |
| `route_station_list` | `route_stations` | `q`, `route_filter`, `route_options`, `total_count`, `add_url` |
| `user_list` | `users` | `q`, `role_filter`, `status_filter`, `role_options`, `total_count`, `add_url` |
| `activity_log_list` | `logs` | `q`, `action_filter`, `user_filter`, `action_options`, `user_options`, `total_count` |
| `notification_list` | `notifications` | `level_filter`, `read_filter`, `level_options`, `total_count`, `unread_total` |

`status_options` / `role_options` / `*_options` are always a list of `(value, label)`
2-tuples or a queryset of model instances (documented per view in the task brief).
All list views also provide `page_obj`.

---

## 10. Testing conventions

* `accounts/factories.py` and `railway/factories.py` provide the object factories —
  use them, do not re-implement.
* `from accounts.factories import DEFAULT_PASSWORD, create_admin, create_railway_manager,
  create_station_manager, create_operations_staff, create_user, create_role`
* `from railway.factories import create_station, create_platform, create_route,
  create_route_station, create_train, create_schedule`
* Log in with `self.client.login(username="…", password=DEFAULT_PASSWORD)`.
* Use `reverse()` for URLs, `assertRedirects`, `assertContains`, `assertEqual(resp.status_code, 403)`.
* Test files: `accounts/tests.py`, `dashboard/tests.py`, `notifications/tests.py`,
  `activity_logs/tests.py`, and the package `railway/tests/` with
  `__init__.py`, `test_station.py`, `test_platform.py`, `test_route.py`,
  `test_route_station.py`, `test_train.py`, `test_schedule.py`.
* Tests must pass with `python manage.py test` on both MySQL and SQLite, so never
  assume auto-increment id values and always use timezone-aware datetimes
  (`django.utils.timezone.now()` + `datetime.timedelta`).
