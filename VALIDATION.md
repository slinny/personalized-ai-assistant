# Task 1 validation

Validated on 2026-09-07 with Python 3.13.1 (project requires Python >=3.12).

| Command | Result |
| --- | --- |
| `.venv/bin/pytest -q` | 6 passed |
| `.venv/bin/ruff check .` | Passed |
| `.venv/bin/ruff format --check .` | 12 files already formatted |
| `.venv/bin/mypy` | Passed, 10 source files |
| `.venv/bin/pip check` | No broken requirements |
| `.venv/bin/alembic heads` | Passed, no revisions |
| `.venv/bin/alembic upgrade head --sql` | Passed, empty transaction |
| `curl --fail-with-body -i http://127.0.0.1:8000/health` | HTTP 200, `{"status":"ok"}` |

HTTP smoke test server command:

```sh
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

pytest reported two upstream deprecation warnings: Starlette's HTTPX test-client
integration and its AnyIO BlockingPortal alias. No warnings were suppressed.

Docker and PostgreSQL executables were unavailable. Container build/Compose runtime,
Python 3.12 container execution, online Alembic execution, and live PostgreSQL
connectivity were not verified. The README provides reproducible commands for each.
No domain persistence or authentication is claimed by this milestone.

# Task 2 validation

Validated on 2026-09-07 against an isolated PostgreSQL 17 container, with no
application data or existing database modified. Task 1 notes above are historical.

| Check | Result |
| --- | --- |
| Local Python 3.13.1, full pytest with TEST_DATABASE_URL | 32 passed |
| Built Docker image, Python 3.12.14, full pytest with TEST_DATABASE_URL | 32 passed |
| Ruff lint and format, local and container | Passed |
| mypy, local and container | Passed, 13 source files |
| pip check, local and container | No broken requirements |
| Alembic upgrade → downgrade base → upgrade | Passed against PostgreSQL |
| Alembic check after upgrade | No new upgrade operations detected |
| alembic heads | Single head: 3f403ab7f7d7 |
| alembic upgrade head --sql | Passed, reviewed generated PostgreSQL SQL |
| Live GET /health on port 58000 | HTTP 200, {"status":"ok"} |
| git diff --check | Passed |

The 32 tests include 25 PostgreSQL cases for persistence across sessions, all four
lifecycle statuses, required status, timestamps, defaults, exact instruction and
string-length boundaries, personality bounds (including NaN/infinity rejection),
invalid roles/statuses, orphan references, cross-user profile references, profile
uniqueness, message ordering/uniqueness, restricted deletes, cascading message
deletes, and migration round trips. Two existing Starlette deprecation warnings
remain; no warnings are suppressed.

Reproduce the PostgreSQL suite using README.md's disposable database commands.
To also validate the declared Python 3.12 container runtime while that database runs:

```sh
docker build -t assistant-task2-validation .
docker run --rm --network container:assistant-task2-test \
  -e TEST_DATABASE_URL=postgresql+psycopg://postgres:task2-local@127.0.0.1:5432/assistant_task2_test \
  assistant-task2-validation sh -c \
  'python --version && pytest -q && ruff check . && ruff format --check . && mypy && pip check'
```

Live HTTP smoke test:

```sh
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 58000
# Another terminal:
curl --fail-with-body -i http://127.0.0.1:58000/health
```

The container image and real PostgreSQL connection are validated. The complete
Compose stack was not started. Task 3 authentication/endpoints and message lifecycle
transition/recovery logic remain outside Task 2.

## Task 3 — 2026-09-07

Implemented configured bearer authentication, explicit idempotent provisioning,
request session cleanup, and owned assistant GET/PATCH endpoints.

- Full pytest run against disposable PostgreSQL 17 on port 55433: **63 passed**,
  no skips. Includes migrations and schema drift, concurrent provisioning,
  real HTTP persistence across app restarts, ownership isolation, partial updates,
  validation failures, authentication failures, and session rollback.
- `ruff check .`, `ruff format --check .`, and `mypy`: passed.
- `alembic heads`: one unchanged head (`3f403ab7f7d7`).
- `alembic upgrade head --sql`: generated successfully.
- `alembic check`: no new upgrade operations detected.
- `python -m app.db.provision`: succeeded against the disposable database.
- `docker compose config --quiet` and `git diff --check`: passed.
- Two existing dependency deprecation warnings remain from Starlette's httpx
  TestClient and AnyIO BlockingPortal alias. The full Compose stack was not run;
  PostgreSQL and the application TestClient were exercised directly.

Each implementation checkpoint was tested and committed independently. No
schema migration was needed. See docs/task-3.md and README.md for the API and setup.

## Task 4 — 2026-09-07

Implemented the pure BehaviorCompiler and validated BehaviorProfile snapshot,
centralized personality mappings, explicit language/custom instruction semantics,
and the documented greeting/context boundary. Seven checkpoints were individually
validated before committing.

- Baseline: 33 passed, 30 PostgreSQL cases skipped without TEST_DATABASE_URL.
- New compiler suite: 53 passed, including reviewed default/customized fixtures.
- Full regression against disposable PostgreSQL 17 on port 55434: **116 passed,
  no skips**, including migration round trips and schema-drift checks.
- Ruff lint and format: passed (36 files formatted).
- mypy: passed (29 source files).
- pip check: no broken requirements.
- Alembic: unchanged single head 3f403ab7f7d7; offline upgrade SQL generated.
- README compilation example: executed successfully without database/provider I/O.
- git diff --check: passed.

Two pre-existing Starlette/AnyIO deprecation warnings remain. No live LLM behavior
is claimed: these tests verify the deterministic instructions. The complete Compose
stack and Python 3.12 container runtime were not rerun for this Python-only change.

Full regression command (while the disposable container is running):

```sh
TEST_DATABASE_URL=postgresql+psycopg://postgres:task4-local@127.0.0.1:55434/assistant_task4_test .venv/bin/pytest -q
```
