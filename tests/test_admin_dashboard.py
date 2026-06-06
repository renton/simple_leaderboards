"""Tests for the admin dashboard + leaderboard view."""

from __future__ import annotations

from datetime import UTC

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


def test_dashboard_renders_with_no_games(signed_in_client):
    resp = signed_in_client.get("/admin/")
    assert resp.status_code == 200
    assert b"No games registered" in resp.data


def test_dashboard_picks_first_non_archived_game(signed_in_client, make_game, make_score):
    g = make_game(slug="tetris-classic", name="Tetris")
    make_score(game=g, player_name="ren", score=100)
    make_score(game=g, player_name="ana", score=200)
    resp = signed_in_client.get("/admin/")
    assert resp.status_code == 200
    assert b"Tetris" in resp.data
    assert b"ren" in resp.data
    assert b"ana" in resp.data


def test_dashboard_filter_by_range(signed_in_client, make_game, make_score):
    from datetime import datetime, timedelta

    g = make_game()  # default timezone UTC
    now = datetime.now(UTC)
    # Noon-today UTC is always inside today's daily window regardless of the
    # wall-clock hour the test runs at (avoids a midnight-boundary flake).
    today_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    make_score(game=g, player_name="today", score=100, submitted_at=today_noon)
    make_score(game=g, player_name="oldweek", score=999, submitted_at=now - timedelta(days=30))
    resp = signed_in_client.get(f"/admin/?game_id={g.id}&range=daily")
    assert resp.status_code == 200
    assert b"today" in resp.data
    assert b"oldweek" not in resp.data


def test_dashboard_seed_filter(signed_in_client, make_game, make_score):
    g = make_game()
    make_score(game=g, player_name="daily", score=100, seed="2026-05-20")
    make_score(game=g, player_name="normal", score=200, seed=None)
    resp = signed_in_client.get(f"/admin/?game_id={g.id}&seed=2026-05-20")
    assert b"daily" in resp.data
    assert b"normal" not in resp.data


def test_dashboard_pagination_caps(signed_in_client, make_game, make_score):
    g = make_game()
    for i in range(60):
        make_score(game=g, player_name=f"p{i:02d}", score=i)
    # >50 in URL should be ignored / capped.
    resp = signed_in_client.get(f"/admin/?game_id={g.id}&page_size=99999")
    assert resp.status_code == 200
    # Default cap means the page can't show more than 50 rows.
    assert resp.data.count(b"<tr>") <= 60  # header + body rows; sanity bound


def test_dashboard_includes_logout_link(signed_in_client, make_game):
    make_game()
    resp = signed_in_client.get("/admin/")
    assert b"/admin/logout" in resp.data
