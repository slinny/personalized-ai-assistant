# Personalized AI Assistant

Tasks 1–5: Python 3.12+, FastAPI, Pydantic settings, SQLAlchemy/PostgreSQL,
User/AssistantProfile/Conversation/Message models, Alembic migrations, pytest,
single-user bearer authentication, assistant settings, deterministic behavior compilation,
non-streaming OpenAI conversation/message APIs, and local Docker development.

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
it deliberately works without PostgreSQL. Assistant endpoints require configured bearer authentication.
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

Task 3 adds single-user bearer authentication and assistant GET/PATCH endpoints.
See [the API contract](docs/task-3.md) for validation and PATCH semantics.

Foundation references: [FastAPI Docker](https://fastapi.tiangolo.com/deployment/docker/)
and [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html).

## Assistant setup and API

After copying `.env.example` to `.env`, generate a token and a stable user UUID:

```sh
python -c 'import secrets, uuid; print("AUTH_TOKEN=" + secrets.token_urlsafe(32)); print("AUTH_USER_ID=" + str(uuid.uuid4()))'
```

Save the two generated lines in `.env`, then initialize persistence:

```sh
alembic upgrade head
python -m app.db.provision
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Provisioning is repeatable and preserves customized profiles. For Docker, Compose
reads `.env`; run `docker compose exec api alembic upgrade head` followed by
`docker compose exec api python -m app.db.provision`. Recreate the API container
with `docker compose up -d --force-recreate api` after changing configuration.

Set the shell variable `AUTH_TOKEN` to your generated token to try the endpoints:

```sh
curl --fail-with-body http://localhost:8000/assistant -H "Authorization: Bearer $AUTH_TOKEN"
curl --fail-with-body -X PATCH http://localhost:8000/assistant \
  -H "Authorization: Bearer $AUTH_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Ada","warmth":0.8,"holiday_preferences":{"new_year":"Happy New Year"}}'
```

Missing/invalid credentials return 401, an unprovisioned profile returns 404,
and invalid updates return 422. With neither auth setting configured, assistant
routes return 503 while `/health` continues to work. Partial auth configuration
fails startup validation. Update the token and restart to rotate credentials;
keep the user UUID unchanged to retain access to the same profile.

## Behavior compiler (Task 4)

Compile validated preferences locally without a database or provider connection:

```sh
.venv/bin/python - <<'PY'
from app.behavior import BehaviorCompiler, BehaviorProfile

profile = BehaviorProfile(name="Alice", warmth=0.8, verbosity=0.2)
print(BehaviorCompiler().compile(profile))
PY
```

For an already-loaded assistant record, use `BehaviorProfile.model_validate(record)`
to create the compiler input. The compiler emits identity, communication, language,
and losslessly encoded custom instructions. See [the compiler contract](docs/task-4.md)
for mappings, precedence, and the greeting/context boundary. Conversation/provider
integration is implemented in Task 5; live behavioral evaluation follows in Task 6.


## Conversations and messages (Task 5)

Set `OPENAI_API_KEY` in `.env` and set `OPENAI_MODEL` to a model available to your
OpenAI project, or configure the assistant's `preferred_model`. Restart the API.
Conversation creation and reading work without provider configuration; sending requires
both a provider and a model. The existing bearer token authenticates all these routes.

```sh
curl --fail-with-body -X POST http://localhost:8000/conversations \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Copy the returned id:
CONVERSATION_ID=replace-with-returned-uuid
curl --fail-with-body -X POST "http://localhost:8000/conversations/$CONVERSATION_ID/messages" \
  -H "Authorization: Bearer $AUTH_TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"Hello! Please introduce yourself."}'
curl --fail-with-body "http://localhost:8000/conversations/$CONVERSATION_ID/messages?after_position=0&limit=50" \
  -H "Authorization: Bearer $AUTH_TOKEN"
curl --fail-with-body 'http://localhost:8000/conversations?limit=50&offset=0' \
  -H "Authorization: Bearer $AUTH_TOKEN"
```

Sending waits for the complete reply and returns HTTP 201 with `user_message` and
`assistant_message`. Each includes its ID, position, role, content, status, and
timestamps. Input must be nonblank and at most 20,000 characters. Profile changes
apply to the next turn, including preferred model and compiled behavior.

Concurrent sends to one conversation return 409 while a turn is active. Upstream
failures return 502 or 504 and leave a failed assistant message in history. Interrupted
turns can be recovered by a new send after the generation lease expires (180 seconds
by default). A lost response should be checked against saved history before resending;
repeated POSTs create new turns. See [the pipeline contract](docs/task-5.md) for context
limits, configuration, error handling, and transaction/recovery semantics.

All automated generation uses a fake provider or mocked SDK. Live HTTP is blocked
in tests, so no OpenAI credentials or paid calls are needed. Run the full suite with
`TEST_DATABASE_URL` pointing at the disposable PostgreSQL database described above.

## Behavioral evaluations (Task 6)

The 18 versioned cases in `evaluations/initial.json` cover identity, personality,
language, customization, precedence, and multi-turn consistency. Run from the
repository root; no database is required.

```sh
# Offline harness smoke: fake text, not evidence of model quality.
.venv/bin/python -m app.evaluation --compare --output evaluation-results/smoke
# Explicit paid provider execution using .env configuration:
.venv/bin/python -m app.evaluation --live --model YOUR_MODEL \
  --compare --repeats 2 --output evaluation-results/live-001
# Narrow runs with repeatable --case or --category filters:
.venv/bin/python -m app.evaluation --live --category language \
  --output evaluation-results/language-001
```

Each run requires a new output directory. JSON preserves inputs, full requests,
responses, settings, and objective results; Markdown groups comparison arms by
case and repetition for manual review. Score rubric adherence and factual quality
from 0 (misses) to 2 (meets), with 1 for partial adherence. All subjective scores
start pending; no automated overall behavioral pass is claimed. The default arm
uses an uncustomized `Assistant` profile and is reviewed against the same desired
outcome, without failing checks for customization it did not receive.

Exit codes: 0 means objective checks did not fail (human review still pending),
1 means objective failures, 2 means generation errors or CLI usage errors. The full
offline smoke intentionally returns 1 because placeholder responses fail identity
checks. Reports contain evaluation text; local output is gitignored. No credentials
are included. `contains` checks are case-insensitive substrings; word limits count
whitespace-separated words. Language and personality are manually reviewed, not
inferred from these simple checks. See [Task 6](docs/task-6.md) for the contract.
