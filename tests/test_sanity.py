"""Tests for the score-submission sanity check pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.game import Game
from app.services.sanity import SanityError, sanitize_submission


def make_game(min_score=None, max_score=None, custom_fields=None) -> Game:
    g = Game(
        slug="tetris-classic",
        name="Tetris Classic",
        timezone="UTC",
        score_direction="desc",
    )
    g.min_score = Decimal(str(min_score)) if min_score is not None else None
    g.max_score = Decimal(str(max_score)) if max_score is not None else None
    g.meta = {"custom_fields": custom_fields} if custom_fields else {}
    return g


def base_kwargs(**overrides):
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    base = dict(
        game=make_game(min_score=0, max_score=1_000_000),
        player_name="ren",
        score=12345,
        played_at=now,
        seed=None,
        custom_data=None,
        token_issued_at=int(now.timestamp()) - 30,
        skew_seconds=60,
        now=now,
    )
    base.update(overrides)
    return base


class TestHappyPath:
    def test_minimal_valid_submission(self):
        out = sanitize_submission(**base_kwargs(played_at=None))
        assert out.player_name == "ren"
        assert out.score == Decimal("12345")
        assert out.played_at is None
        assert out.seed is None
        assert out.custom_data == {}

    def test_decimal_score_preserved(self):
        out = sanitize_submission(**base_kwargs(score=12.5))
        assert out.score == Decimal("12.5")


class TestPlayerName:
    def test_empty_rejected(self):
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(player_name=""))
        assert e.value.code == "invalid_player_name"

    def test_overlong_rejected(self):
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(player_name="x" * 33))
        assert e.value.code == "invalid_player_name"

    def test_whitespace_trimmed(self):
        out = sanitize_submission(**base_kwargs(player_name="  ren  "))
        assert out.player_name == "ren"


class TestScoreBounds:
    def test_below_min_rejected(self):
        g = make_game(min_score=100, max_score=1000)
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(game=g, score=50))
        assert e.value.code == "score_out_of_bounds"

    def test_above_max_rejected(self):
        g = make_game(min_score=100, max_score=1000)
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(game=g, score=10_000))
        assert e.value.code == "score_out_of_bounds"

    def test_at_bounds_accepted(self):
        g = make_game(min_score=100, max_score=1000)
        out = sanitize_submission(**base_kwargs(game=g, score=100))
        assert out.score == Decimal("100")
        out = sanitize_submission(**base_kwargs(game=g, score=1000))
        assert out.score == Decimal("1000")

    def test_unbounded_game_accepts_any(self):
        g = make_game(min_score=None, max_score=None)
        out = sanitize_submission(**base_kwargs(game=g, score=10**18))
        assert out.score == Decimal(10**18)


class TestPlayedAt:
    def test_future_rejected(self):
        now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
        future = now + timedelta(minutes=10)
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(played_at=future, now=now))
        assert e.value.code == "invalid_played_at"

    def test_within_skew_window_accepted(self):
        now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
        nearly_future = now + timedelta(seconds=30)
        out = sanitize_submission(**base_kwargs(played_at=nearly_future, now=now))
        assert out.played_at == nearly_future

    def test_before_token_issued_rejected(self):
        now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
        token_issued = int(now.timestamp())
        long_ago = now - timedelta(hours=1)
        with pytest.raises(SanityError) as e:
            sanitize_submission(
                **base_kwargs(played_at=long_ago, token_issued_at=token_issued, now=now)
            )
        assert e.value.code == "invalid_played_at"

    def test_naive_played_at_rejected(self):
        with pytest.raises(SanityError) as e:
            sanitize_submission(
                **base_kwargs(played_at=datetime(2026, 5, 20, 12, 0))  # no tzinfo
            )
        assert e.value.code == "invalid_played_at"


class TestSeed:
    def test_valid_seeds(self):
        for seed in ["daily-2026-05-20", "abc_123", "X" * 64]:
            out = sanitize_submission(**base_kwargs(seed=seed))
            assert out.seed == seed

    def test_empty_string_rejected(self):
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(seed=""))
        assert e.value.code == "invalid_seed"

    def test_overlong_rejected(self):
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(seed="x" * 65))
        assert e.value.code == "invalid_seed"

    def test_bad_chars_rejected(self):
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(seed="bad seed!"))
        assert e.value.code == "invalid_seed"

    def test_none_accepted(self):
        out = sanitize_submission(**base_kwargs(seed=None))
        assert out.seed is None


class TestCustomData:
    def test_no_schema_accepts_arbitrary_primitives(self):
        out = sanitize_submission(
            **base_kwargs(custom_data={"combo": 12, "perfect": True})
        )
        assert out.custom_data == {"combo": 12, "perfect": True}

    def test_unknown_field_rejected_when_schema_declared(self):
        g = make_game(
            min_score=0,
            max_score=10**9,
            custom_fields={"combo": {"type": "integer"}},
        )
        with pytest.raises(SanityError) as e:
            sanitize_submission(
                **base_kwargs(game=g, custom_data={"unknown_field": 1})
            )
        assert e.value.code == "invalid_custom_data"

    def test_wrong_type_rejected(self):
        g = make_game(
            min_score=0,
            max_score=10**9,
            custom_fields={"combo": {"type": "integer"}},
        )
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(game=g, custom_data={"combo": "ten"}))
        assert e.value.code == "invalid_custom_data"

    def test_required_field_missing_rejected(self):
        g = make_game(
            min_score=0,
            max_score=10**9,
            custom_fields={"combo": {"type": "integer", "required": True}},
        )
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(game=g, custom_data={}))
        assert e.value.code == "invalid_custom_data"

    def test_value_overlong_rejected(self):
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(custom_data={"note": "x" * 1000}))
        assert e.value.code == "invalid_custom_data"

    def test_too_many_keys_rejected(self):
        too_many = {f"k{i}": i for i in range(40)}
        with pytest.raises(SanityError) as e:
            sanitize_submission(**base_kwargs(custom_data=too_many))
        assert e.value.code == "invalid_custom_data"
