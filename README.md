# RailCore ERP

A Railway Enterprise Resource Planning system built with Django 5.2. RailCore ERP gives
railway staff a single console for managing the network — stations and platforms, routes
and their halts, trains and their daily schedules — with role-based access control, an
audit trail of every change, and an operations dashboard driven entirely by live data.

---

## Table of contents

1. [Overview](#overview)
2. [Features](#features)
3. [Technology stack](#technology-stack)
4. [Project structure](#project-structure)
5. [Installation](#installation)
6. [Environment variables](#environment-variables)
7. [Database setup](#database-setup)
8. [Running the application](#running-the-application)
9. [Sample data and demo accounts](#sample-data-and-demo-accounts)
10. [Roles and permissions](#roles-and-permissions)
11. [Application URLs](#application-urls)
12. [Running the tests](#running-the-tests)
13. [Deploying to Render](#deploying-to-render)
14. [Command reference](#command-reference)

---

## Overview

RailCore ERP models the core operational data of a railway network and the workflows
around it:

* **Network** — stations, the platforms at each station, and the routes that connect
  them, including the ordered list of halts (route stations) that make up each route
  with arrival and departure offsets from the origin.
* **Operations** — trains assigned to routes, and the schedules that place a train on a
  specific platform at a specific date and time, with delay tracking and cancellation.
* **Governance** — four staff roles with distinct capabilities, a full activity log of
  every create/update/delete/login/logout, and in-app notifications when something
  operationally significant happens.

Everything on screen is read from the database. There are no hardcoded figures, no
placeholder pages and no stubbed features.

---

## Features

**Authentication and accounts**

* Session-based login and logout with Django's password hashing (PBKDF2).
* Custom user model with role, phone number and profile photo.
* Self-service profile editing and password change.
* Admin-only user management with soft delete and restore.
* Login/logout are recorded in the activity log automatically via signals.

**Role-based access control**

* Four roles — Admin, Railway Manager, Station Manager, Operations Staff.
* Per-module view/manage capabilities enforced by decorators on every view.
* The sidebar only shows modules the signed-in user may open, and action buttons are
  hidden when the user lacks write access.
* Unauthorised access renders a styled 403 page explaining the restriction.

**Master data management (full CRUD on all six entities)**

| Module | Create | Read | List | Update | Delete |
|---|---|---|---|---|---|
| Trains | ✓ | ✓ | ✓ | ✓ | soft delete + archive/restore |
| Routes | ✓ | ✓ | ✓ | ✓ | ✓ |
| Schedules | ✓ | ✓ | ✓ | ✓ | ✓ (plus cancel/reinstate) |
| Stations | ✓ | ✓ | ✓ | ✓ | ✓ |
| Platforms | ✓ | — | ✓ | ✓ | ✓ |
| Route stations | ✓ | — | ✓ | ✓ | ✓ |

Every list view supports search, filtering, column sorting and pagination. Every
destructive action goes through a confirmation page — nothing is ever deleted on a
`GET` request. Records protected by foreign keys report a clear message instead of
raising an error.

**Validation**

* Unique train number, unique station code, unique route name.
* Platform numbers unique within a station.
* Halt sequence numbers unique within a route, and a station cannot appear twice on
  the same route.
* Positive coach counts (1–30), non-negative route distance.
* Arrival must be after departure; a platform cannot be double-booked by two
  overlapping schedules; departure offset cannot precede arrival offset at a halt.
* Enforced at both the database level (unique constraints) and the form level, so
  duplicates surface as readable field errors.

**Operations dashboard**

* Six live statistic cards — active stations, total trains, active trains, active
  routes, today's schedules and cancelled schedules.
* A seven-day schedule volume chart, a train status breakdown, route load ranking and a
  punctuality summary, all computed with ORM aggregates and rendered as CSS/SVG (no
  charting library, no external requests).
* Recent activity feed, real system status rows, and quick actions filtered by role.

**Activity log and notifications**

* Every create, update and delete writes an `ActivityLog` row with the actor, model,
  object id and a human description.
* Notifications are raised for schedule cancellations, delays, trains entering
  maintenance, stations being deactivated and new accounts; the unread count appears in
  the header and sidebar, with a dedicated inbox page.

**Interface**

* Custom design system — a single stylesheet, a single script, and an inline SVG icon
  sprite. No Bootstrap, no Font Awesome, no CDN, no web fonts: the app renders
  identically offline and on a fresh server.
* Collapsible sidebar, sticky table headers, status badges that always carry a text
  label, empty states on every module, toast-style messages.
* Responsive from desktop down to mobile; the sidebar becomes an off-canvas drawer
  below 992px.
* Accessible: labelled inputs, `aria-label` on icon-only controls, visible focus rings,
  semantic tables, and `prefers-reduced-motion` support.

---

## Technology stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Framework | Django 5.2 (Django ORM, Django Templates, ModelForms) |
| Database | MySQL 8 / MariaDB 10.6+ locally, PostgreSQL on Render |
| Frontend | HTML5, CSS3 (custom design system), vanilla JavaScript |
| Settings | django-environ, dj-database-url |
| Images | Pillow |
| Production | Gunicorn, WhiteNoise |
| Hosting | Render |

---

## Project structure

```
RailCoreERP/
├── config/                     Project configuration
│   ├── settings.py             Env-driven settings (dev + production)
│   ├── urls.py                 Root URL configuration
│   ├── wsgi.py  asgi.py
├── accounts/                   Users, roles, authentication, RBAC
│   ├── models.py               Role, User (AbstractUser)
│   ├── permissions.py          Module capability matrix + view decorators
│   ├── context_processors.py   Sidebar navigation + permission map
│   ├── signals.py              Login/logout activity logging
│   ├── forms.py  views.py  urls.py  admin.py  factories.py  tests.py
├── dashboard/                  Aggregated operations dashboard
│   └── views.py  urls.py  tests.py
├── railway/                    Core railway domain
│   ├── models.py               Station, Platform, Route, RouteStation, Train, Schedule
│   ├── forms.py                ModelForms with validation
│   ├── views.py                CRUD for all six entities
│   ├── utils.py                Search, sort and pagination helpers
│   ├── templatetags/rc_tags.py Icons, badges, fields, sortable headers
│   ├── management/commands/seed_data.py
│   ├── tests/                  Per-entity test modules
│   └── urls.py  admin.py  factories.py
├── notifications/              In-app notifications
│   ├── models.py  services.py  context_processors.py  views.py  urls.py  admin.py
├── activity_logs/              Audit trail
│   ├── models.py  services.py  views.py  urls.py  admin.py
├── templates/                  All templates (project-level)
│   ├── base.html               Authenticated app shell
│   ├── base_public.html        Login and error page shell
│   ├── 403.html  404.html  500.html
│   ├── partials/               Sidebar, header, messages, pagination, fields, icons
│   ├── accounts/  dashboard/  railway/  notifications/  activity_logs/
├── static/
│   ├── css/railcore.css        The complete design system
│   ├── js/railcore.js          Sidebar, dropdowns, alerts, filters
│   └── images/
├── media/                      Uploaded profile photos (git-ignored)
├── build.sh                    Render build script
├── Procfile                    Gunicorn process definition
├── render.yaml                 Render blueprint (web service + PostgreSQL)
├── requirements.txt
├── .env.example                Template for local environment variables
└── manage.py
```

---

## Installation

### 1. Clone and enter the project

```bash
git clone <your-repository-url>
cd RailCoreERP
```

### 2. Create and activate a virtual environment

Windows (PowerShell or Git Bash):

```bash
python -m venv venv
venv/Scripts/activate
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> On Linux, `mysqlclient` is skipped by default because it must be compiled against the
> MySQL client headers. If you want to use MySQL locally on Linux, run
> `sudo apt install default-libmysqlclient-dev pkg-config` and then
> `pip install mysqlclient==2.2.8`. Alternatively set `DB_ENGINE=sqlite`.

### 4. Create your environment file

```bash
cp .env.example .env
```

Then edit `.env` and set at minimum a `SECRET_KEY` and your database credentials.

---

## Environment variables

`.env` is read by `django-environ` and is git-ignored — it must never be committed.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SECRET_KEY` | yes in production | dev fallback when `DEBUG=True` | Django cryptographic signing key |
| `DEBUG` | no | `False` | Enables debug mode. Must be `False` in production |
| `ALLOWED_HOSTS` | no | `localhost,127.0.0.1,[::1],testserver` | Comma-separated allowed hostnames |
| `TIME_ZONE` | no | `Asia/Kolkata` | Application timezone |
| `LOG_LEVEL` | no | `INFO` | Console logging level |
| `RAILCORE_PAGE_SIZE` | no | `10` | Rows per page in every list view |
| `DB_ENGINE` | no | `mysql` | `mysql`, `postgresql` or `sqlite` |
| `DB_NAME` | no | `railcore` | Database name |
| `DB_USER` | no | `root` | Database user |
| `DB_PASSWORD` | no | empty | Database password |
| `DB_HOST` | no | `127.0.0.1` | Database host |
| `DB_PORT` | no | `3306` | Database port |
| `DATABASE_URL` | no | — | Full connection URL. **Overrides every `DB_*` variable**; this is what Render supplies |
| `SECURE_SSL_REDIRECT` | no | `True` when `DEBUG=False` | Force HTTPS |
| `CSRF_TRUSTED_ORIGINS` | no | — | Extra trusted origins for CSRF |

Production hardening (secure cookies, HSTS, SSL redirect, `X-Frame-Options: DENY`,
no-sniff headers) switches on automatically whenever `DEBUG=False`. No credentials or
secret keys are stored in the repository.

---

## Database setup

### MySQL / MariaDB (default for local development)

```bash
mysql -u root -p -e "CREATE DATABASE railcore CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

Set the matching values in `.env`:

```
DB_ENGINE=mysql
DB_NAME=railcore
DB_USER=root
DB_PASSWORD=your-password
DB_HOST=127.0.0.1
DB_PORT=3306
```

### PostgreSQL

```
DB_ENGINE=postgresql
DB_NAME=railcore
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=127.0.0.1
DB_PORT=5432
```

### SQLite (zero setup, useful for a quick look or for running the tests)

```
DB_ENGINE=sqlite
```

### Apply the migrations

```bash
python manage.py migrate
```

---

## Running the application

```bash
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000/> — you will be redirected to the login page. The Django
admin is available at <http://127.0.0.1:8000/admin/>.

To load the sample dataset instead of starting from an empty database, see the next
section.

---

## Sample data and demo accounts

```bash
python manage.py seed_data
```

This creates the four roles, seven demo staff accounts, fifteen real Indian stations
(fourteen active) with their platforms, seven routes (six active) with ordered halts,
fourteen trains (one archived), and forty-five schedules spread across the past two days,
today and the next two days, plus a notification inbox and activity history — so every
screen and every dashboard figure has meaningful data.

The command is idempotent: running it again updates the existing records rather than
creating duplicates. To wipe the seeded data and start over:

```bash
python manage.py seed_data --flush
```

The exact credentials are printed at the end of the run. The accounts created are:

| Username | Name | Role | Password |
|---|---|---|---|
| `admin` | Winster Lobo | Admin (superuser) | `RailCore@1234` |
| `rmanager` | Arman Ali | Railway Manager | `RailCore@1234` |
| `rmanager2` | Owais Khatri | Railway Manager | `RailCore@1234` |
| `smanager` | Sameera Dream | Station Manager | `RailCore@1234` |
| `smanager2` | Maya Dream | Station Manager | `RailCore@1234` |
| `opsstaff` | Meera DY | Operations Staff | `RailCore@1234` |
| `opsstaff2` | Jace Dream | Operations Staff | `RailCore@1234` |

Sign in as each one to see how the sidebar, action buttons and permissions change.

> These are development credentials for the sample dataset. Change them, or avoid
> running `seed_data` at all, on any deployment that is publicly reachable.

---

## Roles and permissions

| Module | Admin | Railway Manager | Station Manager | Operations Staff |
|---|---|---|---|---|
| Dashboard | full | view | view | view |
| Trains | full | full | — | view |
| Routes | full | full | — | view |
| Schedules | full | full | view | full |
| Stations | full | view | full | view |
| Platforms | full | view | full | view |
| Route stations | full | view | full | view |
| Activity log | view | view | — | — |
| User management | full | — | — | — |
| Notifications / Profile | full | full | full | full |

"full" means create, edit and delete; "view" means read-only; "—" means the module is
hidden from the sidebar and returns a 403 page if accessed directly.

---

## Application URLs

| URL | Purpose |
|---|---|
| `/` | Redirects to the dashboard |
| `/accounts/login/` | Sign in |
| `/accounts/logout/` | Sign out (POST) |
| `/accounts/profile/` | Own profile and recent activity |
| `/accounts/profile/password/` | Change password |
| `/accounts/users/` | User management (Admin only) |
| `/dashboard/` | Operations dashboard |
| `/railway/trains/` | Train list |
| `/railway/trains/add/` | Add train |
| `/railway/trains/<id>/` | Train details |
| `/railway/trains/<id>/edit/` | Edit train |
| `/railway/trains/<id>/delete/` | Delete train (confirmation) |
| `/railway/trains/archive/` | Soft-deleted trains, with restore |
| `/railway/routes/` | Route list (`add/`, `<id>/`, `<id>/edit/`, `<id>/delete/`) |
| `/railway/schedules/` | Schedule list (`add/`, `<id>/`, `<id>/edit/`, `<id>/delete/`, `<id>/cancel/`) |
| `/railway/stations/` | Station list (`add/`, `<id>/`, `<id>/edit/`, `<id>/delete/`) |
| `/railway/platforms/` | Platform list (`add/`, `<id>/edit/`, `<id>/delete/`) |
| `/railway/route-stations/` | Route station list (`add/`, `<id>/edit/`, `<id>/delete/`) |
| `/notifications/` | Notification inbox |
| `/activity/` | Activity log (Admin and Railway Manager) |
| `/admin/` | Django administration |

---

## Running the tests

```bash
python manage.py test
```

The suite covers authentication, role authorisation (including the 403 responses), CRUD
for all six entities, every validation rule, soft delete and restore, duplicate
prevention, schedule date/time and platform-clash validation, cancellation,
dashboard statistics and activity log generation.

Run a single module or class:

```bash
python manage.py test railway.tests.test_schedule
python manage.py test accounts.tests.LoginViewTests
```

The tests run against whichever database `.env` points at, and pass on MySQL,
PostgreSQL and SQLite. For the fastest run, use `DB_ENGINE=sqlite`.

---

## Deploying to Render

### Option A — Blueprint (recommended)

The repository contains `render.yaml`, which defines the web service and a managed
PostgreSQL database together.

1. Push the repository to GitHub.
2. In Render, choose **New → Blueprint** and select the repository.
3. Render creates `railcore-db` and `railcore-erp`, generates a `SECRET_KEY`, wires
   `DATABASE_URL` to the database, and sets `DEBUG=False`.
4. Apply the blueprint. The build runs `build.sh`, which installs dependencies,
   collects static files and applies migrations. The service then starts with
   `gunicorn config.wsgi:application`.

### Option B — Manual web service

1. **New → Web Service**, connect the repository, choose the Python runtime.
2. Build command: `./build.sh`
3. Start command: `gunicorn config.wsgi:application`
4. Add these environment variables:

   | Key | Value |
   |---|---|
   | `SECRET_KEY` | a long random string |
   | `DEBUG` | `False` |
   | `DATABASE_URL` | the internal connection string of a Render PostgreSQL instance |
   | `PYTHON_VERSION` | `3.12.6` |

5. Deploy, then open a shell on the service and create your first administrator:

   ```bash
   python manage.py createsuperuser
   ```

### How the deployment is configured

* `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` pick up `RENDER_EXTERNAL_HOSTNAME`
  automatically, so no host configuration is required.
* Static files are served by WhiteNoise with compression and content hashing.
* With `DEBUG=False`, Django enforces HTTPS redirects, secure and HTTP-only cookies,
  HSTS, `X-Frame-Options: DENY` and no-sniff headers.
* `DATABASE_URL` takes priority over the `DB_*` variables, and SSL is required for
  PostgreSQL connections in production.

> **Uploaded files on the free plan.** Render's free instances have an ephemeral
> filesystem, so profile photos uploaded to `media/` are lost on redeploy. Attach a
> persistent disk (paid plan) or an object storage backend if you need them to survive.

---

## Command reference

```bash
# Environment
python -m venv venv
venv/Scripts/activate            # Windows
source venv/bin/activate         # macOS / Linux
pip install -r requirements.txt

# Database
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data
python manage.py seed_data --flush

# Development
python manage.py runserver
python manage.py check
python manage.py test

# Production
python manage.py collectstatic --no-input
gunicorn config.wsgi:application
```

---

## License

Built as an academic project. Use and adapt it freely for learning purposes.
