# 🚆 RailCore ERP

<p align="center">
  <strong>A modern Railway Enterprise Resource Planning system built with Django.</strong><br>
  Centralized railway operations management with role-based access control, live dashboards, notifications, and a complete audit trail.
</p>

<p align="center">
  <a href="https://github.com/WINSTER000/RailCoreERP"><img src="https://img.shields.io/badge/GitHub-RailCoreERP-181717?logo=github" alt="GitHub"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white" alt="Django">
  <img src="https://img.shields.io/badge/Database-MySQL%20%7C%20PostgreSQL-4479A1?logo=mysql&logoColor=white" alt="Database">
  <img src="https://img.shields.io/badge/Frontend-HTML%20%7C%20CSS%20%7C%20JavaScript-F7DF1E?logo=javascript&logoColor=black" alt="Frontend">
  <img src="https://img.shields.io/badge/Deployment-Render-46E3B7?logo=render&logoColor=black" alt="Render">
</p>

---

## 📌 Overview

**RailCore ERP** is a web-based Railway Enterprise Resource Planning system designed to provide railway staff with a single platform for managing core railway operations.

The system centralizes:

- 🚆 Train management
- 🛤️ Route and route-station management
- 🏢 Station and platform management
- 📅 Train schedules and operational status
- 👥 Staff accounts and role-based permissions
- 🔔 In-app notifications
- 📝 Activity and audit logs
- 📊 Live operations dashboard

The application is built with **Django 5.2**, uses a database-driven architecture, and includes configuration for deployment on **Render**.

---

## ✨ Key Features

### 🔐 Authentication & User Management

- Secure Django authentication
- Custom user model
- Profile management
- Password change
- Admin-only user management
- Soft delete and restore for users
- Login/logout activity tracking

### 🛡️ Role-Based Access Control

RailCore ERP supports four operational roles:

| Role | Purpose |
|---|---|
| **Admin** | Full system access and user management |
| **Railway Manager** | Manages trains, routes and operational data |
| **Station Manager** | Manages stations, platforms and schedules |
| **Operations Staff** | Handles day-to-day operational activities |

Permissions are enforced at the view level, and the interface dynamically hides modules and actions that a user cannot access.

### 🚆 Railway Operations

- Complete train CRUD
- Train status and maintenance tracking
- Route creation and management
- Ordered route halts/stations
- Station management
- Platform management
- Schedule creation and editing
- Schedule cancellation and reinstatement
- Delay tracking
- Platform conflict validation

### 📊 Operations Dashboard

The dashboard provides live operational information including:

- Active stations
- Total and active trains
- Active routes
- Today's schedules
- Cancelled schedules
- Seven-day schedule volume
- Train status breakdown
- Route load ranking
- Punctuality information
- Recent activity
- System status
- Role-aware quick actions

### 🔔 Notifications & Audit Trail

Operationally important events generate notifications, including:

- Schedule cancellations
- Delays
- Train maintenance events
- Station deactivation
- New user accounts

The activity log records important actions with the responsible user, affected object and action description.

### 🎨 Custom Interface

- Custom CSS design system
- Responsive layout
- Collapsible sidebar
- Sticky table headers
- Search and filtering
- Sorting and pagination
- Status badges
- Confirmation pages for destructive actions
- Toast messages
- Accessible form controls
- No Bootstrap, Font Awesome, external fonts or CDN dependencies

---

# 🖥️ Screenshots

## 🔑 Login

<p align="center">
  <img width="1919" height="1075" alt="login" src="https://github.com/user-attachments/assets/63ee6658-ce20-4824-ad8c-cc30922d5d0b" />
</p>

The login interface provides a clean entry point for authenticated railway staff.

---

## 📊 Dashboard

<p align="center">
  <img width="1900" height="1059" alt="dashboard" src="https://github.com/user-attachments/assets/071bf369-d352-4901-9cfa-22d1f1a37ed5" />
</p>

The operations dashboard presents live railway statistics, schedule information, train status, route activity, punctuality data and recent system activity.

---

## 🛤️ Routes

<p align="center">
  <img width="1919" height="1073" alt="routes" src="https://github.com/user-attachments/assets/fa4092d5-d8e2-4639-9b5e-6efb1184bac9" />
</p>

Routes can be searched, filtered, sorted and managed through the railway operations interface.

---

## 📍 Route Stations

<p align="center">
  <img width="1902" height="1078" alt="route-stations" src="https://github.com/user-attachments/assets/68f67b41-c765-4af7-a9d9-f913539c1bd9" />
</p>

Route stations define the ordered halts that make up each railway route.

---

