# API Reference

All public endpoints are mounted under `/api/v1/`. Requests and responses are JSON. Unknown query/body fields are rejected with `400 invalid_request`.

## Endpoints

### `POST /api/v1/sessions` — issue a session token

Required *before* every score submission.

**Body**

```json
{
  "game": "tetris-classic",
  "client_info": { "device_model": "Pixel 8", "app_version": "1.2.3" }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `game` | string (slug) | yes | Game slug as registered in admin. |
| `client_info` | object | no | Hints stored alongside the score's `device_info`. Allowed keys: `device_model`, `app_version`, `game_version`, `screen_resolution`, `locale`, `platform`. Everything else is dropped. |

**Response (201)**

```json
{
  "session_token": "eyJ...opaque...",
  "expires_at": "2026-05-20T13:34:56Z"
}
```

**Rate limit:** 10/min, 100/hour per IP.

**Errors:** `400 invalid_request`, `404 game_not_found`, `429 rate_limited`, `413 payload_too_large`.

---

### `POST /api/v1/scores` — submit a score

Requires `Authorization: Bearer <token>`. Single-use: the token is consumed regardless of whether the submission ultimately validates. (If validation fails, the client should request a fresh token and retry.)

**Headers**

```
Authorization: Bearer eyJ...
Content-Type: application/json
```

**Body**

```json
{
  "game": "tetris-classic",
  "player_name": "Ren",
  "score": 31415,
  "played_at": "2026-05-20T12:34:56Z",
  "seed": "daily-2026-05-20",
  "custom_data": {"combo": 47, "perfect": true},
  "client_info": {"app_version": "1.2.3"}
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `game` | string (slug) | yes | Must match the slug the token was issued for. |
| `player_name` | string | yes | 1–32 chars after server-side normalization. NFC; control/bidi/zero-width chars stripped. |
| `score` | number | yes | Must be within the game's `min_score`/`max_score` if set. |
| `played_at` | ISO 8601 string | no | Server clock-skew tolerance is 60s. Must not predate the session token's issuance. |
| `seed` | string | no | `[A-Za-z0-9_-]{1,64}`. For daily-challenge style leaderboards. |
| `custom_data` | object | no | Per-game arbitrary fields. Validated against `Game.meta.custom_fields` if declared. ≤32 keys, ≤256 chars per string. |
| `client_info` | object | no | Same allow-list as `/sessions`. |

**Response (201)**

```json
{"id": 1234}
```

**Rate limit:** 30/min, 300/hour per IP.

**Errors:**
- `400 invalid_request` — schema validation failed.
- `400 invalid_player_name` — name empty after sanitization, or too long.
- `400 score_out_of_bounds` — outside per-game min/max.
- `400 invalid_seed` — bad charset/length.
- `400 invalid_custom_data` — schema mismatch.
- `400 invalid_played_at` — naive datetime, future, or predates token issuance.
- `401 invalid_session` — missing/bad/expired token, replay attempt, or token bound to a different game.
- `404 game_not_found`.
- `413 payload_too_large` — body exceeds 4 KB.
- `429 rate_limited`.

---

### `GET /api/v1/champions` — daily-seed win tally per player

For each distinct seed observed in the (optional) time window, awards a "win" to the player with the best score on that seed. Returns players sorted by win count, descending. Useful for "who's the king of the daily challenge" boards.

**Query parameters**

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `game` | string (slug) | _required_ | |
| `since` | ISO 8601 datetime | _none_ | Inclusive lower bound on `submitted_at`. Naive datetimes are assumed UTC. Use `Z` suffix in query strings (not `+00:00` — the `+` needs URL-encoding). |
| `until` | ISO 8601 datetime | _none_ | Exclusive upper bound on `submitted_at`. Must be > `since` if both are set. |
| `page` | int | `1` | |
| `page_size` | int | `25` | Max `50`. |

**Response (200)**

```json
{
  "game": "tetris-classic",
  "since": "2026-01-01T00:00:00Z",
  "until": null,
  "total_seeds": 42,
  "page": 1,
  "page_size": 25,
  "total": 8,
  "results": [
    {"rank": 1, "player_name": "Ren", "wins": 17},
    {"rank": 2, "player_name": "Ana", "wins": 12}
  ]
}
```

`total_seeds` is the number of distinct seeds in the window. `total` is the number of distinct champions (paginated). Scores with `seed = NULL` are ignored entirely — this endpoint is for seeded daily-challenge play. Soft-deleted scores are excluded (so soft-deleting a cheater's winning score promotes the runner-up).

Tie-breaking within a seed: better score wins, then earlier `submitted_at`, then lower `id`. Same ordering as the leaderboard query.

Uses the same Redis version-key cache as `/leaderboards` — a score insert or admin moderation action invalidates both endpoints' caches for the affected game. `X-Cache: HIT|MISS` indicates whether the response was served from cache.

**Rate limit:** 60/min per IP.

**Errors:** `400 invalid_request` (unknown param, page_size>50, since>=until), `404 game_not_found`, `429 rate_limited`.

---

### `GET /api/v1/leaderboards` — query scores

Read-only, cacheable (Redis-backed), no auth required.

**Query parameters**

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `game` | string (slug) | _required_ | |
| `range` | enum | `all-time` | One of `all-time`, `yearly`, `monthly`, `weekly`, `daily`, `hourly`. Period is computed in the game's IANA timezone. ISO week (Monday start). |
| `seed` | string | _none_ | Exact match against `Score.seed`. **See note below** — omitting `seed` returns only non-seeded scores. |
| `name` | string | _none_ | Case-insensitive substring match on `player_name`. |
| `sort` | enum | `score` | `score` (uses game's `score_direction`), `submitted_at`, or `played_at` (both descending). |
| `page` | int | `1` | |
| `page_size` | int | `25` | Max `50`; `>50` is hard-rejected. |

> **Seed filtering.** A score's `seed` segregates which board it belongs to. The main leaderboard (no `seed` param) returns **only scores submitted with no seed** (`seed IS NULL`) — i.e. normal play. To see a daily-challenge board, pass that challenge's `seed`, which returns **only** scores for that seed. There is no way to mix seeded and non-seeded scores in one response; this keeps daily challenges from polluting the all-time board and vice-versa.

**Response (200)**

```json
{
  "page": 1,
  "page_size": 25,
  "total": 1234,
  "results": [
    {
      "rank": 1,
      "id": 9876,
      "player_name": "Ren",
      "score": 31415.0,
      "submitted_at": "2026-05-20T12:34:56+00:00",
      "played_at": "2026-05-20T12:30:00+00:00",
      "seed": "daily-2026-05-20",
      "device_info": {"os": "Windows", "browser": "Chrome"},
      "custom_data": {"combo": 47, "perfect": true}
    }
  ]
}
```

A non-standard header `X-Cache: HIT` or `X-Cache: MISS` indicates whether the response was served from the Redis cache.

**Rate limit:** 60/min per IP.

**Errors:** `400 invalid_request`, `404 game_not_found`, `429 rate_limited`.

---

## Stable error codes

The response body for any error is `{"error": "<code>", "detail": "<optional>"}`. The `detail` is omitted by default to avoid leaking which check fired. Server logs have full detail. Codes:

| Code | HTTP | Meaning |
|---|---|---|
| `invalid_request` | 400 | Schema validation, unknown query param, malformed JSON. |
| `invalid_player_name` | 400 | Player name empty after normalization or too long. |
| `score_out_of_bounds` | 400 | Score outside per-game min/max. |
| `invalid_seed` | 400 | Bad charset/length on seed. |
| `invalid_custom_data` | 400 | custom_data violates the per-game schema. |
| `invalid_played_at` | 400 | played_at is naive, in the future, or predates the token. |
| `invalid_session` | 401 | Bad/missing/expired/already-consumed session token, or token bound to a different game. |
| `game_not_found` | 404 | Slug doesn't match an active (non-archived) game. |
| `method_not_allowed` | 405 | |
| `payload_too_large` | 413 | Body > 4 KB. |
| `rate_limited` | 429 | Per-IP rate limit exceeded. |
| `internal_error` | 500 | |

---

## Caching

`GET /api/v1/leaderboards` results are cached in Redis under a key derived from `game_id`, a per-game version counter, and a canonical hash of the query parameters. Every successful score submission or admin moderation action increments the per-game version counter, which invalidates all of that game's cached query results instantly. The fallback TTL is 5 minutes by default (`CACHE_TTL_SECONDS`).

---

## Rate limits

All public endpoints are rate-limited per IP. The `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers are returned on every public response so clients can self-throttle.

Limits (overridable via env vars):

| Endpoint | Default |
|---|---|
| `POST /sessions` | `10/minute;100/hour` (`RATELIMIT_SESSIONS`) |
| `POST /scores` | `30/minute;300/hour` (`RATELIMIT_SCORES`) |
| `GET /leaderboards` | `60/minute` (`RATELIMIT_LEADERBOARDS`) |
| `GET /champions` | `60/minute` (`RATELIMIT_CHAMPIONS`) |
| Admin login | `5/minute;20/hour` (`RATELIMIT_ADMIN_LOGIN`) |

If you're behind a reverse proxy, set `TRUSTED_PROXY_HOPS=1` (the default) so the app reads the client IP from `X-Forwarded-For`. Set to `0` if you're not behind a proxy.
