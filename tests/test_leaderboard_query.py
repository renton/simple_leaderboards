"""Tests for the leaderboard query builder, exercised against real Postgres."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.leaderboard_query import LeaderboardQuery, run_leaderboard_query


def _now():
    return datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def session(db_session):
    return db_session


class TestSortDirection:
    def test_desc_game_higher_first(self, app, make_game, make_score, session):
        g = make_game(score_direction="desc")
        make_score(game=g, player_name="ren", score=100)
        make_score(game=g, player_name="ana", score=200)
        make_score(game=g, player_name="bob", score=150)
        out = run_leaderboard_query(
            session=session, game=g, query=LeaderboardQuery(), now_utc=_now()
        )
        assert [r["player_name"] for r in out["results"]] == ["ana", "bob", "ren"]
        assert out["total"] == 3

    def test_asc_game_lower_first(self, app, make_game, make_score, session):
        g = make_game(slug="racing-classic", score_direction="asc")
        make_score(game=g, player_name="ren", score=Decimal("60.123"))
        make_score(game=g, player_name="ana", score=Decimal("59.500"))
        make_score(game=g, player_name="bob", score=Decimal("60.000"))
        out = run_leaderboard_query(
            session=session, game=g, query=LeaderboardQuery(), now_utc=_now()
        )
        assert [r["player_name"] for r in out["results"]] == ["ana", "bob", "ren"]

    def test_tie_break_earlier_submission_wins(self, app, make_game, make_score, session):
        g = make_game()
        from app.extensions import db

        with app.app_context():
            from app.models.score import Score

            earlier = Score(
                game_id=g.id,
                player_name="early",
                score=100,
                submitted_at=_now() - timedelta(hours=2),
            )
            later = Score(
                game_id=g.id,
                player_name="late",
                score=100,
                submitted_at=_now() - timedelta(hours=1),
            )
            db.session.add_all([earlier, later])
            db.session.commit()
        out = run_leaderboard_query(
            session=session, game=g, query=LeaderboardQuery(), now_utc=_now()
        )
        assert [r["player_name"] for r in out["results"]] == ["early", "late"]


class TestExcludesDeleted:
    def test_soft_deleted_rows_hidden(self, app, make_game, make_score, session):
        g = make_game()
        make_score(game=g, player_name="alive", score=100)
        make_score(game=g, player_name="dead", score=200, deleted_at=_now())
        out = run_leaderboard_query(
            session=session, game=g, query=LeaderboardQuery(), now_utc=_now()
        )
        assert [r["player_name"] for r in out["results"]] == ["alive"]
        assert out["total"] == 1


class TestRangeFilter:
    def test_daily_only_today(self, app, make_game, make_score, session):
        g = make_game()
        from app.extensions import db

        with app.app_context():
            from app.models.score import Score

            db.session.add_all(
                [
                    Score(
                        game_id=g.id, player_name="today", score=100,
                        submitted_at=_now() - timedelta(hours=2),
                    ),
                    Score(
                        game_id=g.id, player_name="yesterday", score=999,
                        submitted_at=_now() - timedelta(days=2),
                    ),
                ]
            )
            db.session.commit()
        out = run_leaderboard_query(
            session=session,
            game=g,
            query=LeaderboardQuery(range="daily"),
            now_utc=_now(),
        )
        assert [r["player_name"] for r in out["results"]] == ["today"]
        assert out["total"] == 1


class TestSeedFilter:
    def test_only_matching_seed(self, app, make_game, make_score, session):
        g = make_game()
        make_score(game=g, player_name="daily", score=100, seed="2026-05-20")
        make_score(game=g, player_name="normal", score=200, seed=None)
        out = run_leaderboard_query(
            session=session,
            game=g,
            query=LeaderboardQuery(seed="2026-05-20"),
            now_utc=_now(),
        )
        assert [r["player_name"] for r in out["results"]] == ["daily"]


class TestNameFilter:
    def test_substring_case_insensitive(self, app, make_game, make_score, session):
        g = make_game()
        make_score(game=g, player_name="RenLawrence", score=100)
        make_score(game=g, player_name="renata", score=80)
        make_score(game=g, player_name="other", score=200)
        out = run_leaderboard_query(
            session=session,
            game=g,
            query=LeaderboardQuery(name="ren"),
            now_utc=_now(),
        )
        names = {r["player_name"] for r in out["results"]}
        assert names == {"RenLawrence", "renata"}


class TestPagination:
    def test_caps_page_size_at_50(self, app, make_game, make_score, session):
        g = make_game()
        for i in range(75):
            make_score(game=g, player_name=f"p{i:02d}", score=i)
        out = run_leaderboard_query(
            session=session,
            game=g,
            query=LeaderboardQuery(page_size=100),
            now_utc=_now(),
        )
        assert out["page_size"] == 50
        assert len(out["results"]) == 50

    def test_pages_are_disjoint_and_cover(self, app, make_game, make_score, session):
        g = make_game()
        for i in range(60):
            make_score(game=g, player_name=f"p{i:02d}", score=i)
        out1 = run_leaderboard_query(
            session=session,
            game=g,
            query=LeaderboardQuery(page=1, page_size=25),
            now_utc=_now(),
        )
        out2 = run_leaderboard_query(
            session=session,
            game=g,
            query=LeaderboardQuery(page=2, page_size=25),
            now_utc=_now(),
        )
        out3 = run_leaderboard_query(
            session=session,
            game=g,
            query=LeaderboardQuery(page=3, page_size=25),
            now_utc=_now(),
        )
        ids = (
            [r["id"] for r in out1["results"]]
            + [r["id"] for r in out2["results"]]
            + [r["id"] for r in out3["results"]]
        )
        assert len(ids) == 60
        assert len(set(ids)) == 60
        assert out1["results"][0]["rank"] == 1
        assert out2["results"][0]["rank"] == 26
        assert out3["results"][0]["rank"] == 51


class TestSortAlternatives:
    def test_sort_by_submitted_at(self, app, make_game, make_score, session):
        g = make_game()
        from app.extensions import db

        with app.app_context():
            from app.models.score import Score

            db.session.add_all(
                [
                    Score(
                        game_id=g.id, player_name="older", score=999,
                        submitted_at=_now() - timedelta(hours=2),
                    ),
                    Score(
                        game_id=g.id, player_name="newest", score=1,
                        submitted_at=_now() - timedelta(minutes=1),
                    ),
                ]
            )
            db.session.commit()
        out = run_leaderboard_query(
            session=session,
            game=g,
            query=LeaderboardQuery(sort="submitted_at"),
            now_utc=_now(),
        )
        assert [r["player_name"] for r in out["results"]] == ["newest", "older"]
