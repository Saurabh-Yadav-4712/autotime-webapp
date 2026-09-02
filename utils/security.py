"""Application security helpers.

This module intentionally has no third-party dependencies so the same controls
work in local development and the serverless deployment.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import timedelta

from flask import abort, request, session


UNSAFE_HTTP_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def generate_csrf_token() -> str:
    """Return the session's CSRF token, creating it when necessary."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def configure_security(app) -> None:
    """Register request validation and defensive response headers."""
    app.config.setdefault("WTF_CSRF_ENABLED", True)
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(hours=8))

    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def validate_csrf_token():
        if request.method not in UNSAFE_HTTP_METHODS or not app.config.get(
            "WTF_CSRF_ENABLED", True
        ):
            return None

        submitted_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        expected_token = session.get("_csrf_token")
        if (
            not submitted_token
            or not expected_token
            or not hmac.compare_digest(submitted_token, expected_token)
        ):
            abort(400, description="Invalid or missing CSRF token.")
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


def begin_authenticated_session(**identity) -> None:
    """Drop pre-authentication state and establish one unambiguous identity."""
    session.clear()
    session.permanent = True
    session.update(identity)
    generate_csrf_token()