## 📅 Schedules

<p align="center">
  <img width="1905" height="1075" alt="schedules" src="https://github.com/user-attachments/assets/0d7a606d-5899-455d-8e51-29a82256a0b1" />
</p>

Schedules connect trains, routes, stations and platforms to specific operating dates and times.

---

## 🚆 Trains

<p align="center">
  <img width="1903" height="1076" alt="trains" src="https://github.com/user-attachments/assets/c4d87002-b495-4d02-99ab-a60fa22e17de" />
</p>

The train management module provides operational information, status tracking and administrative actions.

---

## 🏗️ Platforms

<p align="center">
  <img width="1905" height="1075" alt="platforms" src="https://github.com/user-attachments/assets/f4a8518e-d60e-428b-bc6d-90a6cd3d48a0" />
</p>

Platforms are managed per station and are used when assigning schedules to railway operations.

---

## 🏢 Stations

<p align="center">
  <img width="1901" height="1075" alt="stations" src="https://github.com/user-attachments/assets/ec692ec5-af27-463d-a706-a8b3bd6d6668" />
</p>

The station module provides centralized management of railway stations and their operational status.

---

## 👥 Users

<p align="center">
  <img width="1904" height="1075" alt="users" src="https://github.com/user-attachments/assets/6bd51cf4-967c-4858-af1d-2b07526fdb21" />
</p>

Administrators can manage staff accounts, roles and account status from the user management module.

---

## 🔔 Notifications

<p align="center">
  <img width="1919" height="1076" alt="notifications" src="https://github.com/user-attachments/assets/daa597f9-ab6a-46c2-8ed5-7f5dee1144e4" />
</p>

The notification inbox keeps staff informed about important operational events.

---

## 📝 Activity Log

<p align="center">
  <img width="1905" height="1074" alt="activity-log" src="https://github.com/user-attachments/assets/07a030bd-b139-4c36-8b0f-f8f99e34c2fa" />
</p>

The activity log provides an audit trail of important system actions and operational changes.

---

# 🧰 Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Framework | Django 5.2 |
| ORM | Django ORM |
| Templates | Django Templates |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Local Database | MySQL 8 / MariaDB 10.6+ |
| Production Database | PostgreSQL |
| Configuration | django-environ, dj-database-url |
| Image Processing | Pillow |
| Production Server | Gunicorn |
| Static Files | WhiteNoise |
| Deployment | Render |

---

# 🗂️ Project Structure

```text
RailCoreERP/
├── accounts/                  # Users, roles, authentication and RBAC
├── activity_logs/             # Audit trail
├── config/                    # Django project configuration
├── dashboard/                 # Operations dashboard
├── notifications/             # In-app notifications
├── railway/                   # Stations, platforms, routes, trains, schedules
├── static/                    # CSS, JavaScript and images
├── templates/                 # Django templates
├── build.sh                   # Render build script
├── Procfile                   # Gunicorn process definition
├── render.yaml                # Render deployment configuration
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable template
└── manage.py                  # Django management entry point
```

---

# 🚀 Installation

## 1. Clone the repository

```bash
git clone https://github.com/WINSTER000/RailCoreERP.git
cd RailCoreERP
```

## 2. Create a virtual environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Configure environment variables

Copy the example environment file:

```bash
cp .env.example .env
```

On Windows, you can also create `.env` manually from `.env.example`.

At minimum, configure your Django `SECRET_KEY` and database settings.

---

# 🗄️ Database Setup

RailCore ERP supports MySQL/MariaDB, PostgreSQL and SQLite.

### MySQL

