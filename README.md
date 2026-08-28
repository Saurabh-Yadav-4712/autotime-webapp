<div align="center">
  <img src="static/favicon.svg" alt="AutoTime logo" width="88" height="88">

  # AutoTime

  **Secure, constraint-aware academic timetable management for institutes.**

  [![Live App](https://img.shields.io/badge/Live_App-Vercel-000000?logo=vercel)](https://autotime-webapp.vercel.app)
  [![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
  [![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask)](https://flask.palletsprojects.com/)
  [![CI](https://github.com/Saurabh-Yadav-4712/autotime-webapp/actions/workflows/ci.yml/badge.svg)](https://github.com/Saurabh-Yadav-4712/autotime-webapp/actions/workflows/ci.yml)

  [Open live application](https://autotime-webapp.vercel.app) ·
  [Engineering audit](docs/engineering-audit.md) ·
  [Security policy](SECURITY.md)
</div>

## Overview

AutoTime is a multi-tenant web application that helps educational institutes
create, manage, and publish conflict-free academic timetables. It combines an
automated scheduling engine with manual controls, teacher availability, academic
calendars, leave management, proxy allocation, and dedicated portals for every
role.

| Role | Main capabilities |
| --- | --- |
| Administrator | Configure institute timings, courses, subjects, teachers and calendars; generate/edit timetables; approve leave; export schedules |
| Teacher | Activate an invited account, view personal schedules, request/cancel leave, track notifications and syllabus progress |
| Student | Register against an institute/class and view the effective timetable, including date-specific proxy changes |

## Key features

- Constraint-aware timetable generation with collision and availability checks
- Multi-period practical sessions and shared-class subject support
- Manual timetable slot editing with server-side conflict validation
- Automatic proxy-teacher allocation for approved leave
- Role-based authentication with email OTP verification and password recovery
- Institute-level tenant isolation for records and mutations
- Academic calendar, notifications, generation history, and Excel export
- Responsive light/dark interface with Turbo-powered navigation
- PostgreSQL production support and SQLite-based local development

## Architecture

```text
Browser / Turbo UI
        │
        ▼
Flask routes ── authentication, authorization, validation, CSRF
        │
        ├── Scheduler engine ── feasibility, scoring, diagnostics
        ├── Leave service ───── proxy allocation and notifications
        └── SQLAlchemy ORM ──── tenant-scoped persistence
                                │
                                ▼
                         PostgreSQL / SQLite
```

The repository is organized by responsibility:

```text
routes/       HTTP endpoints for admin, teacher, student and authentication flows
utils/        Security, scheduling, timetable, email and leave-domain services
templates/    Server-rendered Jinja templates and reusable components
static/       Styles, JavaScript and visual assets
models.py     SQLAlchemy models, constraints and indexes
migrations/   Explicit migrations for existing databases
tests/        Security, tenant-isolation, scheduler and regression tests
```

## Technology stack

- **Backend:** Python, Flask, Flask-SQLAlchemy, Werkzeug
- **Database:** PostgreSQL in production; SQLite for development and tests
- **Frontend:** Jinja, HTML5, Bootstrap, vanilla JavaScript, Hotwired Turbo
- **Documents:** openpyxl for Excel exports/imports
- **Delivery:** Vercel with GitHub integration
- **Quality:** Pytest, Ruff, pip-audit, GitHub Actions, Dependabot

## Local development

### Prerequisites

- Python 3.11 or newer
- Git
- PostgreSQL for a production-like setup, or SQLite for quick local development
- SMTP credentials when testing OTP email delivery

### Installation

```bash
git clone https://github.com/Saurabh-Yadav-4712/autotime-webapp.git
cd autotime-webapp
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Generate a secret key and configure the environment using `.env.example` as the
reference. Never commit real credentials.

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

| Variable | Required | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | Yes | Signs sessions and security tokens; use a long random value |
| `DATABASE_URL` | Production | PostgreSQL connection URL; SQLite is the local default |
| `SMTP_EMAIL` | OTP email | Sender account used for verification emails |
| `SMTP_PASSWORD` | OTP email | Application-specific SMTP credential |
| `SESSION_COOKIE_SECURE` | Production | Keep `true` so cookies are sent only over HTTPS |
| `AUTO_CREATE_SCHEMA` | Local only | Set `true` only when creating a new local SQLite database |
| `FLASK_DEBUG` | No | Keep `false` outside local development |

Run a new local SQLite instance:

```powershell
$env:SECRET_KEY = "your-generated-secret"
$env:AUTO_CREATE_SCHEMA = "true"
python app.py
```

Open `http://127.0.0.1:5000`.

## Quality checks

The following checks match the GitHub Actions workflow:

```bash
python -m compileall -q app.py models.py routes utils migrations
python -m ruff check .
python -m pytest
python -m pip_audit -r requirements.txt
```

The current suite covers authentication, CSRF, cross-tenant authorization,
leave/proxy transactions, database migration integrity, scheduler regressions,
gap semantics, weekly balance, and UI rendering.

## Database migrations

`db.create_all()` is used only for a new local database. Production should keep
`AUTO_CREATE_SCHEMA=false` and apply schema changes as a controlled release
step.

For an existing deployment:

1. Back up the production database and verify that the backup can be restored.
2. Test the migration against a staging copy.
3. Set the production environment variables.
4. Run the migrations in `migrations/` in order, ending with:

   ```bash
   python migrations/production_hardening.py
   ```

The hardening migration checks duplicate legacy identifiers before adding
tenant uniqueness guarantees and performance indexes. It aborts without applying
changes when conflicting data is detected.

## Deployment

The repository is connected to Vercel. A push to `main` triggers the production
deployment at [autotime-webapp.vercel.app](https://autotime-webapp.vercel.app).

Before deployment, confirm that Vercel contains `SECRET_KEY`, `DATABASE_URL`,
`SMTP_EMAIL`, and `SMTP_PASSWORD`. Keep `SESSION_COOKIE_SECURE=true`,
`AUTO_CREATE_SCHEMA=false`, and `FLASK_DEBUG=false`.

## Security

AutoTime enforces CSRF protection, secure session cookies, password hashing,
keyed OTP digests with expiry and attempt limits, tenant-scoped authorization,
safe upload limits, security headers, and POST-only destructive operations.

Deployment-level controls such as rate limiting, monitoring, restricted database
credentials, backups, and incident response remain the operator's responsibility.
Read [SECURITY.md](SECURITY.md) before exposing the service publicly.

## Documentation

- [Engineering audit and remaining production work](docs/engineering-audit.md)
- [Security policy and deployment boundaries](SECURITY.md)
- [Environment variable template](.env.example)

## License

Proprietary. All rights reserved.
