"""Tests for the leaderboard cache."""

from __future__ import annotations

import fakeredis
import pytest

from app.services import cache as c


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def _params(**overrides):
    base = {"range": "all-time", "seed": None, "name": None, "sort": "score", "page": 1, "page_size": 25}
    base.update(overrides)
    return base


def test_params_hash_is_order_independent():
    a = {"range": "daily", "page": 1, "seed": "s"}
    b = {"seed": "s", "page": 1, "range": "daily"}
    assert c.params_hash(a) == c.params_hash(b)


def test_params_hash_differs_on_value_change():
    assert c.params_hash({"x": 1}) != c.params_hash({"x": 2})


def test_get_or_set_miss_then_hit(r):
    calls = []

    def loader():
        calls.append(1)
        return [{"player": "ren", "score": 100}]

    out, hit = c.get_or_set(
        redis_client=r, game_id=1, params=_params(), loader=loader, ttl_seconds=60
    )
    assert out == [{"player": "ren", "score": 100}]
    assert hit is False
    assert calls == [1]

    out2, hit2 = c.get_or_set(
        redis_client=r, game_id=1, params=_params(), loader=loader, ttl_seconds=60
    )
    assert out2 == out
    assert hit2 is True
    assert calls == [1]  # loader NOT called again


def test_bump_version_invalidates_cache(r):
    def loader_one():
        return ["v1"]

    def loader_two():
        return ["v2"]

    out1, _ = c.get_or_set(
        redis_client=r, game_id=1, params=_params(), loader=loader_one, ttl_seconds=60
    )
    assert out1 == ["v1"]

    c.bump_game_version(r, 1)

    out2, hit2 = c.get_or_set(
        redis_client=r, game_id=1, params=_params(), loader=loader_two, ttl_seconds=60
    )
    assert out2 == ["v2"]
    assert hit2 is False


def test_isolation_between_games(r):
    out_a, _ = c.get_or_set(
        redis_client=r, game_id=1, params=_params(), loader=lambda: ["a"], ttl_seconds=60
    )
    out_b, _ = c.get_or_set(
        redis_client=r, game_id=2, params=_params(), loader=lambda: ["b"], ttl_seconds=60
    )
    assert out_a == ["a"]
    assert out_b == ["b"]

    # Bumping one game shouldn't invalidate the other.
    c.bump_game_version(r, 1)
    cached_b, hit_b = c.get_or_set(
        redis_client=r, game_id=2, params=_params(), loader=lambda: ["NEVER"], ttl_seconds=60
    )
    assert cached_b == ["b"]
    assert hit_b is True


def test_different_params_get_different_cache_keys(r):
    c.get_or_set(
        redis_client=r, game_id=1, params=_params(page=1), loader=lambda: ["p1"], ttl_seconds=60
    )
    c.get_or_set(
        redis_client=r, game_id=1, params=_params(page=2), loader=lambda: ["p2"], ttl_seconds=60
    )
    out1, hit1 = c.get_or_set(
        redis_client=r, game_id=1, params=_params(page=1), loader=lambda: ["NEVER"], ttl_seconds=60
    )
    out2, hit2 = c.get_or_set(
        redis_client=r, game_id=1, params=_params(page=2), loader=lambda: ["NEVER"], ttl_seconds=60
    )
    assert (out1, hit1) == (["p1"], True)
    assert (out2, hit2) == (["p2"], True)


def test_current_version_starts_at_zero(r):
    assert c.current_game_version(r, 99) == 0


def test_corrupt_cache_entry_repopulates(r):
    # Manually plant a garbage value at the key the cache would use.
    ver = c.current_game_version(r, 1)
    key = c.QUERY_KEY.format(game_id=1, ver=ver, h=c.params_hash(_params()))
    r.set(key, "not-json")
    out, hit = c.get_or_set(
        redis_client=r, game_id=1, params=_params(), loader=lambda: ["fresh"], ttl_seconds=60
    )
    assert out == ["fresh"]
    assert hit is False
