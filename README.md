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

The app sets `root_path="/auth/api"`. When deployed behind a reverse proxy with that path prefix, the routes below are served under `/auth/api/`.

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

On startup, the service expects the schema to already match the current Alembic revision. See [Database migrations](#database-migrations).

## Tech stack

- Python 3.12, FastAPI
- PostgreSQL (with `pg_partman` / `pg_cron` for login-history partitions)
- Redis (refresh-token blocklist, rate limiting)
- RS256 JWT (`pyjwt`, PEM key pair)
- OpenTelemetry → Jaeger (optional)
- Sentry error reporting (optional)
- Gunicorn + Uvicorn workers (production)
- Multiprocess-safe structured JSON file logging
- [uv](https://docs.astral.sh/uv/) for local dependency management

## Environment variables

| Variable | Description |
|----------|-------------|
| `PROD_RUN` | Sets the `Secure` flag on auth cookies — use `true` only when HTTPS is configured |
| `RESET_DB_ON_STARTUP` | Drop and recreate the schema on app startup when `true` — useful for quick iteration; keep `false` when using Alembic migrations |
| `SUPERUSER_EMAIL` / `SUPERUSER_PASSWORD` | Bootstrap superuser credentials |
| `PRIVATE_KEY_PATH` / `PUBLIC_KEY_PATH` | RS256 PEM files for signing and verification |
| `YANDEXID_CLIENT_ID` / `YANDEXID_CLIENT_SECRET` | Yandex OAuth application credentials |
| `YANDEXID_REDIRECT_URL` | Redirect URI registered with Yandex |
| `RATE_LIMIT_ENABLED` | Enable per-IP rate limiting (`true` by default) |
| `TRACING_ENABLED` | Export traces to Jaeger when `true` |
| `SENTRY_ENABLED` | Report unhandled errors to Sentry when `true` and `SENTRY_DSN` is set |
| `SENTRY_DSN` | Sentry DSN; leave empty to keep Sentry off |
| `SENTRY_ENVIRONMENT` | Sentry environment tag (for example, `development`) |
| `SENTRY_RELEASE` | Optional release identifier |
| `LOG_FILE_PATH` | Enable structured file logging and set the active JSON log path; unset to keep console-only logging |
| `LOG_MAX_BYTES` | Rotate the active log after this many bytes (default: 10 MiB) |
| `LOG_BACKUP_COUNT` | Number of rotated files retained (default: 7) |

Database, Redis, Yandex endpoints, tracing, and Sentry settings — see `.env.example`. Copy it to `.env` and adjust values for your environment.

## Logging and ELK

Console logging remains enabled for `docker compose logs`. When `LOG_FILE_PATH` is set, the service also writes one JSON object per line through a multiprocess-safe rotating handler, suitable for the four Gunicorn workers. Events include timestamp, level, logger, message, process ID, exception details, `request.id`, `trace.id`, and `span.id`.

The portfolio Compose stack sets `LOG_FILE_PATH=/var/log/auth-api/app.json`, mounts that directory as a named volume, and has Filebeat forward it through Logstash to daily `auth-api-YYYY.MM.dd` indexes in the logging Elasticsearch cluster. Search the events in Kibana at `http://localhost/logs/`.

## Error reporting (Sentry)

Unhandled exceptions are sent to Sentry when `SENTRY_ENABLED=true` and `SENTRY_DSN` is set. Expected `HTTPException` responses (401, 404, 429, and similar) are ignored. Authorization headers, cookies, and request bodies are stripped; events are tagged with `service=auth-api` and the current `request.id`. Sentry performance tracing stays off — Jaeger remains the trace backend.

The portfolio production stack uses a self-hosted Sentry at `http://sentry.localhost/`. Copy the **auth-api** project DSN from the UI, replace only the host with `sentry-api:9000`, and keep the project ID from that DSN. Tests set `SENTRY_ENABLED=false`.

## Getting started

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Copy `.env.example` to `.env` and adjust hosts, ports, and credentials.
3. Generate or copy an RS256 key pair and set `PRIVATE_KEY_PATH` and `PUBLIC_KEY_PATH` in `.env` (for example, `certs/jwt-private.pem` and `certs/jwt-public.pem`).
4. Start PostgreSQL and Redis; match their hosts and ports in `.env`.
5. Configure Yandex OAuth credentials when testing the real provider.
6. Sync dependencies:
   ```bash
   uv sync --group dev
   ```
7. Prepare the database — see [Database migrations](#database-migrations) (Alembic or `RESET_DB_ON_STARTUP`).

Run the service:

```bash
set -a && source .env && set +a; uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

OpenAPI docs: http://127.0.0.1:8000/docs

## Database migrations

Schema changes live in `alembic/versions/`. Alembic reads the database URL from `POSTGRES_*` variables in `.env`.

### When to use Alembic vs `RESET_DB_ON_STARTUP`

| Approach | When | What happens |
|----------|------|--------------|
| `RESET_DB_ON_STARTUP=true` | Quick local iteration with `uvicorn` only | On startup the app drops and recreates all tables from models, then seeds the superuser and default `user` role. Do not use with existing data. |
| Alembic (`RESET_DB_ON_STARTUP=false`, default) | Normal development, tests, and production | Applies versioned migrations; safe for existing databases. |

### Apply migrations

From the `auth_api` directory:

```bash
set -a && source .env && set +a
uv run alembic upgrade head
```

After the first migration on a fresh database, create bootstrap data:

```bash
uv run python -m app.commands.create_default_role
uv run python -m app.commands.create_superuser
```

`create_superuser` uses `SUPERUSER_EMAIL` and `SUPERUSER_PASSWORD` from the environment, or prompts interactively.

When the app starts through `run_app.sh`, it runs `alembic upgrade head` and both bootstrap commands automatically before serving traffic.

### Create a new migration

After changing models in `app/db/models.py`:

```bash
set -a && source .env && set +a
uv run alembic revision --autogenerate -m "short description"
uv run alembic upgrade head
```

Review the generated script in `alembic/versions/` before applying.

## Running tests

Sentry unit tests do not need Docker:

```bash
uv run pytest tests/test_sentry.py
```

Functional tests exercise the live API against PostgreSQL, Redis, and a Yandex OAuth mock. Default connection settings in `tests/functional/settings.py` match the ports published by `docker-compose.tests.yaml`:

| Service | Host | Port |
|---------|------|------|
| API | `127.0.0.1` | `8001` |
| PostgreSQL | `127.0.0.1` | `5434` |
| Redis | `127.0.0.1` | `6377` |
| Yandex mock | `127.0.0.1` | `8090` |

### Test stack (Docker)

1. JWT keys for the test stack live in `tests/docker/certs/` (included in the repo). Compose mounts them into the API container; pytest reads the same public key from that path. The stack loads `.env.tests` with `PROD_RUN=false` and `RESET_DB_ON_STARTUP=false`; migrations and bootstrap run automatically via `run_app.sh`.

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

## Code quality (PEP pipeline)

Install development-only tooling and enable hooks from the `auth_api` directory:

```bash
uv sync --group dev
uv run pre-commit install
```

Run checks manually:

```bash
uv run ruff format --check .
uv run ruff check .
```

Auto-format and apply safe lint fixes:

```bash
uv run ruff check --fix .
uv run ruff format .
```

## Updating dependencies

`pyproject.toml` is the source of truth for local development. After changing dependencies, export them for Docker builds:

```bash
uv export --format requirements-txt --no-dev --no-hashes -o requirements.txt
uv export --format requirements-txt --only-dev --no-hashes -o requirements-dev.txt
```
