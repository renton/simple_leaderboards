# Simple Leaderboards

A small self-hosted leaderboards service for video games. One Flask app + Postgres + Redis, orchestrated by Docker Compose. Comes with a built-in admin UI for managing games and moderating scores, and a public JSON API for game clients to submit and read scores.

**Design goals:** simple to host, simple to integrate, hardened against casual cheating and abuse. **Non-goals:** federation, multi-tenant SaaS, motivated reverse-engineer-proof anti-cheat.

---

## Contents

- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Bootstrapping the first admin](#bootstrapping-the-first-admin)
- [Integrating from your game](#integrating-from-your-game)
- [Production deployment](#production-deployment)
- [What's in / out of scope](#whats-in--out-of-scope)
- [Threat model](#threat-model)

---

## Quickstart

Requires Docker + Docker Compose v2.

```bash
git clone <this repo>
cd simple_leaderboards

# 1. Configure secrets
cp .env.example .env
# Generate strong secrets and edit .env:
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> .env
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))" >> .env
# (Remove the placeholder lines from .env after appending real ones, or just edit in place.)

# 2. Bring up the stack
docker compose up -d --build

# 3. Apply migrations
docker compose exec app flask db upgrade

# 4. Create the first admin
docker compose exec app flask create-admin --username root

# 5. Visit the admin UI
open http://127.0.0.1:8000/admin/login
```

After signing in, create your first game under **Games → + New game**, set its slug (e.g. `tetris-classic`), timezone, score direction, and min/max bounds.

---

## Configuration

All configuration is via environment variables (or a `.env` file). The required ones are marked **required** — the app refuses to start without them.

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | _none_ | **required.** HMAC signing key for session tokens and Flask sessions. Rotate to invalidate all outstanding tokens. |
| `POSTGRES_USER` | `leaderboards` | App's database role (non-superuser recommended). |
| `POSTGRES_PASSWORD` | _none_ | **required.** Database password. |
| `POSTGRES_DB` | `leaderboards` | Database name. |
| `POSTGRES_HOST` | `db` | Compose service name. |
| `POSTGRES_PORT` | `5432` | |
| `REDIS_URL` | `redis://redis:6379/0` | Redis URL for cache + session nonces. |
| `REDIS_RATELIMIT_URL` | `redis://redis:6379/1` | Separate Redis logical DB for rate-limit state. |
| `SESSION_TTL_SECONDS` | `3600` | How long a session token is valid before submission. |
| `CACHE_TTL_SECONDS` | `300` | Fallback TTL for cached leaderboard responses. |
| `MAX_PLAYED_AT_SKEW_SECONDS` | `60` | Clock-skew tolerance for `played_at` checks. |
| `TRUSTED_PROXY_HOPS` | `1` | Set to `0` if you're NOT behind a reverse proxy. |
| `SESSION_COOKIE_SECURE` | `1` | Set to `0` for local HTTP-only development. **MUST** be `1` in production behind TLS. |
| `ADMIN_BOOTSTRAP_PASSWORD` | _unset_ | Optional one-shot password used by `flask create-admin --password-env ADMIN_BOOTSTRAP_PASSWORD`. Unset after first use. |

---

## Bootstrapping the first admin

There is no public sign-up. The first admin is created via CLI:

```bash
# Interactive (recommended)
docker compose exec app flask create-admin --username root
# Prompts for password (min 12 chars).

# Non-interactive (CI / automation)
docker compose run --rm -e ADMIN_BOOTSTRAP_PASSWORD='<...>' app \
    flask create-admin --username root --password-env ADMIN_BOOTSTRAP_PASSWORD
```

Subsequent admins can be created via the **Admins → + New admin** page once you're signed in.

---

## Integrating from your game

The public API is exactly three endpoints under `/api/v1/`:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/sessions` | Get a single-use session token bound to a game. |
| `POST` | `/scores` | Submit a score (requires `Authorization: Bearer <token>`). |
| `GET` | `/leaderboards` | Read scores for a game with filters + pagination. |

See [`docs/api.md`](docs/api.md) for full reference (parameters, error codes, rate limits).

### The two-call submission flow

A score submission is always two HTTP calls: get a token, then submit with it. The token is short-lived and single-use; this prevents replay and trivial spoofing from scripted clients.

```bash
# 1. Get a token at the *start* of the game run.
TOKEN=$(curl -fsS -X POST http://localhost:8000/api/v1/sessions \
    -H 'Content-Type: application/json' \
    -d '{"game": "tetris-classic"}' \
  | jq -r .session_token)

# 2. When the game ends, submit the score.
curl -fsS -X POST http://localhost:8000/api/v1/scores \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{
      "game": "tetris-classic",
      "player_name": "Ren",
      "score": 31415,
      "seed": "daily-2026-05-20",
      "custom_data": {"combo": 47, "perfect": true}
    }'

# Response: {"id": 1234}
```

### Reading the leaderboard

```bash
# All-time top 25.
curl 'http://localhost:8000/api/v1/leaderboards?game=tetris-classic'

# Daily challenge with a seed.
curl 'http://localhost:8000/api/v1/leaderboards?game=tetris-classic&range=daily&seed=daily-2026-05-20'

# Search for a player.
curl 'http://localhost:8000/api/v1/leaderboards?game=tetris-classic&name=ren'

# Paginate.
curl 'http://localhost:8000/api/v1/leaderboards?game=tetris-classic&page=2&page_size=50'
```

### Integration notes for game clients

- The session token is opaque to clients — don't try to parse it.
- Request a *fresh* token before each score submission. Tokens are single-use.
- Tokens are bound to a specific game (by slug); submitting a score for a different game returns `401 invalid_session`.
- `played_at` is optional, in ISO 8601 (`2026-05-20T12:34:56Z`). It must be ≥ the token's issuance time and ≤ now + 60s of skew tolerance.
- `seed` is for daily-challenge style leaderboards. Free-form `[A-Za-z0-9_-]` up to 64 chars; leave it `null` for normal play.
- `custom_data` is any small JSON object (≤32 keys, ≤256 chars per string value). The admin may pin a schema per game (see `docs/data_models.md`).

---

## Production deployment

The compose file is production-usable, with these requirements:

1. **Put it behind a reverse proxy with TLS.** Do NOT expose Flask directly to the public internet. The app listens on `127.0.0.1:8000` by default. Example Caddyfile:

   ```caddy
   leaderboards.example.com {
       reverse_proxy 127.0.0.1:8000
   }
   ```

   Caddy handles TLS certificates automatically.

2. **Keep `/admin/` off the public internet** if you can. Either:
   - Restrict by IP allow-list at the proxy, or
   - Put it behind a VPN / Tailscale, or
   - Add HTTP basic auth at the proxy in front of `/admin/`.

3. **Remove the localhost Postgres port binding** if you don't need `flask db migrate` from the host. In `docker-compose.yml`, remove the `ports:` block under the `db:` service.

4. **Back up the Postgres volume** on a schedule. Test the restore.

5. **Use a dedicated, non-superuser Postgres role** (the compose file does this by default — the `leaderboards` role only has access to its own database).

6. **Set `SESSION_COOKIE_SECURE=1`** (the default). Browsers refuse to send the session cookie over plain HTTP when this is on, so set up TLS first.

7. **Rotate `SECRET_KEY`** if you ever suspect compromise. All outstanding session tokens become invalid; players' next score submission will simply fail with `invalid_session` and the game client requests a fresh token automatically.

---

## What's in / out of scope

**In scope (v1):**
- Three-endpoint public API with session-token-guarded score submission.
- Per-game min/max score bounds + named-character / control-char filtering on player names.
- Admin UI for game management, score moderation (soft-delete + restore), and admin-user management.
- Per-game cache invalidation, range queries respecting per-game IANA timezone.

**Out of scope (deliberately deferred):**
- 2FA for admins (model has room for it).
- Email-based password reset (admins reset each other via CLI).
- Statistical / ML anti-cheat.
- Minimum-game-duration anti-cheat (a per-game knob is easy to add later).
- Per-game shared-secret API keys for multi-tenant hosting.
- Audit-log UI (audit rows ARE written to `admin_actions` — query via SQL).
- Custom-field filtering in the admin dashboard (display only in v1).
- Background workers / async ingestion (writes are synchronous; fine at typical self-hosted scale).

---

## Threat model

This service is hardened against:
- Casual cheating (random POSTs, replays of captured tokens, oversized payloads, control-char player names, params-blow-up DoS of the cache).
- Common admin attacks (brute-force login, session fixation, CSRF, open redirects, stored XSS via player names).

It is **not** hardened against:
- A motivated reverse-engineer who decompiles the game client and submits arbitrary in-bounds scores. There is no anti-tamper that survives someone owning the player's machine.
- DDoS at the network layer (put a CDN / WAF in front if that matters).
- Side-channel attacks on the hashing or HMAC code (mitigated where stdlib offers it; not separately audited).

For a small self-hosted leaderboard, the realistic attack vectors are admin-account compromise (so set a strong password and keep `/admin/` off the public internet) and casual cheating (which bounds + session tokens raise the cost of).

---

## Running tests

```bash
# One-off: bring up the compose stack and create the test DB.
docker compose up -d db redis
docker compose exec db createdb -U leaderboards leaderboards_test

# Run the suite from the host venv (Python 3.12+).
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

set -a; source .env; set +a
export POSTGRES_HOST=127.0.0.1
.venv/bin/pytest
```

The test suite uses `fakeredis` for cache/session tests but a real Postgres for queries that rely on JSONB.
