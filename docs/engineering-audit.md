# Engineering audit

Date: 28 August 2026

## Scope

This review covered application configuration, authentication and recovery,
authorization boundaries, request integrity, input and upload validation,
database constraints and query patterns, scheduler and proxy-allocation hot
paths, error handling, browser behaviour, dependency health, automated tests,
deployment configuration, and maintainability.

## Remediated findings

| Severity | Finding | Resolution |
| --- | --- | --- |
| Critical | Record IDs could be used without consistently proving institute ownership. | Admin and teacher mutations now scope lookups by the authenticated institute and, where required, teacher identity. Regression tests cover cross-tenant access. |
| High | State-changing requests lacked CSRF enforcement and some destructive actions accepted GET. | Added session-bound CSRF validation for all unsafe methods; logout and deletion now use POST. |
| High | Registration state contained a plaintext password and OTP values were readable in the signed client session. | Pending passwords are hashed immediately; OTP values are stored as keyed digests with expiry and attempt limits. |
| High | The production secret could fall back to an unsafe value and debug/schema creation were startup behaviours. | Startup now fails closed without `SECRET_KEY`; debug is opt-in and production schema creation is disabled by default. |
| High | Locked Flask and Werkzeug releases had known security advisories; the psycopg and SQLAlchemy pins were incompatible with Python 3.13. | Upgraded and re-audited all affected packages; CI tests Python 3.11 and 3.13. |
| Medium | Profile, password-reset, leave, and timetable flows had incomplete validation or missing recovery behaviour. | Added normalized email/password validation, complete password recovery, ownership checks, transaction rollbacks, and safer user messages. |
| Medium | Upload parsing accepted weak inputs and could expose internal exception details. | Added a 5 MB request limit, strict extensions/types, read-only workbook parsing, defensive CSV decoding, and generic errors. |
| Medium | Existing databases would not receive new model constraints automatically. | Added an idempotent hardening migration with duplicate preflight and tenant-aware indexes. |
| Medium | Slot APIs, leave proxy selection, schedule grouping, trimming, and scheduler scoring performed repeated scans or queries. | Replaced repeated scans with maps/sets and batch queries, reducing the affected paths from nested-query or repeated-linear behaviour to single-pass lookups where practical. |
| Low | Turbo used an unstable CDN import, footer rendering broke Turbo navigation, and a referenced teacher template did not exist. | Pinned the browser module, made the year server-rendered, and routed the teacher portal through the maintained dashboard template. |
| Low | Naming, imports, line wrapping, comments, and development instructions were inconsistent. | Applied deterministic formatting, removed misleading comments, added focused lint rules, and rewrote the operational documentation. |

## Verification evidence

- Python compilation completed without errors.
- Ruff runtime-error rules completed without findings.
- 28 automated tests passed on Python 3.13 with the exact upgraded dependency set.
- The dependency audit reported no known vulnerabilities.
- Browser checks covered landing, navigation, login submission and validation,
  forgot-password rendering, CSRF presence, Turbo navigation, console errors, and
  the absence of framework error overlays.
- `git diff --check` reported no whitespace errors.

## Remaining production work

These items depend on the hosting environment or require architectural choices,
so they should be tracked before a high-traffic public launch:

1. Add edge-level IP/account rate limiting for authentication and OTP endpoints.
2. Adopt Alembic or an equivalent versioned migration runner for future schema
   evolution; run the included hardening migration against a backed-up staging
   copy before production.
3. Store sessions, OTPs, and pending registration records in a shared expiring
   server-side store for multi-region or multi-process deployment.
4. Replace comma-separated legacy relationships and name-based timetable fields
   with normalized foreign-key relationships after a controlled data migration.
5. Add structured log aggregation, error tracking, metrics, alerting, database
   backup/restore drills, and a documented incident response process.
6. Run production-sized load and concurrency tests, full accessibility testing,
   and SMTP failure/retry testing in staging.
7. Introduce a strict Content Security Policy after self-hosting or integrity-
   pinning the remaining third-party frontend assets.

This review substantially raises the engineering baseline, but it is not a claim
that any software is defect-free. The CI, audit, migration, and operational
controls are intended to keep the baseline enforceable as the project evolves.
