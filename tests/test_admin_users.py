"""Tests for admin user list / create."""

from __future__ import annotations

import pytest


@pytest.fixture
def signed_in_client(client, app):
    from app.extensions import db
    from app.models.user import AdminUser

    with app.app_context():
        user = AdminUser(username="root")
        user.set_password("hunter2-hunter2-hunter2")
        db.session.add(user)
        db.session.commit()
    client.post("/admin/login", data={"username": "root", "password": "hunter2-hunter2-hunter2"})
    return client


def test_users_list_renders(signed_in_client):
    resp = signed_in_client.get("/admin/users")
    assert resp.status_code == 200
    assert b"root" in resp.data
    assert b"(you)" in resp.data


def test_create_admin_happy_path(signed_in_client):
    resp = signed_in_client.post(
        "/admin/users/new",
        data={
            "username": "secondary",
            "password": "newpassword-2",
            "confirm": "newpassword-2",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    list_resp = signed_in_client.get("/admin/users")
    assert b"secondary" in list_resp.data


def test_create_admin_password_mismatch(signed_in_client):
    resp = signed_in_client.post(
        "/admin/users/new",
        data={
            "username": "secondary",
            "password": "newpassword-2",
            "confirm": "different-pass",
        },
    )
    assert resp.status_code == 400


def test_create_admin_short_password(signed_in_client):
    resp = signed_in_client.post(
        "/admin/users/new",
        data={
            "username": "secondary",
            "password": "short",
            "confirm": "short",
        },
    )
    assert resp.status_code == 400


def test_create_admin_duplicate_username(signed_in_client):
    resp = signed_in_client.post(
        "/admin/users/new",
        data={
            "username": "root",  # already exists from fixture
            "password": "hunter2-hunter2-hunter2",
            "confirm": "hunter2-hunter2-hunter2",
        },
    )
    assert resp.status_code == 400


def test_create_admin_audit_row_written(signed_in_client):
    signed_in_client.post(
        "/admin/users/new",
        data={
            "username": "secondary",
            "password": "newpassword-2",
            "confirm": "newpassword-2",
        },
    )
    from app.extensions import db
    from app.models.admin_action import AdminAction

    with signed_in_client.application.app_context():
        rows = db.session.execute(
            db.select(AdminAction).where(AdminAction.action == "admin.create")
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].details.get("username") == "secondary"
