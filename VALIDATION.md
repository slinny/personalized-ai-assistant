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
