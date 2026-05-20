"""Tests for admin score soft-delete + restore."""

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


def test_soft_delete_hides_score_from_public(signed_in_client, make_game, make_score):
    g = make_game()
    s = make_score(game=g, player_name="cheater", score=999_999)

    # Delete via admin
    resp = signed_in_client.post(f"/admin/scores/{s.id}/delete")
    assert resp.status_code == 302

    # Public leaderboard excludes the score.
    resp = signed_in_client.get(f"/api/v1/leaderboards?game={g.slug}")
    assert resp.get_json()["total"] == 0


def test_restore_brings_score_back(signed_in_client, make_game, make_score):
    g = make_game()
    s = make_score(game=g, player_name="cheater", score=999)

    signed_in_client.post(f"/admin/scores/{s.id}/delete")
    resp = signed_in_client.post(f"/admin/scores/{s.id}/restore")
    assert resp.status_code == 302

    resp = signed_in_client.get(f"/api/v1/leaderboards?game={g.slug}")
    assert resp.get_json()["total"] == 1


def test_double_delete_is_idempotent(signed_in_client, make_game, make_score):
    g = make_game()
    s = make_score(game=g, player_name="cheater", score=999)
    signed_in_client.post(f"/admin/scores/{s.id}/delete")
    resp = signed_in_client.post(f"/admin/scores/{s.id}/delete")
    assert resp.status_code == 302  # Redirect with a warning flash, not an error.


def test_audit_rows_written(signed_in_client, make_game, make_score):
    g = make_game()
    s = make_score(game=g, player_name="cheater", score=999)
    signed_in_client.post(f"/admin/scores/{s.id}/delete")
    signed_in_client.post(f"/admin/scores/{s.id}/restore")

    from app.extensions import db
    from app.models.admin_action import AdminAction

    with signed_in_client.application.app_context():
        actions = db.session.execute(
            db.select(AdminAction).order_by(AdminAction.id.asc())
        ).scalars().all()
        kinds = [a.action for a in actions]
        assert "score.soft_delete" in kinds
        assert "score.restore" in kinds


def test_unknown_score_id_returns_404(signed_in_client):
    resp = signed_in_client.post("/admin/scores/9999999/delete")
    assert resp.status_code == 404


def test_unauthenticated_cannot_delete(client, make_game, make_score):
    g = make_game()
    s = make_score(game=g, player_name="ren", score=100)
    resp = client.post(f"/admin/scores/{s.id}/delete", follow_redirects=False)
    # Anonymous users get redirected to login by before_request.
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_open_redirect_in_next_blocked(signed_in_client, make_game, make_score):
    g = make_game()
    s = make_score(game=g, player_name="ren", score=100)
    resp = signed_in_client.post(
        f"/admin/scores/{s.id}/delete",
        data={"next": "http://evil.example.com/"},
    )
    assert resp.status_code == 302
    assert "evil.example.com" not in resp.headers["Location"]


def test_delete_bumps_cache_version(signed_in_client, make_game, make_score, fake_redis):
    g = make_game()
    s = make_score(game=g, player_name="ren", score=100)
    from app.services.cache import current_game_version

    v0 = current_game_version(fake_redis, g.id)
    signed_in_client.post(f"/admin/scores/{s.id}/delete")
    assert current_game_version(fake_redis, g.id) == v0 + 1
