"""End-to-end smoke test: full sessions -> scores -> leaderboards round-trip."""

from __future__ import annotations


def test_full_round_trip(client, make_game):
    g = make_game(
        slug="tetris-classic",
        name="Tetris Classic",
        min_score=0,
        max_score=10**6,
    )

    def submit(payload, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/123.0"):
        token = client.post("/api/v1/sessions", json={"game": g.slug}).get_json()[
            "session_token"
        ]
        return client.post(
            "/api/v1/scores",
            json={"game": g.slug, **payload},
            headers={"Authorization": f"Bearer {token}", "User-Agent": ua},
        ), token

    # 1 + 2. Submit a normal (un-seeded) score.
    normal_resp, _ = submit(
        {"player_name": "ren", "score": 31415, "custom_data": {"combo": 47, "perfect": True}}
    )
    assert normal_resp.status_code == 201, normal_resp.get_data(as_text=True)
    score_id = normal_resp.get_json()["id"]
    assert isinstance(score_id, int) and score_id > 0

    # Submit a seeded (daily-challenge) score for the same game.
    seeded_resp, seeded_token = submit(
        {"player_name": "ana", "score": 99999, "seed": "daily-2026-05-20"}
    )
    assert seeded_resp.status_code == 201

    # 3. Default leaderboard (no seed param) shows ONLY un-seeded scores.
    lb_resp = client.get(f"/api/v1/leaderboards?game={g.slug}")
    assert lb_resp.status_code == 200
    assert lb_resp.headers["X-Cache"] == "MISS"
    body = lb_resp.get_json()
    assert body["total"] == 1
    row = body["results"][0]
    assert row["player_name"] == "ren"
    assert row["score"] == 31415.0
    assert row["seed"] is None
    assert row["custom_data"]["combo"] == 47
    assert row["device_info"]["os"] == "Windows"
    assert row["device_info"]["browser"] == "Chrome"

    # 4. Second read is a cache HIT.
    lb_resp2 = client.get(f"/api/v1/leaderboards?game={g.slug}")
    assert lb_resp2.headers["X-Cache"] == "HIT"
    assert lb_resp2.get_json() == body

    # 5. Seeded leaderboard shows ONLY that seed's scores.
    seeded = client.get(
        f"/api/v1/leaderboards?game={g.slug}&seed=daily-2026-05-20"
    ).get_json()
    assert seeded["total"] == 1
    assert seeded["results"][0]["player_name"] == "ana"

    # 6. Replay of an already-consumed token is rejected.
    replay = client.post(
        "/api/v1/scores",
        json={"game": g.slug, "player_name": "ana", "score": 1},
        headers={"Authorization": f"Bearer {seeded_token}"},
    )
    assert replay.status_code == 401
    assert replay.get_json()["error"] == "invalid_session"


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.data == b"ok"
