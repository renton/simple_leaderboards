"""Integration tests for POST /api/v1/sessions."""

from __future__ import annotations


def test_issue_session_happy_path(client, make_game):
    g = make_game(slug="tetris-classic")
    resp = client.post("/api/v1/sessions", json={"game": "tetris-classic"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert "session_token" in body and body["session_token"]
    assert "expires_at" in body


def test_unknown_game_returns_404(client, make_game):
    resp = client.post("/api/v1/sessions", json={"game": "no-such-game"})
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"] == "game_not_found"


def test_missing_game_field_returns_400(client, make_game):
    g = make_game()
    resp = client.post("/api/v1/sessions", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_request"


def test_extra_field_rejected(client, make_game):
    g = make_game()
    resp = client.post(
        "/api/v1/sessions",
        json={"game": "tetris-classic", "extra": "nope"},
    )
    assert resp.status_code == 400


def test_non_json_body_rejected(client, make_game):
    g = make_game()
    resp = client.post(
        "/api/v1/sessions",
        data="not json",
        content_type="text/plain",
    )
    assert resp.status_code == 400


def test_archived_game_returns_404(client, make_game):
    g = make_game(slug="archived-game", archived=True)
    resp = client.post("/api/v1/sessions", json={"game": "archived-game"})
    assert resp.status_code == 404


def test_two_sessions_get_different_tokens(client, make_game):
    g = make_game()
    r1 = client.post("/api/v1/sessions", json={"game": "tetris-classic"}).get_json()
    r2 = client.post("/api/v1/sessions", json={"game": "tetris-classic"}).get_json()
    assert r1["session_token"] != r2["session_token"]
