# CLAUDE.md — agent ramp-up notes

This file is for Claude (or any AI assistant) picking up work on this repo. The user-facing docs live in [`README.md`](README.md), [`docs/api.md`](docs/api.md), and [`docs/data_models.md`](docs/data_models.md) — don't duplicate them here. This file is for the *non-obvious* things.

## What this is, in one breath

Self-hosted leaderboards service. Three docker-compose containers (Flask + Postgres + Redis). Public API is four endpoints under `/api/v1/`: `POST /sessions` (issue token), `POST /scores` (consume token + insert), `GET /leaderboards` (cached read), `GET /champions` (daily-seed win tally, cached). Server-rendered admin UI at `/admin/` for game/admin CRUD and score moderation. v1.

## How to run / develop

```bash
# First-time setup
cp .env.example .env
# Edit .env: fill SECRET_KEY and POSTGRES_PASSWORD (any value for local dev).
docker compose up -d --build
docker compose exec app flask db upgrade
docker compose exec app flask create-admin --username root  # interactive

# Day-to-day
docker compose up -d           # bring up
docker compose logs -f app     # tail
docker compose down            # stop (keeps volumes)
docker compose down -v         # nuke volumes (loses data)
```

The app is at `http://127.0.0.1:8000`. Postgres is bound to `127.0.0.1:5432` deliberately for host-side `flask db migrate`; remove that `ports:` block from `docker-compose.yml` in production behind a remote proxy. Redis is NOT host-bound — use `docker compose exec redis redis-cli` to inspect.

## Tests

```bash
# One-time: test DB must exist on the docker postgres.
docker compose exec db createdb -U leaderboards leaderboards_test

# Setup venv (once)
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Run
set -a; source .env; set +a
export POSTGRES_HOST=127.0.0.1
.venv/bin/pytest              # 154 tests, ~13s
.venv/bin/pytest tests/test_smoke.py -v   # one end-to-end test
.venv/bin/pytest -k cache     # filter
```

**Test DB caveat:** `docker compose down -v` deletes the `leaderboards_test` DB too. After a volume wipe, recreate it (`docker compose exec db createdb -U leaderboards leaderboards_test`) before running pytest.

**Pure-logic tests** (no DB): `test_time_ranges`, `test_name_and_device`, `test_session_tokens`, `test_cache`, `test_sanity`. These run with `fakeredis` and no Postgres.

**DB tests** need real Postgres (JSONB-dependent). `tests/conftest.py` truncates all tables before every test via `TRUNCATE ... RESTART IDENTITY CASCADE`.

## Architecture map

```
app/
├── __init__.py             create_app() factory. Order matters: db.init_app →
│                           import models → migrate.init_app → … → install_security_headers
├── config.py               Config dataclass + load_config() + TestConfig
├── extensions.py           db, migrate, login_manager, csrf, limiter, redis_client singletons
├── cli.py / cli_commands.py  `flask create-admin` (Click command)
├── security_headers.py     after_request: CSP, X-Frame-Options, etc.
├── models/                 SQLAlchemy 2.x Mapped[] models
│   ├── base.py             shared declarative base + utcnow_column helper
│   ├── user.py             AdminUser (Argon2 helpers, lockout state)
│   ├── game.py             Game (validators for slug/timezone/direction)
│   ├── score.py            Score (composite indexes; soft-delete via deleted_at)
│   └── admin_action.py     audit log
├── schemas/                Pydantic v2 (extra="forbid")
├── services/               PURE LOGIC. Avoid Flask imports where possible.
│   ├── time_ranges.py      range_to_bounds() — zoneinfo-based UTC bounds
│   ├── session_tokens.py   issue / verify_and_consume (itsdangerous + redis nonce)
│   ├── cache.py            get_or_set + bump_game_version + params_hash
│   ├── sanity.py           all score-submission rejection logic
│   ├── name_normalize.py   NFC + strip bidi/zero-width/control
│   ├── device_info.py      ua-parser merge with client-provided hints
│   ├── leaderboard_query.py  SQLAlchemy select builder
│   └── champions.py        per-seed winner → win tally per player (window fn + group-by)
├── api/                    public JSON API, csrf-exempt blueprint
│   ├── __init__.py         api_bp + side-effect imports
│   ├── errors.py           stable error codes table + ApiError handler
│   ├── sessions.py / scores.py / leaderboards.py / champions.py
├── admin/                  server-rendered UI, @login_required at blueprint level
│   ├── __init__.py         admin_bp + before_request login enforcement
│   ├── forms.py            WTForms classes
│   ├── auth.py / dashboard.py / games.py / users.py / scores.py
│   └── api_test.py         read-only page to build/fire /leaderboards + /champions queries (admin-only)
├── templates/admin/        Jinja2 templates (always autoescape on; never |safe)
└── static/
    ├── css/app.css         single minimal stylesheet
    ├── js/api_test.js      vanilla JS for the API-test page (NO build step; no React/npm)
    └── favicon.svg         ascending-bars mark
```