```sql
CREATE DATABASE railcore CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Example `.env` configuration:

```env
DB_ENGINE=mysql
DB_NAME=railcore
DB_USER=root
DB_PASSWORD=your-password
DB_HOST=127.0.0.1
DB_PORT=3306
```

### PostgreSQL

```env
DB_ENGINE=postgresql
DB_NAME=railcore
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=127.0.0.1
DB_PORT=5432
```

### SQLite

For a quick local setup:

```env
DB_ENGINE=sqlite
```

Then run migrations:

```bash
python manage.py migrate
```

---

# ▶️ Run the Application

Create an administrator:

```bash
python manage.py createsuperuser
```

Start the development server:

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

Django admin:

```text
http://127.0.0.1:8000/admin/
```

---

# 🌱 Sample Data

RailCore ERP includes a seed command for quickly populating a realistic railway dataset:

```bash
python manage.py seed_data
```

The seed command creates sample roles, staff accounts, Indian railway stations, platforms, routes, trains, schedules, notifications and activity history.

To reset the seeded dataset:

```bash
python manage.py seed_data --flush
```

### Demo Accounts

| Username | Role | Password |
|---|---|---|
| `admin` | Admin | `RailCore@1234` |
| `rmanager` | Railway Manager | `RailCore@1234` |
| `rmanager2` | Railway Manager | `RailCore@1234` |
| `smanager` | Station Manager | `RailCore@1234` |
| `smanager2` | Station Manager | `RailCore@1234` |
| `opsstaff` | Operations Staff | `RailCore@1234` |
| `opsstaff2` | Operations Staff | `RailCore@1234` |

> ⚠️ These credentials are intended for development/demo data. Change them or avoid running the seed command on a publicly accessible deployment.

---

# 🛡️ Role & Permission Matrix

| Module | Admin | Railway Manager | Station Manager | Operations Staff |
|---|---|---|---|---|
| Dashboard | Full | View | View | View |
| Trains | Full | Full | — | View |
| Routes | Full | Full | — | View |
| Schedules | Full | Full | View | Full |
| Stations | Full | View | Full | View |
| Platforms | Full | View | Full | View |
| Route Stations | Full | View | Full | View |
| Activity Log | View | View | — | — |
| User Management | Full | — | — | — |
| Notifications / Profile | Full | Full | Full | Full |

**Full** = create, edit and delete  
**View** = read-only access  
**—** = module hidden and protected from direct access

---

# 🧪 Testing

Run the complete test suite:

```bash
python manage.py test
```

Useful checks:

```bash
python manage.py check
```

Run a specific test module:

```bash
python manage.py test railway.tests.test_schedule
```

---

# ☁️ Deployment on Render

The repository includes Render deployment configuration through `render.yaml` and `build.sh`.

### Blueprint deployment

1. Push the project to GitHub.
2. Open Render.
3. Choose **New → Blueprint**.
4. Select the `RailCoreERP` repository.
5. Render provisions the web service and PostgreSQL database from the blueprint.
6. The build process installs dependencies, collects static files and applies migrations.
7. Gunicorn starts the Django application.

### Manual deployment

**Build command:**

```bash
./build.sh
```

**Start command:**

```bash
gunicorn config.wsgi:application
```

Typical production environment variables:

```env
SECRET_KEY=your-production-secret
DEBUG=False
DATABASE_URL=your-render-postgresql-url
PYTHON_VERSION=3.12.6
```

> ⚠️ Do not commit real passwords, secret keys or production database credentials to GitHub.

---

# 📍 Important URLs

| URL | Purpose |
|---|---|
| `/` | Dashboard redirect |
| `/accounts/login/` | Login |
| `/accounts/profile/` | User profile |
| `/accounts/users/` | User management |
| `/dashboard/` | Operations dashboard |
| `/railway/trains/` | Train management |
| `/railway/routes/` | Route management |
| `/railway/schedules/` | Schedule management |
| `/railway/stations/` | Station management |
| `/railway/platforms/` | Platform management |
| `/railway/route-stations/` | Route-station management |
| `/notifications/` | Notification inbox |
| `/activity/` | Activity log |
| `/admin/` | Django administration |

---

# 🔒 Security Highlights

- Django password hashing
- Session-based authentication
- Role-based authorization
- CSRF protection
- Secure cookies in production
- HTTPS redirect in production
- HSTS support
- `X-Frame-Options: DENY`
- Content sniffing protection
- Environment-based secret management
- Database-level and form-level validation

---

# 📈 Validation & Data Integrity

RailCore ERP validates important railway constraints such as:

- Unique train numbers
- Unique station codes
- Unique route names
- Unique platform numbers within a station
- Unique halt sequence numbers within a route
- Positive coach counts
- Non-negative route distance
- Valid arrival/departure ordering
- Prevention of overlapping platform schedules
- Valid route halt timing offsets

---

# 🗺️ Roadmap

- [x] Authentication and user management
- [x] Role-based access control
- [x] Railway master data management
- [x] Train and schedule management
- [x] Dashboard analytics
- [x] Notifications
- [x] Activity/audit logging
- [x] Database validation
- [x] Render deployment configuration
- [ ] Advanced reporting
- [ ] Additional operational analytics
- [ ] Production object storage for uploaded media

---

# 🤝 Contributing

Contributions, suggestions and improvements are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Run the test suite.
5. Commit your changes.
6. Open a pull request.

---

# 📄 License

Built as an academic project and intended for learning, demonstration and further development.

---

## 👨‍💻 Project

**RailCore ERP** — Railway Enterprise Resource Planning System

**Repository:** https://github.com/WINSTER000/RailCoreERP
