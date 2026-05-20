"""Tests for admin login / logout / lockout."""

from __future__ import annotations

import pytest


@pytest.fixture
def make_admin(app):
    def _factory(username="root", password="hunter2-hunter2-hunter2"):
        from app.extensions import db
        from app.models.user import AdminUser

        with app.app_context():
            user = AdminUser(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            db.session.refresh(user)
            db.session.expunge(user)
            return user, password

    return _factory


def test_login_page_renders(client):
    resp = client.get("/admin/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_login_success_redirects_to_dashboard(client, make_admin):
    _, password = make_admin()
    resp = client.post(
        "/admin/login",
        data={"username": "root", "password": password},
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin/")


def test_login_failure_returns_401(client, make_admin):
    make_admin()
    resp = client.post(
        "/admin/login",
        data={"username": "root", "password": "wrong-password"},
    )
    assert resp.status_code == 401


def test_login_unknown_user_returns_401(client):
    resp = client.post(
        "/admin/login",
        data={"username": "ghost", "password": "doesntmatter12"},
    )
    assert resp.status_code == 401


def test_account_locks_after_max_failures(client, make_admin):
    from app.extensions import db
    from app.models.user import AdminUser

    _, password = make_admin()
    for _ in range(10):
        client.post(
            "/admin/login",
            data={"username": "root", "password": "wrong-password"},
        )
    with client.application.app_context():
        user = db.session.execute(
            db.select(AdminUser).where(AdminUser.username == "root")
        ).scalar_one()
        assert user.failed_login_attempts >= 10
        assert user.locked_until is not None

    # Even with the correct password, login is locked.
    resp = client.post(
        "/admin/login",
        data={"username": "root", "password": password},
    )
    assert resp.status_code == 423


def test_unauthenticated_admin_routes_redirect_to_login(client):
    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_authenticated_can_logout(client, make_admin):
    _, password = make_admin()
    client.post("/admin/login", data={"username": "root", "password": password})
    resp = client.post("/admin/logout")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_open_redirect_in_next_blocked(client, make_admin):
    _, password = make_admin()
    resp = client.post(
        "/admin/login?next=http://evil.example.com/",
        data={"username": "root", "password": password},
    )
    assert resp.status_code == 302
    assert "evil.example.com" not in resp.headers["Location"]
    assert resp.headers["Location"].startswith("/")


def test_relative_next_path_honored(client, make_admin):
    _, password = make_admin()
    resp = client.post(
        "/admin/login?next=/admin/games",
        data={"username": "root", "password": password},
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin/games")
