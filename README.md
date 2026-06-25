# Auth API — Online Movie Theater

FastAPI service for an online movie theater platform. It manages user accounts, issues RS256 JWT access tokens, assigns content-access roles, and integrates with Yandex ID for OAuth login.

Part of the [Yandex Practicum](https://practicum.yandex.ru/) diploma project (sprint 2).

## What it does

The service is the **identity and access layer** for the platform. Other services (admin panel, movies API) verify access tokens with the auth service public key and use JWT claims to authorize requests.

**Authentication** issues short-lived access tokens and long-lived refresh tokens. Refresh tokens are stored in an HTTP-only `refresh` cookie; access tokens are returned in the JSON body and sent by clients in the `Authorization: Bearer <token>` header.

**Roles** map users to content tiers. Each role carries one or more `access_labels` (`free`, `premium`, `vip`) that downstream services use for catalog access control. Role management endpoints require a superuser token.

**Yandex ID OAuth** lets users sign in or register through Yandex without a local password. The flow uses a CSRF `state` cookie and exchanges the provider authorization code for platform tokens.

Every successful login (password or OAuth) is recorded in **login history**: user, timestamp, client IP, user agent, and device ID. The table is range-partitioned by date in PostgreSQL.

### Access token claims

Access tokens are RS256 JWTs. Downstream services typically rely on:

| Claim | Description |
|-------|-------------|
| `sub` | User UUID |
| `is_superuser` | Full administrative access when `true` |
| `role` | Assigned role title (for example, `user`) |
| `access_labels` | Content tiers the user may view (`free`, `premium`, `vip`) |
| `tv` | Token version; incremented on password change or forced logout |

Superusers may have `role: null` and an empty `access_labels` list; consumers treat `is_superuser=true` as unrestricted access.

## REST API

The app sets `root_path="/auth/api"`. Through nginx in the development stack, all paths below are served under `/auth/api/`.

### Auth

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/token` | Login with email and password; returns access token, sets refresh cookie |
| `POST` | `/refresh` | Issue a new access token from the refresh cookie |
| `POST` | `/logout` | Revoke the current refresh token and clear the cookie |
| `POST` | `/logout-others` | Revoke all other sessions for the authenticated user (requires Bearer token) |

### Users

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/users` | Register a new user |
| `GET` | `/users/me` | Current user profile (requires Bearer token) |
| `PATCH` | `/users/me/email` | Change email (requires current password) |
| `PATCH` | `/users/me/password` | Change password |
| `GET` | `/users/me/login-history` | Paginated login history (`page`, `page_size`) |

### Roles (superuser only)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/roles` | List all roles |
| `POST` | `/roles` | Create a role |
| `PATCH` | `/roles/<uuid>` | Update role title and access labels |
| `DELETE` | `/roles/<uuid>` | Delete a role (the default `user` role is protected) |
| `POST` | `/roles/assign` | Assign a role to a user |
| `POST` | `/roles/revoke` | Remove a user's role (falls back to the default role) |

### Yandex ID

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/yandexid/login` | Redirect to Yandex OAuth; sets CSRF `state` cookie |
| `GET` | `/yandexid/token` | OAuth callback; exchanges code for tokens |

Sensitive routes are rate-limited per client IP via Redis (see `RATE_LIMIT_*` settings).

## Data model

```
Role ──< User ──< LoginHistory
         │
         └──< OAuthAccount
```

- **User** — email, password hash, optional role, superuser flag, token version
- **Role** — unique title and JSON list of `access_labels`
- **LoginHistory** — append-only audit of sign-ins, partitioned by `logged_in_at`
- **OAuthAccount** — links a Yandex account to a local user

On container start, the entrypoint runs Alembic migrations and creates the default `user` role (with the `free` label) plus the configured superuser account if they do not exist yet.

## Tech stack

- Python 3.12, FastAPI
- PostgreSQL (with `pg_partman` / `pg_cron` for login-history partitions)
- Redis (refresh-token blocklist, rate limiting)
- RS256 JWT (`pyjwt`, PEM key pair)
- OpenTelemetry → Jaeger (optional)
- Gunicorn + Uvicorn workers (production)
- [uv](https://docs.astral.sh/uv/) for local dependency management

## Environment variables

| Variable | Description |
|----------|-------------|
| `PROD_RUN` | Sets the `Secure` flag on auth cookies — use `true` only when HTTPS is configured |
| `RESET_DB_ON_STARTUP` | Drop and recreate the schema on app startup when `true` (local dev / tests) |
| `SUPERUSER_EMAIL` / `SUPERUSER_PASSWORD` | Bootstrap superuser credentials |
| `PRIVATE_KEY_PATH` / `PUBLIC_KEY_PATH` | RS256 PEM files for signing and verification |
| `YANDEXID_CLIENT_ID` / `YANDEXID_CLIENT_SECRET` | Yandex OAuth application credentials |
| `YANDEXID_REDIRECT_URL` | Redirect URI registered with Yandex |
| `RATE_LIMIT_ENABLED` | Enable per-IP rate limiting (`true` by default) |
| `TRACING_ENABLED` | Export traces to Jaeger when `true` |

Database, Redis, Yandex endpoints, and tracing settings — see `.env.example` for container defaults and `.env.local` for local run defaults.

## Local development

From app root:
1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Start PostgreSQL and Redis. From repo root, `just dev` brings up `postgres-auth` (port `5433`) and Redis (port `6379`); match hosts/ports in `.env.local`.
3. Generate or copy an RS256 key pair into `certs/jwt-private.pem` and `certs/jwt-public.pem` (the `certs/` directory is gitignored). Other platform services use the public key from repo-root `auth-certs/jwt-public.pem` — keep both in sync during local development.
4. Configure Yandex OAuth credentials in `.env.local` when testing the real provider.
5. Sync dependencies and start the dev server:
   ```bash
   uv sync
   set -a && source .env.local && set +a; uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

With `RESET_DB_ON_STARTUP=true` (the default in `.env.local`), the service drops and recreates tables on startup and seeds the superuser and default role — no manual migrations needed.

From repo root:

```bash
just auth-api-local
```

OpenAPI docs: http://127.0.0.1:8000/docs

## Containerized run

Containerized runs are orchestrated from repo root:

- Development stack: `docker-compose.dev.yml`

The `auth-api` service depends on `postgres-auth`, Redis, and Jaeger. JWT keys are mounted from `./auth-certs/` at `/run/secrets/jwt/`.

Ensure env files are in place (`env-files/.env.auth` is used by the dev stack). The repo development stack serves HTTP only on port 80, so keep `PROD_RUN=false` there. Use `RESET_DB_ON_STARTUP=false` for container runs that should apply Alembic migrations instead of resetting the schema:

Run development stack:

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

The API is exposed through nginx at `/auth/api`:

OpenAPI docs: http://127.0.0.1/auth/api/docs  
Jaeger UI: http://127.0.0.1:16686

The admin panel uses this service for staff login (`AUTH_API_LOGIN_URL=http://auth-api/auth/api/token` inside Docker). Mount the same public key into dependent services.

## Running tests

Functional tests exercise the live API against PostgreSQL, Redis, and a Yandex OAuth mock. Default connection settings in `tests/functional/settings.py` match the ports published by `docker-compose.tests.yaml`:

| Service | Host | Port |
|---------|------|------|
| API | `127.0.0.1` | `8001` |
| PostgreSQL | `127.0.0.1` | `5434` |
| Redis | `127.0.0.1` | `6377` |
| Yandex mock | `127.0.0.1` | `8090` |

### Test stack (Docker)

1. Place the JWT key pair at `certs/jwt-private.pem` and `certs/jwt-public.pem` (used by the API container and the test suite). The test stack uses `.env.tests` with `PROD_RUN=false` and `RESET_DB_ON_STARTUP=true`.

2. Start PostgreSQL, Redis, the Yandex mock, and the API:
   ```bash
   docker compose -f docker-compose.tests.yaml up --build -d
   ```

3. Run the full suite from the `auth_api` directory:
   ```bash
   uv run pytest tests/functional
   ```

4. Stop the stack when finished:
   ```bash
   docker compose -f docker-compose.tests.yaml down
   ```

### Run a subset

```bash
uv run pytest tests/functional/testunits/auth
uv run pytest tests/functional/testunits/users
uv run pytest tests/functional/testunits/roles
uv run pytest tests/functional/testunits/yandexid
```

Override host or port via environment variables accepted by `tests/functional/settings.py` (for example, `AUTH_TEST_API_URL`, `POSTGRES_PORT`, `REDIS_PORT`).

## Updating dependencies

`pyproject.toml` is the source of truth for local development. After changing dependencies, export them for Docker builds:

```bash
uv export --format requirements-txt --no-hashes > requirements.txt
```