**No frontend build step / no React.** The admin UI is 100% server-rendered Jinja2.
The only JS is `static/js/api_test.js`, a plain `<script>` served as a static
asset. There is no `package.json`, bundler, or `npm`/`yarn` — nothing to "build"
or "refresh." Edit the `.js`/`.css`/templates and reload the page.

## Load-bearing files (highest care if changing)

- `app/services/session_tokens.py` — auth correctness; replay protection
- `app/services/sanity.py` — every public score rejection lives here
- `app/services/leaderboard_query.py` — the only SQL the public API reads
- `app/services/champions.py` — window-function tally that rides the same cache scheme
- `app/services/cache.py` — version-key invalidation scheme
- `app/services/time_ranges.py` — DST/ISO-week correctness
- `app/api/scores.py` — orchestrates the token-consume → sanity → insert → cache-bump flow
- `app/models/score.py` — composite indexes the leaderboard query depends on

## Conventions and patterns already established

- **SQLAlchemy 2.x `Mapped[]` declarative style.** No legacy `Column(...)` syntax. No raw SQL — ORM/Core only.
- **Pydantic v2 with `extra="forbid"`** on every public input schema. Unknown fields are 400, by design (keeps cache keyspace bounded and rejects probing).
- **Stable error codes**, not free-form messages. See `app/api/errors.py`. The error code is the public contract; the `detail` field is omitted by default and goes to server logs only.
- **Services are framework-agnostic.** They take a `redis_client` / `session` / `secret_key` as parameters instead of pulling from Flask context. This is what makes them unit-testable without a Flask app.
- **Time everywhere is `TIMESTAMP WITH TIME ZONE` in UTC.** Game timezone is only used to compute range boundaries in Python before passing UTC datetimes to SQL. No `AT TIME ZONE` in queries.
- **Cache keys**: `lb:game:{id}:ver` (integer version) and `lb:q:{id}:v{ver}:{params_hash}`. Bump the version to invalidate everything for a game. Both `/leaderboards` and `/champions` share the prefix; their params dicts differ (champions params include `"_endpoint": "champions"`) so cache entries don't collide.
- **Soft-delete only.** Public queries always filter `deleted_at IS NULL`. Admin moderation writes an `AdminAction` audit row.
- **Audit rows on every state-changing admin action**. There's no UI yet — query via SQL.
- **CSRF**: globally on; `csrf.exempt(api_bp)` for the public API blueprint (called in `create_app()`).
- **Rate limit**: Flask-Limiter, Redis-backed in prod (`memory://` in tests). Set `RATELIMIT_ENABLED=False` in test config or per-IP limits trip after a handful of test requests (they all come from `127.0.0.1`).

## Decisions explicitly locked with the user

1. **Score direction is per-game** (`asc`/`desc` enum on `Game`), not "always desc, invert client-side." Affects `leaderboard_query.py` sort logic.
2. **Game identity in the public API is the slug**, not the integer PK. Slug regex `^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$` validated on insert.
3. **Soft-delete + audit row** for moderation, not hard delete.
4. **No minimum-duration anti-cheat in v1.** Defer until a real game asks for it.
5. **Four public endpoints**, not two — `/sessions` is a protocol prerequisite, `/champions` is a derived view over seeded play. Both documented in README. Don't "simplify" by removing them.
6. **Champions endpoint computes on read, not via an aggregate table.** The SQL is a CTE with `ROW_NUMBER() OVER (PARTITION BY seed ORDER BY score)` + group-by. Rides the partial index `ix_scores_champions` on `(game_id, submitted_at, seed) WHERE seed IS NOT NULL AND deleted_at IS NULL`. An aggregate table was considered and deferred — soft-delete consistency would require recomputing per-seed leaders anyway, which is the same query.
7. **`/leaderboards` segregates seeded vs non-seeded scores.** With no `seed` param it filters `seed IS NULL` (normal play only); with a `seed` it returns only that seed. There is intentionally no "all scores regardless of seed" view — daily challenges must not pollute the all-time board. See `app/services/leaderboard_query.py` (the `else: base.where(Score.seed.is_(None))` branch). If you change this, update `tests/test_smoke.py` and `docs/api.md` together.

