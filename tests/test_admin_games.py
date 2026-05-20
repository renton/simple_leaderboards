"""Tests for admin game CRUD."""

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


def test_games_list_renders(signed_in_client):
    resp = signed_in_client.get("/admin/games")
    assert resp.status_code == 200
    assert b"No games yet" in resp.data


def test_create_game_happy_path(signed_in_client):
    resp = signed_in_client.post(
        "/admin/games/new",
        data={
            "name": "Tetris Classic",
            "slug": "tetris-classic",
            "timezone": "UTC",
            "score_direction": "desc",
            "min_score": "0",
            "max_score": "999999",
            "metadata_json": "{}",
            "archived": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    list_resp = signed_in_client.get("/admin/games")
    assert b"tetris-classic" in list_resp.data


def test_create_game_invalid_slug_rejected(signed_in_client):
    resp = signed_in_client.post(
        "/admin/games/new",
        data={
            "name": "Bad",
            "slug": "Has Spaces",
            "timezone": "UTC",
            "score_direction": "desc",
            "metadata_json": "{}",
        },
    )
    assert resp.status_code == 400


def test_create_game_invalid_timezone_rejected(signed_in_client):
    resp = signed_in_client.post(
        "/admin/games/new",
        data={
            "name": "Bad",
            "slug": "bad-tz",
            "timezone": "Mars/Olympus",
            "score_direction": "desc",
            "metadata_json": "{}",
        },
    )
    assert resp.status_code == 400


def test_min_above_max_rejected(signed_in_client):
    resp = signed_in_client.post(
        "/admin/games/new",
        data={
            "name": "Bad",
            "slug": "bad-bounds",
            "timezone": "UTC",
            "score_direction": "desc",
            "min_score": "100",
            "max_score": "10",
            "metadata_json": "{}",
        },
    )
    assert resp.status_code == 400


def test_invalid_metadata_json_rejected(signed_in_client):
    resp = signed_in_client.post(
        "/admin/games/new",
        data={
            "name": "Bad",
            "slug": "bad-meta",
            "timezone": "UTC",
            "score_direction": "desc",
            "metadata_json": "not json {",
        },
    )
    assert resp.status_code == 400


def test_edit_game(signed_in_client):
    signed_in_client.post(
        "/admin/games/new",
        data={
            "name": "Tetris",
            "slug": "tetris-classic",
            "timezone": "UTC",
            "score_direction": "desc",
            "metadata_json": "{}",
        },
    )
    from app.extensions import db
    from app.models.game import Game

    with signed_in_client.application.app_context():
        gid = db.session.execute(
            db.select(Game.id).where(Game.slug == "tetris-classic")
        ).scalar_one()

    resp = signed_in_client.get(f"/admin/games/{gid}/edit")
    assert resp.status_code == 200
    assert b"tetris-classic" in resp.data

    resp = signed_in_client.post(
        f"/admin/games/{gid}/edit",
        data={
            "name": "Tetris (renamed)",
            "slug": "tetris-classic",
            "timezone": "America/New_York",
            "score_direction": "desc",
            "metadata_json": "{}",
        },
    )
    assert resp.status_code == 302
    with signed_in_client.application.app_context():
        g = db.session.execute(
            db.select(Game).where(Game.id == gid)
        ).scalar_one()
        assert g.name == "Tetris (renamed)"
        assert g.timezone == "America/New_York"


def test_audit_row_written_on_create(signed_in_client):
    signed_in_client.post(
        "/admin/games/new",
        data={
            "name": "Tetris",
            "slug": "tetris-classic",
            "timezone": "UTC",
            "score_direction": "desc",
            "metadata_json": "{}",
        },
    )
    from app.extensions import db
    from app.models.admin_action import AdminAction

    with signed_in_client.application.app_context():
        rows = db.session.execute(
            db.select(AdminAction).where(AdminAction.action == "game.create")
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].target_type == "game"
        assert rows[0].details.get("slug") == "tetris-classic"
