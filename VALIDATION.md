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

## Task 5 — 2026-09-07

Implemented authenticated conversation creation/listing, ordered message retrieval,
non-streaming generation, injectable OpenAI/fake providers, bounded compiled context,
transactional message positions, failure persistence, and lease-based recovery.
Each of the seven planned checkpoints was validated before its commit.

- Local Python 3.13.1, full suite against disposable PostgreSQL 17: **153 passed,
  no skips**. Includes all prior tests and migrations/schema-drift checks.
- Built Docker image, Python 3.12.14, same full suite: **153 passed, no skips**.
- Ruff lint/format and strict mypy: passed locally and in Docker (46 source files
  checked by mypy).
- `pip check`: passed locally and in Docker. OpenAI SDK 2.54.0 installed and tested.
- Alembic: unchanged single head `3f403ab7f7d7`; offline upgrade SQL generated;
  online schema-drift and upgrade/downgrade/upgrade checks passed in the test suite.
- `docker compose config --quiet` and `git diff --check`: passed.
- New integration checks exercise committed reservations with no transaction during
  generation, same-conversation exclusion, independent conversations, expired/late
  worker recovery, failed final-commit recovery, profile updates, history filtering,
  pagination, ownership, and application-restart persistence.
- All provider calls use scripted fakes or mocked SDK clients. A global test fixture
  rejects live HTTP transport. No OpenAI API key or paid generation was used.

Two existing Starlette/AnyIO deprecation warnings remain. This validates transport
mapping and pipeline behavior, not real model output quality. The full Compose
stack was not started; the built application image and disposable PostgreSQL were
validated directly. No schema migration was introduced.

Reproduce local validation with a disposable container:

```sh
docker run --detach --rm --name assistant-task5-test \
  -e POSTGRES_PASSWORD=task5-local -e POSTGRES_DB=assistant_task5_test \
  -p 127.0.0.1:55435:5432 postgres:17
docker exec assistant-task5-test pg_isready -U postgres -d assistant_task5_test
TEST_DATABASE_URL=postgresql+psycopg://postgres:task5-local@127.0.0.1:55435/assistant_task5_test \
  .venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pip check
```

For the declared Python 3.12 runtime:

```sh
docker build -t assistant-task5-validation .
docker run --rm --network container:assistant-task5-test \
  -e TEST_DATABASE_URL=postgresql+psycopg://postgres:task5-local@127.0.0.1:5432/assistant_task5_test \
  assistant-task5-validation sh -c \
  'python --version && pytest -q && ruff check . && ruff format --check . && mypy && pip check'
docker stop assistant-task5-test
```

## Task 6 behavioral evaluation (2026-09-07)

Eight checkpoints were implemented and committed independently after validation.
Schema, runner, cases, reporting, and comparison checkpoint tests passed before
commits; the documentation checkpoint passed a contract-content smoke check.

Final evidence:

- Host Python 3.13: **164 passed**, including all PostgreSQL integration tests,
  using disposable `assistant_task6_test` on loopback port 55436. The temporary
  container was stopped and removed after validation.
- Ruff check, Ruff format check, strict mypy, dependency check, and diff whitespace
  check passed.
- Built `assistant-task6-validation` with Python 3.12.14; includes evaluation
  fixtures so the CLI and new tests work in Docker. Container checks: **120 passed,
  44 database tests skipped**, Ruff, format, mypy, and dependency checks passed.
- Existing two Starlette/AnyIO deprecation warnings remain.
- Offline CLI comparison ran all 18 cases in two arms: 36 results, 0 provider errors,
  5 expected objective failures on placeholder text, 31 pending human review.
  Exit code 1 is expected. Local JSON/Markdown artifacts are under the gitignored
  `evaluation-results/task6-smoke/` directory.
- No API key or model is configured, so no live calls were made. Personality,
  language compliance, and personalization quality have **not** been measured.

