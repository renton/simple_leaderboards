"""Integration tests for GET /api/v1/leaderboards."""

from __future__ import annotations

from datetime import UTC


def _issue_and_submit(client, slug, *, player_name, score):
    token_resp = client.post("/api/v1/sessions", json={"game": slug})
    token = token_resp.get_json()["session_token"]
    resp = client.post(
        "/api/v1/scores",
        json={"game": slug, "player_name": player_name, "score": score},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)


def test_empty_leaderboard_returns_empty(client, make_game):
    g = make_game()
    resp = client.get(f"/api/v1/leaderboards?game={g.slug}")
    assert resp.status_code == 200
    assert resp.get_json() == {
        "page": 1,
        "page_size": 25,
        "total": 0,
        "results": [],
    }


def test_unknown_game_returns_404(client, make_game):
    resp = client.get("/api/v1/leaderboards?game=no-such-game")
    assert resp.status_code == 404


def test_orders_by_score_desc_for_desc_game(client, make_game):
    g = make_game()
    _issue_and_submit(client, g.slug, player_name="ren", score=100)
    _issue_and_submit(client, g.slug, player_name="ana", score=300)
    _issue_and_submit(client, g.slug, player_name="bob", score=200)
    resp = client.get(f"/api/v1/leaderboards?game={g.slug}")
    body = resp.get_json()
    assert [r["player_name"] for r in body["results"]] == ["ana", "bob", "ren"]
    assert body["total"] == 3
    assert body["results"][0]["rank"] == 1


def test_orders_by_score_asc_for_asc_game(client, make_game):
    g = make_game(slug="racing", score_direction="asc")
    _issue_and_submit(client, g.slug, player_name="ren", score=100)
    _issue_and_submit(client, g.slug, player_name="ana", score=50)
    resp = client.get(f"/api/v1/leaderboards?game={g.slug}")
    body = resp.get_json()
    assert [r["player_name"] for r in body["results"]] == ["ana", "ren"]


def test_cache_hit_after_miss(client, make_game):
    g = make_game()
    _issue_and_submit(client, g.slug, player_name="ren", score=100)
    r1 = client.get(f"/api/v1/leaderboards?game={g.slug}")
    r2 = client.get(f"/api/v1/leaderboards?game={g.slug}")
    assert r1.status_code == 200
    assert r1.headers.get("X-Cache") == "MISS"
    assert r2.headers.get("X-Cache") == "HIT"
    assert r1.get_json() == r2.get_json()


def test_new_score_invalidates_cache(client, make_game):
    g = make_game()
    _issue_and_submit(client, g.slug, player_name="ren", score=100)
    r1 = client.get(f"/api/v1/leaderboards?game={g.slug}").get_json()
    assert r1["total"] == 1

    _issue_and_submit(client, g.slug, player_name="ana", score=200)
    r2 = client.get(f"/api/v1/leaderboards?game={g.slug}")
    assert r2.headers.get("X-Cache") == "MISS"
    assert r2.get_json()["total"] == 2


def test_pagination_caps_at_50(client, make_game):
    g = make_game()
    resp = client.get(f"/api/v1/leaderboards?game={g.slug}&page_size=999")
    # >50 should be rejected as invalid_request (Literal validator rejects out-of-range).
    assert resp.status_code == 400


def test_unknown_param_rejected(client, make_game):
    g = make_game()
    resp = client.get(f"/api/v1/leaderboards?game={g.slug}&malicious=1")
    assert resp.status_code == 400


def test_name_filter(client, make_game):
    g = make_game()
    _issue_and_submit(client, g.slug, player_name="RenLawrence", score=100)
    _issue_and_submit(client, g.slug, player_name="renata", score=80)
    _issue_and_submit(client, g.slug, player_name="other", score=200)
    resp = client.get(f"/api/v1/leaderboards?game={g.slug}&name=ren")
    names = {r["player_name"] for r in resp.get_json()["results"]}
    assert names == {"RenLawrence", "renata"}


def test_seed_filter(client, make_game):
    g = make_game()
    # Daily challenge with a seed
    token = client.post("/api/v1/sessions", json={"game": g.slug}).get_json()[
        "session_token"
    ]
    client.post(
        "/api/v1/scores",
        json={
            "game": g.slug,
            "player_name": "daily",
            "score": 100,
            "seed": "2026-05-20",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    _issue_and_submit(client, g.slug, player_name="normal", score=200)
    resp = client.get(f"/api/v1/leaderboards?game={g.slug}&seed=2026-05-20")
    body = resp.get_json()
    assert {r["player_name"] for r in body["results"]} == {"daily"}


def test_soft_deleted_score_hidden(client, make_game, make_score):
    g = make_game()
    make_score(game=g, player_name="alive", score=100)
    from datetime import datetime

    make_score(
        game=g, player_name="dead", score=200, deleted_at=datetime.now(UTC)
    )
    resp = client.get(f"/api/v1/leaderboards?game={g.slug}")
    body = resp.get_json()
    assert {r["player_name"] for r in body["results"]} == {"alive"}
