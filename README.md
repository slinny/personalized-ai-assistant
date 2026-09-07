# Personalized AI Assistant

Task 1 only: Python 3.12+, FastAPI, Pydantic settings, SQLAlchemy/PostgreSQL,
empty Alembic environment, pytest, and local Docker development.

## Local Python

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From another terminal:

```sh
curl --fail-with-body http://localhost:8000/health
```

Expected: HTTP 200 with `{"status":"ok"}`. This is a public liveness check;
it deliberately works without PostgreSQL. No authentication is implemented yet.
Environment variables override `.env`. Sample credentials are local development defaults.

## Docker development

Requires Docker Engine/Desktop and Compose v2.

```sh
docker compose up --build -d --wait
curl --fail-with-body http://localhost:8000/health
docker compose exec api python -m app.db.check
docker compose exec api alembic upgrade head
docker compose exec api pytest -q
docker compose down
```

PostgreSQL data survives `down` in the named volume. Both exposed ports bind to
loopback. The API reloads when `app/` changes. This image includes development tools.
For host Python with only PostgreSQL in Docker:

```sh
docker compose up -d db
python -m app.db.check
```

The database probe executes `SELECT 1` and exits nonzero on connection failure.
SQLAlchemy uses synchronous psycopg with a five-second connection timeout.
Engine construction is lazy; callers own disposal and explicitly commit writes.
There are no domain tables, schema creation at app startup, or migration revisions.
Task 2 must connect Alembic's empty metadata to the domain model metadata before
using autogenerate. `alembic upgrade head` currently has no domain changes to apply.

## Validation

```sh
pytest -q
ruff check .
ruff format --check .
mypy
alembic heads
alembic upgrade head --sql
```

Tests cover HTTP liveness without a database, configuration validation and precedence,
and lazy engine/session construction. They do not claim live database coverage.

## Plan review

- Keep the modular monolith and add module directories only when implemented.
  Task 1 is smaller than Phase 1: models/migrations belong to Task 2 and auth to Task 3.
- Define `/health` as liveness; use the separate database probe for connectivity.
- Later, enforce ownership through related records (including conversation/profile
  consistency). Foreign keys alone do not enforce authorization.
- Add a basic explicit context overflow guard with the first LLM pipeline, then
  develop the complete history budgeting policy in Task 7.
- Later, specify transaction boundaries, retries, and recovery for interrupted
  message generation; avoid holding a database transaction during provider calls.
- Validate the product hypothesis with a small same-model generic versus customized
  comparison before investing in voice, clients, and additional providers.

No domain models, authentication, LLM calls, or future-phase abstractions are included.
The next milestone is Task 2; it has not been started.

Foundation references: [FastAPI Docker](https://fastapi.tiangolo.com/deployment/docker/)
and [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html).