The harness has 11 focused tests covering suite validation, duplicate IDs, history,
repetition/arm isolation, model parity, provider failures, blank output, objective
checks, serialization, CLI filtering and output protection. Review rubrics use
0/1/2 scoring recorded manually; reports intentionally do not declare an overall
behavioral pass. Baseline comparison uses the same model/provider settings and
fresh history per arm, but a live study should use repeated trials and blinded
human review to reduce stochastic and reviewer effects.

## Task 7 context budgets (2026-09-08)

Implemented and validated all ten checkpoints, with a commit after each step's
checks. Changes include explicit model budget configuration, conservative local
UTF-8 token estimates, mandatory-content overflow rejection, lazy paginated history,
per-request output limits, and content-free diagnostics. No schema migration or
new dependency was introduced.

Final evidence:

- Host Python 3.13.1: **222 passed, no skips**, against disposable PostgreSQL 17
  in `assistant-task7-test`, database `assistant_task7_test`, loopback port 55437.
- Built `assistant-task7-validation`, Python 3.12.14: **222 passed, no skips**,
  against the same isolated PostgreSQL database after the local run completed.
- Ruff lint/format, strict mypy (57 source files), and dependency checks passed
  on both runtimes. `git diff --check` passed.
- Alembic has the unchanged single head `3f403ab7f7d7`; offline upgrade SQL
  generated successfully. Integration tests passed upgrade/downgrade/upgrade
  and schema-drift checks. `docker compose config --quiet` passed.
- Offline evaluation comparison: 36 results, 0 provider errors, 5 expected
  objective failures on placeholder text, 31 pending human review. All request
  estimates stayed within their budgets. Artifacts are gitignored under
  `evaluation-results/task7-validation/`. CLI exit 1 is expected for this smoke.
- The live CLI path was tested with a mocked SDK, including model budget
  enforcement and per-model output overrides. No API credentials or paid calls
  were used. Provider transport is mocked and live HTTP is blocked by the test
  fixture; no real-model token usage or output quality is claimed.

Review/regression coverage includes exact mandatory and whole-turn boundaries,
multilingual text compared with brute-force valid suffixes, injected counters,
failed/cancelled/interrupted/orphaned messages, lazy-read stopping, pair boundaries
across pages, scan caps, retrieval beyond 40 messages, atomic rejection, model
changes, output-limit snapshots, untouched stored history, and diagnostic privacy.
Review tightened the history scan-limit snapshot so logs use the limit applied to
that request. Existing ownership, concurrency, lease recovery, and persistence
tests continue to pass.

Two existing Starlette/AnyIO deprecation warnings remain on both runtimes. The
full Compose application stack was not started; the built application image and
real disposable database were tested directly. The test database container was
stopped and removed after validation.

Reproduction:

```sh
docker run --detach --rm --name assistant-task7-test \
  -e POSTGRES_PASSWORD=task7-local -e POSTGRES_DB=assistant_task7_test \
  -p 127.0.0.1:55437:5432 postgres:17
# Wait for readiness before running the suite:
docker exec assistant-task7-test pg_isready -U postgres -d assistant_task7_test
TEST_DATABASE_URL=postgresql+psycopg://postgres:task7-local@127.0.0.1:55437/assistant_task7_test \
  .venv/bin/pytest -q
docker build -t assistant-task7-validation .
docker run --rm --network container:assistant-task7-test \
  -e TEST_DATABASE_URL=postgresql+psycopg://postgres:task7-local@127.0.0.1:5432/assistant_task7_test \
  assistant-task7-validation sh -c \
  'python --version && pytest -q && ruff check . && ruff format --check . && mypy && pip check'
docker stop assistant-task7-test
```

Operational change: existing deployments need a matching `CONTEXT_MODEL_BUDGETS`
entry for every selected model. See [Task 7](docs/task-7.md) and the README for the
configuration contract and estimator limitations.

## Task 8 streaming and lifecycle (2026-09-08)

Implemented the seven execution checkpoints with a separate tested commit for
contracts, lifecycle operations, async provider streaming, SSE transport,
cancellation, failure recovery, and final validation/documentation. The execution
plan file was deleted after implementation as requested. The README retains the
public API, client examples, settings, and operational limitations.