## Common gotchas I hit during the initial build

- `metadata` is reserved on SQLAlchemy declarative bases. `Game.meta` is the Python attribute; the DB column is named `"metadata"` via `mapped_column("metadata", JSONB, ...)`. Don't try to "fix" the inconsistency.
- `ua-parser` API is `from ua_parser import user_agent_parser; user_agent_parser.Parse(ua)`. Returns a `dict`, not an object. Do NOT use `from ua_parser import parse`.
- Alembic's `flask db migrate` produces "No changes in schema detected" if models aren't imported by `create_app()`. The line `from app import models  # noqa: F401` in `app/__init__.py` is load-bearing.
- WTForms validators that fail don't enter the `if form.validate_on_submit():` branch — fall-through must explicitly return 400 on `request.method == "POST"`. See `app/admin/games.py` for the pattern.
- `flask-limiter` in-memory storage warning at boot: harmless if it appears in scripts, but for production make sure `RATELIMIT_STORAGE_URI` is set (it is, via `config.py`).
- Tests share a single fake client IP, so rate limits trip if enabled. `conftest.py` sets `RATELIMIT_ENABLED=False` in TestConfig.
- `Game.meta` defaults to `dict` in Python and `'{}'` in `server_default`. When constructing in code, pass `meta={}` explicitly to avoid stale-default-dict bugs.

## What's deliberately out of scope (do NOT add without a real ask)

- 2FA for admins (DB has room — `password_hash`/`last_login_at` only, no `totp_secret` yet)
- Email password reset (admins reset each other via CLI by deleting + recreating)
- Statistical / ML anti-cheat
- Audit-log UI (rows are written; no admin page)
- Custom-data filtering in the admin dashboard (display only)
- Per-game shared-secret API keys for multi-tenant
- Background workers / async ingestion
- Sliding-window or token-bucket implementations more sophisticated than Flask-Limiter's defaults

If a request looks like one of these, surface that it's an explicit v2 decision before implementing.

## Where to look first when…

| You need to… | Start here |
|---|---|
| Add a new rejection code on score submit | `app/services/sanity.py` + `app/api/errors.py` (code table) + the README/`docs/api.md` |
| Change how the cache invalidates | `app/services/cache.py` — currently version-key scheme |
| Add a new range type (e.g. "biweekly") | `app/services/time_ranges.py` (VALID_RANGES + handler) + Pydantic Literal in `app/schemas/leaderboards.py` |
| Adjust how champions are computed | `app/services/champions.py` (window function + group-by); migration `2b41ac9d5e3a` added the partial index |
| Add a new admin moderation action | `app/admin/scores.py` for the pattern, including the audit-row write |
| Adjust security headers / CSP | `app/security_headers.py` |
| Add a new admin form field | `app/admin/forms.py` + the matching template under `app/templates/admin/` |
| Tweak rate limits | `app/config.py` `RATELIMIT_*` keys; per-route via `current_app.config[...]` |
| Add a CLI command | `app/cli_commands.py` + register in `app/cli.py` |

## Reflexes when picking back up

- Read `README.md` for the user story, then this file for context.
- `git log --oneline` for recent activity.
- `.venv/bin/pytest -q` should always be green. If it's not, that's the first thing to fix.
- The compose stack should start clean from `docker compose up -d --build` after `down -v`. If `flask db upgrade` won't run, the test DB likely also doesn't exist — recreate both.
- Don't add a comment unless removing it would confuse a future reader. Most explanation belongs in this file or a docstring, not inline.
