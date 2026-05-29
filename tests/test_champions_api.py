"""Integration tests for GET /api/v1/champions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _now():
    return datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


def test_empty_leaderboard_returns_zeros(client, make_game):
    g = make_game()
    resp = client.get(f"/api/v1/champions?game={g.slug}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {
        "game": g.slug,
        "since": None,
        "until": None,
        "total_seeds": 0,
        "page": 1,
        "page_size": 25,
        "total": 0,
        "results": [],
    }


def test_unknown_game_returns_404(client):
    resp = client.get("/api/v1/champions?game=no-such-game")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "game_not_found"


def test_single_seed_single_winner(client, make_game, make_score):
    g = make_game()
    make_score(game=g, player_name="ren", score=100, seed="2026-05-20")
    make_score(game=g, player_name="ana", score=200, seed="2026-05-20")
    make_score(game=g, player_name="bob", score=50, seed="2026-05-20")
    body = client.get(f"/api/v1/champions?game={g.slug}").get_json()
    assert body["total_seeds"] == 1
    assert body["total"] == 1
    assert body["results"] == [{"rank": 1, "player_name": "ana", "wins": 1}]


def test_multiple_seeds_distributed_winners(client, make_game, make_score):
    g = make_game()
    # seed-1: ren wins
    make_score(game=g, player_name="ren", score=200, seed="seed-1")
    make_score(game=g, player_name="ana", score=100, seed="seed-1")
    # seed-2: ana wins
    make_score(game=g, player_name="ana", score=500, seed="seed-2")
    make_score(game=g, player_name="ren", score=400, seed="seed-2")
    # seed-3: ana wins
    make_score(game=g, player_name="ana", score=300, seed="seed-3")
    make_score(game=g, player_name="bob", score=100, seed="seed-3")
    body = client.get(f"/api/v1/champions?game={g.slug}").get_json()
    assert body["total_seeds"] == 3
    assert body["total"] == 2
    assert body["results"] == [
        {"rank": 1, "player_name": "ana", "wins": 2},
        {"rank": 2, "player_name": "ren", "wins": 1},
    ]


def test_unseeded_scores_ignored(client, make_game, make_score):
    g = make_game()
    make_score(game=g, player_name="seeded-winner", score=10, seed="seed-1")
    make_score(game=g, player_name="random-best-score", score=99999, seed=None)
    body = client.get(f"/api/v1/champions?game={g.slug}").get_json()
    assert body["total_seeds"] == 1
    assert body["results"] == [
        {"rank": 1, "player_name": "seeded-winner", "wins": 1}
    ]


def test_soft_deleted_winner_promotes_next(client, make_game, make_score):
    g = make_game()
    make_score(game=g, player_name="cheater", score=999, seed="s", deleted_at=_now())
    make_score(game=g, player_name="honest", score=100, seed="s")
    body = client.get(f"/api/v1/champions?game={g.slug}").get_json()
    assert body["results"] == [{"rank": 1, "player_name": "honest", "wins": 1}]


def test_asc_game_inverts_winner(client, make_game, make_score):
    g = make_game(slug="racing", score_direction="asc")
    make_score(game=g, player_name="slow", score=120, seed="track-1")
    make_score(game=g, player_name="fast", score=60, seed="track-1")
    body = client.get("/api/v1/champions?game=racing").get_json()
    assert body["results"] == [{"rank": 1, "player_name": "fast", "wins": 1}]


def test_tie_break_earlier_submission_wins(app, make_game, client):
    g = make_game()
    from app.extensions import db
    from app.models.score import Score

    with app.app_context():
        earlier = Score(
            game_id=g.id,
            player_name="early",
            score=100,
            seed="s",
            submitted_at=_now() - timedelta(hours=2),
        )
        later = Score(
            game_id=g.id,
            player_name="late",
            score=100,
            seed="s",
            submitted_at=_now() - timedelta(hours=1),
        )
        db.session.add_all([earlier, later])
        db.session.commit()
    body = client.get(f"/api/v1/champions?game={g.slug}").get_json()
    assert body["results"] == [{"rank": 1, "player_name": "early", "wins": 1}]


def test_since_filter(app, make_game, client):
    g = make_game()
    from app.extensions import db
    from app.models.score import Score

    with app.app_context():
        db.session.add_all(
            [
                Score(
                    game_id=g.id,
                    player_name="old-winner",
                    score=999,
                    seed="old-seed",
                    submitted_at=_now() - timedelta(days=30),
                ),
                Score(
                    game_id=g.id,
                    player_name="recent-winner",
                    score=100,
                    seed="recent-seed",
                    submitted_at=_now() - timedelta(hours=2),
                ),
            ]
        )
        db.session.commit()
    since = (_now() - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    body = client.get(f"/api/v1/champions?game={g.slug}&since={since}").get_json()
    assert body["total_seeds"] == 1
    assert body["results"] == [
        {"rank": 1, "player_name": "recent-winner", "wins": 1}
    ]


def test_since_and_until_window(app, make_game, client):
    g = make_game()
    from app.extensions import db
    from app.models.score import Score

    with app.app_context():
        db.session.add_all(
            [
                Score(
                    game_id=g.id,
                    player_name="before",
                    score=999,
                    seed="a",
                    submitted_at=_now() - timedelta(days=30),
                ),
                Score(
                    game_id=g.id,
                    player_name="inside",
                    score=999,
                    seed="b",
                    submitted_at=_now() - timedelta(days=5),
                ),
                Score(
                    game_id=g.id,
                    player_name="after",
                    score=999,
                    seed="c",
                    submitted_at=_now() + timedelta(days=5),
                ),
            ]
        )
        db.session.commit()
    since = (_now() - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    until = _now().isoformat().replace("+00:00", "Z")
    body = client.get(
        f"/api/v1/champions?game={g.slug}&since={since}&until={until}"
    ).get_json()
    assert body["total_seeds"] == 1
    assert body["results"] == [{"rank": 1, "player_name": "inside", "wins": 1}]


def test_invalid_since_until_order_rejected(client, make_game):
    g = make_game()
    since = _now().isoformat().replace("+00:00", "Z")
    until = (_now() - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    resp = client.get(f"/api/v1/champions?game={g.slug}&since={since}&until={until}")
    assert resp.status_code == 400


def test_extra_param_rejected(client, make_game):
    g = make_game()
    resp = client.get(f"/api/v1/champions?game={g.slug}&malicious=1")
    assert resp.status_code == 400


def test_page_size_caps_at_50(client, make_game):
    g = make_game()
    resp = client.get(f"/api/v1/champions?game={g.slug}&page_size=999")
    assert resp.status_code == 400


def test_pagination(client, make_game, make_score):
    g = make_game()
    # 30 distinct players, each wins one seed
    for i in range(30):
        make_score(game=g, player_name=f"p{i:02d}", score=100, seed=f"seed-{i}")
    r1 = client.get(f"/api/v1/champions?game={g.slug}&page=1&page_size=10").get_json()
    r2 = client.get(f"/api/v1/champions?game={g.slug}&page=2&page_size=10").get_json()
    r3 = client.get(f"/api/v1/champions?game={g.slug}&page=3&page_size=10").get_json()
    assert r1["total_seeds"] == 30
    assert r1["total"] == 30
    assert len(r1["results"]) == 10
    assert len(r2["results"]) == 10
    assert len(r3["results"]) == 10
    assert r1["results"][0]["rank"] == 1
    assert r2["results"][0]["rank"] == 11
    assert r3["results"][0]["rank"] == 21
    all_names = {r["player_name"] for r in r1["results"] + r2["results"] + r3["results"]}
    assert len(all_names) == 30


def test_cache_hit_after_miss(client, make_game, make_score):
    g = make_game()
    make_score(game=g, player_name="ren", score=100, seed="s1")
    r1 = client.get(f"/api/v1/champions?game={g.slug}")
    r2 = client.get(f"/api/v1/champions?game={g.slug}")
    assert r1.headers["X-Cache"] == "MISS"
    assert r2.headers["X-Cache"] == "HIT"
    assert r1.get_json() == r2.get_json()


def test_new_score_invalidates_cache(client, make_game, make_score):
    g = make_game()
    make_score(game=g, player_name="ren", score=100, seed="s1")
    r1 = client.get(f"/api/v1/champions?game={g.slug}").get_json()
    assert r1["total_seeds"] == 1

    # Submit a score for a NEW seed via the public API (triggers cache bump).
    token = client.post("/api/v1/sessions", json={"game": g.slug}).get_json()[
        "session_token"
    ]
    resp = client.post(
        "/api/v1/scores",
        json={"game": g.slug, "player_name": "ana", "score": 200, "seed": "s2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    r2 = client.get(f"/api/v1/champions?game={g.slug}")
    assert r2.headers["X-Cache"] == "MISS"
    assert r2.get_json()["total_seeds"] == 2


def test_admin_score_soft_delete_invalidates_cache(client, make_game, make_score, app):
    g = make_game()
    s = make_score(game=g, player_name="cheater", score=999, seed="s1")
    r1 = client.get(f"/api/v1/champions?game={g.slug}").get_json()
    assert r1["results"] == [{"rank": 1, "player_name": "cheater", "wins": 1}]

    # Soft-delete bumps the cache version via app/admin/scores.py.
    from app.extensions import db
    from app.models.score import Score as S

    with app.app_context():
        row = db.session.get(S, s.id)
        row.deleted_at = _now()
        db.session.commit()
    from app.extensions import redis_client
    from app.services.cache import bump_game_version

    bump_game_version(redis_client, g.id)
    r2 = client.get(f"/api/v1/champions?game={g.slug}").get_json()
    assert r2["results"] == []
    assert r2["total_seeds"] == 0


def test_iso_datetime_with_z_suffix_accepted(client, make_game, make_score):
    g = make_game()
    make_score(game=g, player_name="ren", score=100, seed="s")
    resp = client.get(
        f"/api/v1/champions?game={g.slug}&since=2025-01-01T00:00:00Z"
    )
    assert resp.status_code == 200
