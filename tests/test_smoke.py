"""End-to-end smoke test: full sessions -> scores -> leaderboards round-trip."""

from __future__ import annotations


def test_full_round_trip(client, make_game):
    g = make_game(
        slug="tetris-classic",
        name="Tetris Classic",
        min_score=0,
        max_score=10**6,
    )

    # 1. Public client asks for a session token.
    token_resp = client.post("/api/v1/sessions", json={"game": g.slug})
    assert token_resp.status_code == 201
    token = token_resp.get_json()["session_token"]

    # 2. Public client submits a score with the token.
    score_resp = client.post(
        "/api/v1/scores",
        json={
            "game": g.slug,
            "player_name": "ren",
            "score": 31415,
            "seed": "daily-2026-05-20",
            "custom_data": {"combo": 47, "perfect": True},
        },
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/123.0",
        },
    )
    assert score_resp.status_code == 201, score_resp.get_data(as_text=True)
    score_id = score_resp.get_json()["id"]
    assert isinstance(score_id, int) and score_id > 0

    # 3. Public client reads the leaderboard (cache MISS).
    lb_resp = client.get(f"/api/v1/leaderboards?game={g.slug}")
    assert lb_resp.status_code == 200
    assert lb_resp.headers["X-Cache"] == "MISS"
    body = lb_resp.get_json()
    assert body["total"] == 1
    row = body["results"][0]
    assert row["player_name"] == "ren"
    assert row["score"] == 31415.0
    assert row["seed"] == "daily-2026-05-20"
    assert row["custom_data"]["combo"] == 47
    assert row["device_info"]["os"] == "Windows"
    assert row["device_info"]["browser"] == "Chrome"

    # 4. Second read is a cache HIT.
    lb_resp2 = client.get(f"/api/v1/leaderboards?game={g.slug}")
    assert lb_resp2.headers["X-Cache"] == "HIT"
    assert lb_resp2.get_json() == body

    # 5. Daily leaderboard with seed filter.
    seeded = client.get(
        f"/api/v1/leaderboards?game={g.slug}&seed=daily-2026-05-20"
    ).get_json()
    assert seeded["total"] == 1

    # 6. Replay rejected.
    replay = client.post(
        "/api/v1/scores",
        json={"game": g.slug, "player_name": "ren", "score": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replay.status_code == 401
    assert replay.get_json()["error"] == "invalid_session"


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.data == b"ok"
