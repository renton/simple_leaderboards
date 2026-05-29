"""Tests for the admin API-test page (/admin/api-test)."""

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
    client.post(
        "/admin/login",
        data={"username": "root", "password": "hunter2-hunter2-hunter2"},
    )
    return client


def test_requires_login(client):
    resp = client.get("/admin/api-test", follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_page_renders_with_both_endpoints(signed_in_client, make_game):
    make_game(slug="tetris-classic", name="Tetris")
    resp = signed_in_client.get("/admin/api-test")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Endpoint selector offers both public read endpoints.
    assert "/api/v1/leaderboards" in body
    assert "/api/v1/champions" in body
    # Champions-specific param fields are present.
    assert 'id="param-since"' in body
    assert 'id="param-until"' in body
    # Leaderboards-specific fields still present.
    assert 'id="param-range"' in body
    assert 'id="param-seed"' in body
    # The game appears as an option.
    assert "tetris-classic" in body