Checkpoint evidence:

| Checkpoint | Validation before commit |
| --- | --- |
| Event contracts and limits | 5 contract/configuration tests; Ruff and mypy |
| Shared lifecycle operations | 23 existing pipeline tests and 2 new PostgreSQL lifecycle/race tests; Ruff and mypy |
| Async provider | 34 provider/adapter/evaluation tests; Ruff and mypy |
| SSE endpoint | 3 PostgreSQL/HTTP tests, including real incremental delivery and keepalives; Ruff and mypy |
| Cancellation | 8 lifecycle/stream tests, including separate app instances and real socket disconnect; Ruff and mypy |
| Failure recovery | 11 failure/timeout/recovery tests; Ruff and mypy; 17 combined stream/lifecycle cases before the final lease additions |
| Final review and documentation | Full local and container suites plus browser parser tests and static checks below |

Final evidence:

- Local Python 3.13.1: **257 passed, no skips**, against disposable PostgreSQL 17
  in `assistant-task8-test`, database `assistant_task8_test`, loopback port 55432.
- Built `assistant-task8-validation`, Python 3.12.14: **257 passed, no skips**,
  against that same disposable database after the host suite finished.
- Ruff lint/format, strict mypy (65 source files), and dependency checks passed
  on both runtimes. `git diff --check` and `docker compose config --quiet` passed.
- Browser example parser: **4 Node tests passed**, including one-byte network
  chunks splitting Unicode, comment keepalives, authoritative terminal text,
  missing terminal events, unknown outcomes, and sequence rejection.
- Alembic retained the single head `3f403ab7f7d7`. Offline upgrade SQL generated;
  migration round trips and schema-drift checks passed in the integration suite.
  No schema migration was needed; AnyIO is now an explicit dependency.
- Offline evaluation comparison: 36 results, 0 provider errors, 5 expected
  objective failures on fake text, 31 pending human review. Exit code 1 is
  expected; temporary artifacts were written to `/tmp/assistant-task8-evaluation`.
- No paid or live provider calls were made. Both sync and async HTTPX transports
  are blocked in automated tests. Real transport tests use loopback HTTP with
  fake generation, while adapter tests mock the installed OpenAI SDK 2.54.0.

Review fixed the expired-JSON-failure path to preserve HTTP 409, validated that
SSE event payloads match their event/state, bounded upstream cleanup waits, and
made blocked queue delivery respect the overall generation deadline. Coverage
includes terminal races, foreign ownership, failed/cancelled history exclusion,
partial output and output caps, blank/incomplete output, idle/overall timeouts,
lease renewal/expiry, persistence outage with unknown outcome, slow ASGI sends,
content-free metrics, and SDK/client cleanup. A subprocess commits a partial
checkpoint then exits abruptly; recovery retains that prefix and excludes the
interrupted turn from subsequent context after simulated lease expiry.

Two pre-existing Starlette/AnyIO deprecation warnings remain. Reverse-proxy
buffering, live model behavior, and the full Compose stack were not exercised.
Cancellation/persistence latency depends on database responsiveness; JSON upstream
calls remain synchronous. The README documents these limits, lazy recovery, and
lack of replay/idempotent retries.

Reproduction while the disposable database is running:

```sh
TEST_DATABASE_URL=postgresql+psycopg://postgres:task8-local@127.0.0.1:55432/assistant_task8_test \
  .venv/bin/pytest -q
node --test examples/stream-client.test.mjs
docker build -t assistant-task8-validation .
docker run --rm --network container:assistant-task8-test \
  -e TEST_DATABASE_URL=postgresql+psycopg://postgres:task8-local@127.0.0.1:5432/assistant_task8_test \
  assistant-task8-validation sh -c \
  'python --version && pytest -q && ruff check . && ruff format --check . && mypy && pip check'
```

## Browser test client — 2026-09-08

- Full regression against disposable PostgreSQL 17: **258 passed**, no skips.
- Shared streaming helper: **4 Node tests passed**. Client JavaScript syntax,
  Ruff lint/format, mypy, and diff whitespace checks passed.
