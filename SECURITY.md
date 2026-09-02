# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it directly to the repository owner rather than opening a public issue.

## Implemented Security Controls

This project implements the following security mechanisms to protect user data and maintain application integrity:

- **Password Hashing:** Passwords are securely hashed using Werkzeug's security utilities before being stored in the database.
- **OTP Protection:** One-Time Passwords (OTPs) have strict expiration times and attempt limits to prevent brute-force attacks.
- **CSRF Protection:** All state-changing forms and requests require a valid, session-bound CSRF token.
- **Secure Sessions:** User sessions are managed securely. Session cookies are HTTP-only and configured appropriately for production.
- **Institute-Level Authorization:** Institute-owned records are scoped using the logged-in user's institute_code during protected queries and modifications. Records are queried and modified using the logged-in user's institute_code to prevent unauthorized cross-tenant access.
- **Secret Management:** Sensitive configuration details (like database URIs, secret keys, and SMTP credentials) are managed using environment variables and never hardcoded in the repository.
- **Safe Route Methods:** Destructive actions (like deleting records or modifying timetables) enforce HTTP POST requests rather than GET.
- **Error Handling:** Generic error messages are displayed to users, preventing internal application stack traces or database structures from leaking to the frontend.
