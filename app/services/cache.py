"""Redis-backed leaderboard cache with per-game version-key invalidation.

Keys:
    lb:game:{game_id}:ver       integer; INCR'd on every score insert
    lb:q:{game_id}:v{ver}:{h}   cached JSON result, TTL = CACHE_TTL_SECONDS

Invalidation: bumping the version key makes every previous query key
unreachable. Old keys expire naturally via TTL (or evict under LRU pressure).
No SCAN, no DEL, no race window.

Cache key hash is `blake2b(canonical_json(params), 16)` so that equivalent
queries with different param ordering collapse to a single cache entry.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

GAME_VERSION_KEY = "lb:game:{game_id}:ver"
QUERY_KEY = "lb:q:{game_id}:v{ver}:{h}"


def _canonical_json(params: dict[str, Any]) -> str:
    """Stable JSON serialization for cache keying.

    `sort_keys=True` + `separators=(",", ":")` makes the output deterministic
    independent of dict insertion order or whitespace.
    """
    return json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)


def params_hash(params: dict[str, Any]) -> str:
    blob = _canonical_json(params).encode("utf-8")
    return hashlib.blake2b(blob, digest_size=16).hexdigest()


def current_game_version(redis_client: Any, game_id: int) -> int:
    raw = redis_client.get(GAME_VERSION_KEY.format(game_id=game_id))
    return int(raw) if raw is not None else 0


def bump_game_version(redis_client: Any, game_id: int) -> int:
    """Increment a game's cache version. Returns the new version."""
    return int(redis_client.incr(GAME_VERSION_KEY.format(game_id=game_id)))


def get_or_set(
    *,
    redis_client: Any,
    game_id: int,
    params: dict[str, Any],
    loader: Callable[[], Any],
    ttl_seconds: int,
) -> tuple[Any, bool]:
    """Return (result, cache_hit). On miss, calls `loader()` and writes back."""
    ver = current_game_version(redis_client, game_id)
    key = QUERY_KEY.format(game_id=game_id, ver=ver, h=params_hash(params))

    cached = redis_client.get(key)
    if cached is not None:
        try:
            return json.loads(cached), True
        except json.JSONDecodeError:
            # Corrupt cache entry — fall through and re-populate.
            pass

    result = loader()
    try:
        redis_client.set(key, json.dumps(result, default=str), ex=ttl_seconds)
    except (TypeError, ValueError):
        # Loader returned a non-JSON-serializable value; surface immediately.
        raise
    return result, False
