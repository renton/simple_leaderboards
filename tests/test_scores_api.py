"""Integration tests for POST /api/v1/scores."""

from __future__ import annotations


def _issue_token(client, slug):
    resp = client.post("/api/v1/sessions", json={"game": slug})
    assert resp.status_code == 201
    return resp.get_json()["session_token"]


def _post_score(client, token, body):
    return client.post(
        "/api/v1/scores",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_submit_score_happy_path(client, make_game):
    g = make_game()
    token = _issue_token(client, g.slug)
    resp = _post_score(
        client,
        token,
        {"game": g.slug, "player_name": "ren", "score": 1234},
    )
    assert resp.status_code == 201
    assert "id" in resp.get_json()


def test_missing_authorization_header_rejected(client, make_game):
    g = make_game()
    resp = client.post(
        "/api/v1/scores",
        json={"game": g.slug, "player_name": "ren", "score": 100},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_session"


def test_garbage_token_rejected(client, make_game):
    g = make_game()
    resp = _post_score(
        client,
        "garbage.token.value",
        {"game": g.slug, "player_name": "ren", "score": 100},
    )
    assert resp.status_code == 401


def test_replay_rejects_second_use(client, make_game):
    g = make_game()
    token = _issue_token(client, g.slug)
    r1 = _post_score(client, token, {"game": g.slug, "player_name": "ren", "score": 1})
    r2 = _post_score(client, token, {"game": g.slug, "player_name": "ren", "score": 2})
    assert r1.status_code == 201
    assert r2.status_code == 401
    assert r2.get_json()["error"] == "invalid_session"


def test_token_bound_to_different_game_rejected(client, make_game):
    g1 = make_game(slug="game-a")
    g2 = make_game(slug="game-b")
    token_a = _issue_token(client, g1.slug)
    resp = _post_score(
        client,
        token_a,
        {"game": g2.slug, "player_name": "ren", "score": 100},
    )
    assert resp.status_code == 401


def test_score_out_of_bounds_rejected(client, make_game):
    g = make_game(min_score=0, max_score=10_000)
    token = _issue_token(client, g.slug)
    resp = _post_score(
        client,
        token,
        {"game": g.slug, "player_name": "ren", "score": 99_999},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "score_out_of_bounds"


def test_invalid_player_name_rejected(client, make_game):
    g = make_game()
    token = _issue_token(client, g.slug)
    resp = _post_score(
        client,
        token,
        {"game": g.slug, "player_name": "   ", "score": 100},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_player_name"


def test_unknown_game_slug_returns_404(client, make_game):
    g = make_game()
    token = _issue_token(client, g.slug)
    resp = _post_score(
        client,
        token,
        {"game": "no-such-game", "player_name": "ren", "score": 100},
    )
    assert resp.status_code == 404


def test_extra_field_in_body_rejected(client, make_game):
    g = make_game()
    token = _issue_token(client, g.slug)
    resp = _post_score(
        client,
        token,
        {"game": g.slug, "player_name": "ren", "score": 100, "secret": "x"},
    )
    assert resp.status_code == 400


def test_device_info_includes_browser_from_ua(client, make_game):
    g = make_game()
    token = _issue_token(client, g.slug)
    resp = client.post(
        "/api/v1/scores",
        json={"game": g.slug, "player_name": "ren", "score": 100},
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
            ),
        },
    )
    assert resp.status_code == 201
    # Verify the row stored the parsed UA.
    from app.extensions import db
    from app.models.score import Score

    with client.application.app_context():
        row = db.session.execute(
            db.select(Score).order_by(Score.id.desc())
        ).scalars().first()
        assert row.device_info.get("os") == "Windows"
        assert row.device_info.get("browser") == "Chrome"


def test_cache_version_bumps_on_score_insert(client, make_game, fake_redis):
    g = make_game()
    from app.services.cache import current_game_version

    assert current_game_version(fake_redis, g.id) == 0
    token = _issue_token(client, g.slug)
    resp = _post_score(
        client,
        token,
        {"game": g.slug, "player_name": "ren", "score": 100},
    )
    assert resp.status_code == 201
    assert current_game_version(fake_redis, g.id) == 1