- Browser smoke against FastAPI plus disposable PostgreSQL and a delayed fake
  streaming provider: connected, saved a profile, created a conversation, observed
  a completed response, stopped another response, reloaded/reconnected, and
  verified both durable message statuses and saved settings. Visually inspected
  the desktop layout and corrected overflowing settings layout.
- Static asset test verifies page redirect/loading, JavaScript and CSS MIME types,
  missing-asset 404, and unchanged API authentication requirements.
- No real model calls were made. The complete Compose stack and mobile browser
  layout were not exercised in this change. Two existing dependency deprecation
  warnings remain.

## Personalization step 1 — personal chat interface

- Added `/ui/` with responsive chat, a native settings dialog, three curated
  appearances, communication presets/examples, and response refinement shortcuts.
  Reused the existing streaming/cancellation client; `/test-client/` is preserved.
- Appearance is temporarily device-local and profile-keyed; step 2 moves it to
  validated server persistence. Communication uses the existing profile endpoint.
- Fixed an existing disabled-auth test's accidental dependency on the local `.env`.
- Validation: 259 Python tests passed against disposable PostgreSQL 17; 5 Node
  tests passed; Ruff lint/format, mypy, and JavaScript syntax checks passed.
  `/ui/` returned HTTP 200 from the local preview. No live model call was made.

## Personalization step 2 — persisted AI theme previews

- Added migration `9a01`, a bounded theme schema with contrast validation,
  authenticated generation/save/read routes, and an unsaved communication preview.
- Appearance now persists in PostgreSQL; the UI isolates draft previews until
  Apply. Invalid/unreadable provider output preserves the last saved appearance.
- Validation: 271 Python tests passed including PostgreSQL migration round-trip,
  persistence/isolation, failed previews, theme contrast, and schema drift checks.
  Ruff, mypy, JS syntax and all 5 Node tests passed. Provider calls used fakes;
  actual model theme quality is not established by these automated checks.

## Personalization step 3 — explicit, bounded memory

- Added migration `9a02`, owned note CRUD, user-message source validation, a
  serialized 20-note limit, and a reviewed “Remember this” flow in `/ui/`.
- Both generation paths select whole notes within a fixed bounded allocation.
  Omission IDs are exposed in JSON and SSE and shown in the interface.
- Validation: 279 Python tests passed against disposable PostgreSQL, including
  cross-conversation recall inputs, correction/deletion, ownership, concurrent
  cap enforcement, streaming omission reports, migration round-trip and drift.
  All 5 Node tests, Ruff, formatting, mypy, and JS syntax checks passed.
- Updated evaluation diagnostic typing for memory ID tuples; no new serializer
  warnings remain. Model behavior was tested with fake providers, not live calls.

## Final browser validation — first personalization release

- Added a repeatable Chrome/Playwright flow and an explicitly opt-in fake-provider
  server that rejects databases not ending in `_test` and ignores the local `.env`.
- Browser checks passed: curated and generated previews, Apply, persistence after
  reload, invalid generation preserving saved appearance, Reset, communication
  saving and live-sample plumbing, reviewed memory creation, edit/delete, streaming,
  cancellation, response refinement, Escape/focus return, and disconnect cleanup.
- Inspected desktop and mobile screenshots. Fixed header overflow at 200% text
  size, kept the settings heading available while scrolling, and collapsed the
  connection panel after connecting. Both chat and settings pass horizontal
  overflow checks at 390px width with normal and 200% text sizing.
- Final checks: 279 Python tests passed in the full PostgreSQL suite; 5 Node tests
  passed; Chrome workflow passed; Ruff lint/format, mypy (76 files), JavaScript
  syntax, migration SQL generation, and git whitespace checks passed.
- Two existing dependency deprecation warnings remain. No live paid model calls
  were made: generated-theme quality and subjective communication quality still
  need evaluation with the chosen model during the planned personal trial.
- Temporary test server and disposable database are stopped after validation.
  Existing development data was not migrated or changed by this work.
