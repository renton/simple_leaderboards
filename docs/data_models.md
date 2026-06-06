# Data Models

Four tables. All timestamps are stored as `TIMESTAMP WITH TIME ZONE` in UTC.

## AdminUser (`admin_users`)

A login account for the admin UI. Public players are NOT represented in this table — they're just unauthenticated `player_name` strings on `Score` rows.

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `username` | `varchar(64)` unique, indexed | Login identifier. |
| `password_hash` | `varchar(255)` | Argon2id hash. Set via `set_password()`. |
| `created_at` | `timestamptz` | Server-default `now()`. |
| `last_login_at` | `timestamptz` nullable | Updated on successful login. |
| `failed_login_attempts` | `int` default 0 | Counter for lockout. Reset on success. |
| `locked_until` | `timestamptz` nullable | Account is locked until this time. |

### Lockout behavior

After `ADMIN_MAX_FAILED_LOGINS` (default 10) consecutive failures, the account is locked for `ADMIN_LOCKOUT_MINUTES` (default 15). A correct password during the lockout window still returns `423 Locked`. A successful login clears both counter and lock.

---

## Game (`games`)

A leaderboard-bearing game registered by an admin. Game clients identify a game by its **slug** in API calls.

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | Internal identifier. |
| `slug` | `varchar(64)` unique, indexed | URL-safe identifier used in the public API. Regex: `^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$`. |
| `name` | `varchar(128)` | Display name. |
| `timezone` | `varchar(64)` | IANA timezone string (e.g. `America/New_York`). Determines "today", "this week", etc. on range filters. Validated against `zoneinfo.ZoneInfo` on insert. |
| `score_direction` | `varchar(4)` | `'desc'` (higher wins, default) or `'asc'` (lower wins, e.g. racing time). |
| `min_score` | `numeric(20,6)` nullable | Minimum allowed score. If set, submissions below this are rejected. |
| `max_score` | `numeric(20,6)` nullable | Maximum allowed score. If set, submissions above this are rejected. |
| `metadata` | `jsonb` | Free-form JSON. May declare a `custom_fields` schema (see below). The Python attribute is `Game.meta` because `metadata` is reserved by SQLAlchemy. |
| `archived` | `bool` | When true, the game is hidden from the public API (`/api/v1/sessions` and `/api/v1/leaderboards` both return `404`) and from the public privacy pages. Existing scores are preserved. |
| `created_at` | `timestamptz` | |
| `operator_name` | `varchar(128)` nullable | Operator/developer name shown on the public privacy policy. Falls back to generic wording when unset. |
| `contact_email` | `varchar(254)` nullable | Privacy contact email shown (and `mailto:`-linked) on the policy. Loosely validated. |
| `privacy_policy_extra` | `text` nullable | Optional extra clauses appended verbatim (HTML-escaped, newlines preserved) as a final policy section. |
| `privacy_updated_at` | `timestamptz` nullable | Stamped on each game edit; shown as the policy's "Effective date" (falls back to `created_at`). |

The public privacy pages live at `GET /privacy` (index) and `GET /privacy/<slug>` (per-game policy) — no auth. The policy text is a standard template parameterized by the fields above; see `app/templates/public/privacy_policy.html`.

### `metadata.custom_fields` schema

To validate `custom_data` on submitted scores, declare a schema in the game's metadata:

```json
{
  "custom_fields": {
    "combo": {"type": "integer", "required": false},
    "perfect": {"type": "boolean"},
    "level": {"type": "string", "required": true}
  }
}
```

Supported types: `string`, `integer`, `number` (int or float), `boolean`. Unknown fields in a submission are rejected when a schema is declared. If you omit `custom_fields` entirely, the API accepts any small JSON object (≤32 keys, ≤256 chars per string value).

---

## Score (`scores`)

One row per submitted score.

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `game_id` | `int` FK → games(id) `ON DELETE CASCADE` | |
| `player_name` | `varchar(32)` | Normalized: NFC + control/bidi/zero-width stripped, trimmed, ≤32 chars. |
| `score` | `numeric(20,6)` | The score value. Wide enough for racing milliseconds and astronomic arcade scores. |
| `submitted_at` | `timestamptz` server-default `now()` | Authoritative server time. Used for range filters. |
| `played_at` | `timestamptz` nullable | Client-asserted gameplay time. Advisory; range filters use `submitted_at`. |
| `seed` | `varchar(64)` nullable | Daily-challenge seed. `[A-Za-z0-9_-]{1,64}`. Null for normal play. |
| `device_info` | `jsonb` | UA-parsed (`os`, `browser`, `device`) + client-provided (`device_model`, `app_version`, `game_version`, `screen_resolution`, `locale`, `platform`). UA wins for OS/browser. |
| `custom_data` | `jsonb` | Per-game arbitrary JSON. Validated against `Game.meta.custom_fields` if declared. |
| `deleted_at` | `timestamptz` nullable | Soft-delete marker. Rows with `deleted_at IS NOT NULL` are excluded from the public API and admin leaderboard view. |

### Indexes

- `ix_scores_game_id` — single-column FK index.
- `ix_scores_game_submitted` — `(game_id, submitted_at)`. Range queries.
- `ix_scores_game_score` — `(game_id, score)`. Top-N by score.
- `ix_scores_game_seed_score` — `(game_id, seed, score)`. Daily-challenge leaderboards.
- `ix_scores_game_deleted` — `(game_id, deleted_at)`. Fast exclusion of soft-deleted rows.
- `ix_scores_player_name` — substring name search (ILIKE).

---

## AdminAction (`admin_actions`)

Audit log. Written by the application on state-changing admin actions; never written by the public API.

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `admin_user_id` | `int` FK → admin_users(id) `ON DELETE SET NULL` | The actor. May be null if the admin row was later deleted. |
| `action` | `varchar(64)`, indexed | Examples: `game.create`, `game.update`, `score.soft_delete`, `score.restore`, `admin.create`. |
| `target_type` | `varchar(32)` nullable | E.g. `"game"`, `"score"`, `"admin_user"`. |
| `target_id` | `int` nullable | PK of the target row. |
| `details` | `jsonb` | Action-specific context (slug, player_name, score, etc.). |
| `created_at` | `timestamptz` | |

There is no UI for browsing audit rows in v1. Query directly:

```bash
docker compose exec db psql -U leaderboards leaderboards \
    -c "SELECT created_at, action, target_type, target_id, details FROM admin_actions ORDER BY id DESC LIMIT 50;"
```

---

## Relationships

```
admin_users ──┐
              ├──< admin_actions (admin_user_id, target_type, target_id)
              │
games ───────┬──< scores (game_id)
             │
             │
```

Soft-deletes on scores never cascade. Hard-deleting a game cascades to its scores.
