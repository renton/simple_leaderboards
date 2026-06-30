# Simple Leaderboards

A small self-hosted leaderboards service for video games. One Flask app + Postgres + Redis, orchestrated by Docker Compose. Comes with a built-in admin UI for managing games and moderating scores, and a public JSON API for game clients to submit and read scores.

**Design goals:** simple to host, simple to integrate, hardened against casual cheating and abuse. **Non-goals:** federation, multi-tenant SaaS, motivated reverse-engineer-proof anti-cheat.

---

## Contents

- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Bootstrapping the first admin](#bootstrapping-the-first-admin)
- [Integrating from your game](#integrating-from-your-game)
- [Privacy policy](#privacy-policy)
- [Production deployment](#production-deployment)
- [What's in / out of scope](#whats-in--out-of-scope)
- [Threat model](#threat-model)
- [Running tests](#running-tests)
- [License & disclaimer](#license--disclaimer)

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
| `POSTGRES_PASSWORD` | `changeme-localdev-only` | **Always set this** for any real deployment. The default exists so that an override which deletes the bundled `db` service can apply cleanly — compose interpolation can't be skipped on a service that's about to be removed. The default is intentionally a string nobody could mistake for safe. |
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

The public API is four endpoints under `/api/v1/`:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/sessions` | Get a single-use session token bound to a game. |
| `POST` | `/scores` | Submit a score (requires `Authorization: Bearer <token>`). |
| `GET` | `/leaderboards` | Read scores for a game with filters + pagination. |
| `GET` | `/champions` | Per-player tally of daily-seed wins (cached, paginated). |

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
      "seed": "3421789012",
      "custom_data": {"combo": 47, "perfect": true}
    }'

# Response: {"id": 1234}
```

### Reading the leaderboard

```bash
# All-time top 25 of NORMAL (non-seeded) play.
curl 'http://localhost:8000/api/v1/leaderboards?game=tetris-classic'

# A specific daily-challenge board (pass its seed hash).
curl 'http://localhost:8000/api/v1/leaderboards?game=tetris-classic&range=daily&seed=3421789012'

# Search for a player.
curl 'http://localhost:8000/api/v1/leaderboards?game=tetris-classic&name=ren'

# Paginate.
curl 'http://localhost:8000/api/v1/leaderboards?game=tetris-classic&page=2&page_size=50'
```

> **Seeded vs. normal scores don't mix.** Omitting `seed` returns only scores submitted with no seed (normal play). Passing a `seed` returns only that seed's scores. This keeps daily-challenge runs from polluting the all-time board and vice-versa. See [`docs/api.md`](docs/api.md#get-apiv1leaderboards--query-scores).

### Daily-seed champions

For each distinct seed, whoever posted the best score that day gets a win. The `/champions` endpoint tallies wins per player. Useful for surfacing "king of the daily challenge"-style boards.

```bash
# All-time tally.
curl 'http://localhost:8000/api/v1/champions?game=tetris-classic'

# Last 90 days only (use Z suffix; + must be URL-encoded as %2B in query strings).
curl 'http://localhost:8000/api/v1/champions?game=tetris-classic&since=2026-02-20T00:00:00Z'

# Specific window.
curl 'http://localhost:8000/api/v1/champions?game=tetris-classic&since=2026-01-01T00:00:00Z&until=2026-04-01T00:00:00Z'
```

Scores with `seed = null` are ignored; soft-deleted scores are excluded (a cheater's winning score being moderated promotes the runner-up for that seed).

### Integration notes for game clients

- The session token is opaque to clients — don't try to parse it.
- Request a *fresh* token before each score submission. Tokens are single-use.
- Tokens are bound to a specific game (by slug); submitting a score for a different game returns `401 invalid_session`.
- `played_at` is optional, in ISO 8601 (`2026-05-20T12:34:56Z`). It must be ≥ the token's issuance time and ≤ now + 60s of skew tolerance.
- `seed` is for daily-challenge style leaderboards. Leave it `null` for normal play. For daily challenges, the seed is the **Godot DJB2-XOR hash** of the date string `"YYYY-MM-DD"` (in US Eastern time, accounting for DST), returned as an **unsigned 32-bit decimal string** — e.g. `"3421789012"`. The algorithm: start with `h = 5381`; for each character `c`, compute `h = ((h * 33) XOR ord(c)) mod 2³²`. This matches GDScript's built-in `hash()` function. The admin dashboard and API test page accept a calendar date and convert it automatically.
- `custom_data` is any small JSON object (≤32 keys, ≤256 chars per string value). The admin may pin a schema per game (see `docs/data_models.md`).

---

## Privacy policy

Because players submit a name plus device/OS info, app stores (and the law in
many places) expect a privacy policy. Each game gets one automatically:

- **Public URL:** `/privacy/<slug>` (with an index at `/privacy`), reachable
  without login — this is the "active URL" you link from your Google Play / App
  Store listing and from inside your game.
- **What it says:** a standard, conventional policy that comprehensively
  describes what this software collects (player name, scores, timestamps, seed,
  device/OS info, custom fields), how IP is used (rate-limiting only, not stored
  with scores), how data is used and shared (public leaderboard display; no sale;
  self-hosted, no third-party ad/analytics by default), retention, deletion
  requests, children, security, and contact info.
- **Customize per game:** set the operator name, privacy contact email, and any
  extra clauses in the admin game form (**Games → edit → Privacy policy**).

> ⚠️ **Not legal advice.** This template reflects common practice and the data
> this software actually handles, and is written to satisfy Google Play's
> requirement for a privacy policy that "comprehensively discloses how your app
> collects, uses and shares user data." It is **not** a substitute for legal
> review — if your audience includes the EU/UK (GDPR), California (CCPA/CPRA), or
> children (COPPA), have counsel review and adapt it.

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

8. **Site-specific compose tweaks go in `docker-compose.override.yml`.** Docker Compose auto-merges that file if present, and it's gitignored so it never ships. Use it to, e.g., drop the bundled `db`/`redis` and point the app at managed/external instances, attach to an existing network, or pin a container name — without editing the tracked `docker-compose.yml`. Example:

   ```yaml
   services:
     db: !reset null          # use an external Postgres instead of the bundled one
     redis: !reset null        # use an external Redis instead of the bundled one
     app:
       environment:
         POSTGRES_HOST: my-managed-postgres.internal
         REDIS_URL: redis://:password@my-managed-redis.internal:6379/0
         REDIS_RATELIMIT_URL: redis://:password@my-managed-redis.internal:6379/1
   ```

---

## What's in / out of scope

**In scope (v1):**
- Four-endpoint public API (`/sessions`, `/scores`, `/leaderboards`, `/champions`) with session-token-guarded score submission.
- Per-game min/max score bounds + named-character / control-char filtering on player names.
- Admin UI for game management, score moderation (soft-delete + restore), admin-user management, and an interactive API-test page (`/admin/api-test`) for building `/leaderboards` and `/champions` queries.
- Public, per-game privacy policy at `/privacy/<slug>` (and an index at `/privacy`) — a standard, Google-Play-aligned policy you can link from your store listing and in-app.
- Per-game cache invalidation, range queries respecting per-game IANA timezone, daily-seed champion tallies.

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

---

## License & disclaimer

Released under the [MIT License](LICENSE) — you are free to use, copy, modify, merge, publish, distribute, sublicense, and sell copies, including in commercial and closed-source products. The only condition is that the copyright notice and license text travel with substantial copies.

**Use at your own risk.** As stated in the LICENSE, the software is provided **"as is", without warranty of any kind**, express or implied. The author(s) and copyright holder(s) are **not liable** for any claim, damages, or other liability — including data loss, leaderboard tampering, downtime, or security incidents — arising from the use of this software. You are responsible for how you deploy, secure, and operate it (see [Production deployment](#production-deployment) and [Threat model](#threat-model)).
