import re

from utils.helpers import generate_and_store_otp, verify_session_otp


def test_csrf_rejects_missing_token(app, client):
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post(
        "/login_admin",
        data={
            "username": "admin",
            "password": "password123",
        },
    )

    assert response.status_code == 400


def test_csrf_accepts_valid_token(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    page = client.get("/login")
    token_match = re.search(rb'name="csrf-token" content="([^"]+)"', page.data)
    assert token_match

    response = client.post(
        "/login_admin",
        data={
            "username": "admin",
            "password": "password123",
            "csrf_token": token_match.group(1).decode(),
        },
    )

    assert response.status_code == 302
    assert "/admin_dash" in response.location


def test_otp_is_not_stored_in_plaintext(app):
    with app.test_request_context("/"):
        otp = generate_and_store_otp("security_test")

        from flask import session

        assert session["security_test_otp"] != otp
        assert verify_session_otp("security_test", otp)[0] is True


def test_destructive_routes_do_not_accept_get(client):
    assert client.get("/logout").status_code == 405
    assert client.get("/delete/course/1").status_code == 405
