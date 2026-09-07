# Personalized AI Assistant

Tasks 1–2: Python 3.12+, FastAPI, Pydantic settings, SQLAlchemy/PostgreSQL,
User/AssistantProfile/Conversation/Message models, Alembic migrations, pytest,
and local Docker development.

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
Run `alembic upgrade head` explicitly to create the four domain tables. The app
does not create tables at startup. Model metadata is registered with Alembic.
See [the storage contract](docs/task-2.md) for limits, ownership, and deletion rules.
JSON holiday preferences should be replaced as a whole when editing through the ORM;
in-place dictionary mutations are not tracked.

## Validation

```sh
pytest -q
ruff check .
ruff format --check .
mypy
alembic heads
alembic upgrade head --sql
```

The default test run skips PostgreSQL integration tests unless `TEST_DATABASE_URL`
is set. Integration tests exercise migrations, persistence, constraints, and deletion.
They downgrade the entire schema: use only an isolated disposable database whose
name ends in `_test`. Never point them at a database containing valuable records.

```sh
docker run --name assistant-task2-test --rm -d \
  -e POSTGRES_PASSWORD=task2-local -e POSTGRES_DB=assistant_task2_test \
  -p 127.0.0.1:55432:5432 postgres:17
# Wait until this succeeds before running tests:
docker exec assistant-task2-test pg_isready -U postgres -d assistant_task2_test
export TEST_DATABASE_URL=postgresql+psycopg://postgres:task2-local@127.0.0.1:55432/assistant_task2_test
.venv/bin/pytest -q
# Remove only this disposable test container:
docker stop assistant-task2-test
```

In addition to migration round-trip tests, check schema drift using
`DATABASE_URL="$TEST_DATABASE_URL" .venv/bin/alembic check` while the test database runs.

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

Task 2 adds domain persistence only. The next milestone is Task 3: single-user
bearer authentication and assistant GET/PATCH endpoints.

Foundation references: [FastAPI Docker](https://fastapi.tiangolo.com/deployment/docker/)
and [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html).
