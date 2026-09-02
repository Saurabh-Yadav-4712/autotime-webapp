# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Report it privately to
the project owner with the affected route, reproduction steps, expected impact,
and any relevant logs with credentials and personal data removed.

## Implemented controls

- Unsafe browser requests require a session-bound CSRF token.
- Successful authentication rotates and minimizes session state.
- Session cookies are HTTP-only, SameSite=Lax, and secure in production.
- Passwords use Werkzeug's adaptive password hashing; OTPs are stored as keyed
  digests and have expiry and attempt limits.
- Tenant-owned records are selected by both identifier and institute code.
- Uploads are size- and type-limited and parsing errors do not expose internals.
- Security headers deny framing, MIME sniffing, unnecessary browser features,
  and insecure transport downgrade on HTTPS.
- Destructive actions use POST rather than mutation-capable GET routes.
- Pinned dependencies are audited in CI and updated by Dependabot.

## Production boundaries

The application is substantially hardened, but deployment security also depends
on its environment. Before exposing it publicly:

- Add IP/account rate limiting for login, registration, OTP, and password-reset
  endpoints at the reverse proxy or edge.
- Move OTP and pending-registration state to a server-side, expiring store when
  deploying across multiple processes or regions.
- Configure centralized structured logs, error monitoring, uptime checks, and
  alerts without recording passwords, OTPs, or SMTP credentials.
- Use a restricted database role, encrypted connections, automated backups, and
  regular restore tests. Supabase Row Level Security protects its public APIs;
  it is not a substitute for authorization in an application using a direct
  privileged database connection.
- Replace or self-host third-party browser assets if the deployment requires a
  strict Content Security Policy and supply-chain isolation.
- Run concurrency, load, accessibility, and disaster-recovery testing with a
  production-sized anonymized dataset.

Supported releases receive dependency and security fixes through the repository's
CI and dependency-update workflow.
