# Personalized AI Assistant

Tasks 1–8: Python 3.12+, FastAPI, Pydantic settings, SQLAlchemy/PostgreSQL,
User/AssistantProfile/Conversation/Message models, Alembic migrations, pytest,
single-user bearer authentication, assistant settings, deterministic behavior compilation,
non-streaming OpenAI conversation/message APIs, behavioral evaluations,
model-specific context budgets, SSE streaming and cancellation, and local Docker development.

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
- Task 7 replaces the initial character guard with explicit model token budgets
  and bounded, paginated history selection.
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
Also configure a matching entry in `CONTEXT_MODEL_BUDGETS` as described below.
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

## Context budgets (Task 7)

Existing deployments must add `CONTEXT_MODEL_BUDGETS` before sending messages or
running live evaluations. Each selected model, including a profile's preferred
model, needs an exact-name entry. Missing entries return HTTP 503 before reserving
a turn. Conversation creation, history retrieval, and health checks still work.

Example `.env` configuration (replace `YOUR_MODEL`; 8192 is an illustrative
application capacity, not a claim about your model's context window):

```dotenv
OPENAI_MODEL=YOUR_MODEL
OPENAI_MAX_OUTPUT_TOKENS=2048
CONTEXT_MODEL_BUDGETS={"YOUR_MODEL":{"context_window_tokens":8192,"safety_margin_tokens":1024}}
CONTEXT_HISTORY_SCAN_LIMIT=10000
```

Verify the model's supported context and output limits before setting these values.
You can use a smaller context capacity as an application limit. A per-model
`max_output_tokens` overrides `OPENAI_MAX_OUTPUT_TOKENS`. Restart the API after
configuration changes. Invalid budgets fail settings validation at startup.

The example leaves 5120 estimated input tokens after reserving output and safety
margin. The offline estimator counts UTF-8 bytes of content and role names plus
16 tokens per message and 16 per request. It is deliberately conservative and
may retain less history than an exact tokenizer; counts are not provider usage.
The output reserve covers visible text and reasoning tokens.

Platform instructions, the latest compiled behavior, and the current message are
always retained. If they exceed the allowance, sending returns HTTP 422 without
saving a turn or calling the provider. Otherwise, the request includes the newest
complete eligible turns that fit. Older messages remain available through GET.
History is read in batches of 100 messages, up to the configured scan limit
(2–100000, default 10000). Failed, cancelled, interrupted, and orphaned messages
are excluded. Provider-side automatic truncation is disabled.

Live evaluations use the same budget resolution. Offline smoke runs use a fixed
synthetic 32768-token capacity with a 2048-token output reserve and 1024-token
margin, independent of live settings. JSON reports include budget diagnostics.
See [Task 7](docs/task-7.md) for estimation limits, logging, and validation details.


## Streaming and cancellation (Task 8)

The existing JSON send endpoint still returns HTTP 201 with a complete turn.
For incremental delivery, POST the same body to the authenticated streaming endpoint:

```sh
curl -N --fail-with-body -X POST \
  "http://localhost:8000/conversations/$CONVERSATION_ID/messages/stream" \
  -H "Authorization: Bearer $AUTH_TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"Explain how streaming works."}'
```

Setup validates ownership, input, provider/model configuration, context budget,
and the active-turn lock before returning HTTP 200 `text/event-stream`.
Setup failures retain the JSON API's 401/404/409/422/503 semantics and do not
create a new turn. After headers, failures are reported through SSE; a successful
HTTP status alone does not mean generation succeeded.

Each JSON event has `event`, `message_id`, `sequence`, and `payload`. Sequence
numbers begin at 1 and increase within this connection. They are not replay IDs;
reconnection and `Last-Event-ID` replay are not supported. SSE comments keep an
idle connection alive.

| Event | Payload and client action |
| --- | --- |
| `turn.started` | Saved `user_message` and `assistant_message`; remember the assistant ID |
| `message.delta` | Append `text` to provisional displayed content |
| `message.completed` | Replace displayed text with the saved `message` |
| `message.cancelled` | Replace displayed text with the saved `message`; generation stopped |
| `message.failed` | Saved partial `message` and safe `error_code`; generation failed |
| `stream.error` | `code: outcome_unknown`; fetch history to determine the durable outcome |

Failure codes are `generation_failed`, `generation_timeout`, `output_limit`, and
`lease_expired`. They are event diagnostics, not persisted message fields. A
normal connected stream ends after one terminal message event. EOF without a
terminal event is an unknown outcome. Fetch history before resending: repeated
POSTs create new turns, and there are no automatic retries.

Use the tested [browser client example](examples/stream-client.mjs) with `fetch`
and a bearer header. It parses frames and UTF-8 across arbitrary network chunk
boundaries, ignores keepalives, and returns the authoritative terminal message:

```js
import { streamTurn, cancelTurn } from "./examples/stream-client.mjs";

let messageId;
const saved = await streamTurn({
  conversationId, token, content: "Hello",
  onEvent(event) {
    if (event.event === "turn.started") messageId = event.message_id;
    // Render message.delta provisionally; use the returned saved content at the end.
  },
});
// A separate Stop button can call this while streamTurn is still pending:
// await cancelTurn({ conversationId, messageId, token });
```

Serve the example from the same origin as the API, or configure cross-origin
access separately. No browser UI or CORS policy is added by Task 8. A caller may
also pass an AbortSignal; aborting or losing the connection triggers server-side
cancellation. Catch client errors and reconcile with saved message history.
Run the example's parser tests with `node --test examples/stream-client.test.mjs`.

To cancel explicitly after receiving the assistant ID:

```sh
ASSISTANT_MESSAGE_ID=replace-with-id-from-turn.started
curl --fail-with-body -X POST \
  "http://localhost:8000/conversations/$CONVERSATION_ID/messages/$ASSISTANT_MESSAGE_ID/cancel" \
  -H "Authorization: Bearer $AUTH_TOKEN"
```

Cancellation returns the saved message. Repeated cancellation of any terminal
assistant message returns its unchanged state. Missing/foreign resources return
404; targeting a user message returns 409. The first committed terminal transition
wins: completion already committed remains completed. Cancellation is stored in
PostgreSQL and observed across workers without shared process memory.

User messages remain completed; assistants transition from `in_progress` to
`completed`, `cancelled`, or `failed`. Streaming saves partial text periodically
and on terminal transitions. Explicit cancellation preserves the latest durable
prefix, which can be shorter than provisional text already displayed. No late
worker may append to a terminal message. Failed and cancelled turns are excluded
from future context. The JSON endpoint retains empty content on provider failure;
cancellation prevents its late result from being saved, returning 409 when it
wins, but its synchronous upstream call is not interrupted immediately.

### Streaming settings and recovery

| Environment setting | Default | Purpose |
| --- | --- | --- |
| `STREAM_DEADLINE_SECONDS` | 120 | Overall generation deadline, independent of incoming deltas |
| `STREAM_IDLE_SECONDS` | 30 | Maximum wait without a text/completion event, including the first token |
| `STREAM_HEARTBEAT_SECONDS` | 10 | SSE keepalive interval |
| `STREAM_POLL_SECONDS` | 0.5 | Database cancellation checks and lease heartbeats |
| `STREAM_CHECKPOINT_SECONDS` | 1 | Partial text save cadence, checked during polling |
| `STREAM_SEND_TIMEOUT_SECONDS` | 10 | Maximum blocked queue/ASGI send time and upstream cleanup wait |
| `STREAM_MAX_OUTPUT_BYTES` | 262144 | UTF-8 output cap, in addition to the model token allowance |

Polling and checkpoint intervals must each be less than one third of
`GENERATION_LEASE_SECONDS`. All intervals are positive and finite. Restart after
changing settings. The upstream SDK also retains `OPENAI_TIMEOUT_SECONDS` and
zero retries. There is one queued frame per stream and bounded accumulated text;
a blocked consumer is cancelled after the send timeout. Generation deadlines do
not include the time needed to persist the outcome or clean up resources.

Normally cancellation is observed at the next poll plus database time. A blocked
send can add up to the send timeout; closing upstream can take a further cleanup
interval. Database availability and responsive database locks are required for
prompt persistence. No transaction or row lock is held during provider/network
waits, and each streaming DB operation owns its session within a worker thread.

`updated_at` continues to serve as the assistant's lease heartbeat, so it can
change without new content. If a process dies or persistence fails, a subsequent
valid send recovers the expired lease as failed and retains its last checkpoint.
GET can show `in_progress` until recovery occurs. There is no sweeper, replay log,
or background generation job, and uncheckpointed text may be lost on a crash.

Responses disable caching and request proxy buffering be disabled. Configure the
actual reverse proxy to stream without buffering or compression-induced delays,
and set its idle timeout above the heartbeat interval. The server header alone
does not configure every proxy.

INFO logs expose content-free `stream_metrics` (outcome, duration, time to first
delta, and observed cancellation age). The age uses the database timestamp and
application clock; it is approximate. Context logs also include a recovered-turn
count. No prompts, generated text, credentials, or upstream diagnostics are logged.

The adapter consumes typed text and completion events as described in the
[official OpenAI streaming guide](https://developers.openai.com/api/docs/guides/streaming-responses),
checked alongside installed SDK 2.54.0. EOF, incomplete responses, and blank
output are failures. Automated validation uses fakes/mocked SDKs, including real
loopback HTTP transport tests; no paid provider calls are required.

## Browser test client

Start the API using the local Python or Docker instructions above, apply migrations,
and provision the assistant. Open **http://localhost:8000/test-client/** and paste
`AUTH_TOKEN` into the connection form. The token stays in page memory, is cleared
on disconnect/reload, and is never stored in browser storage. The static page is
public; every assistant/conversation request still requires bearer authentication.
No frontend dependencies, build step, or CORS configuration are needed.

Create/select a conversation, send a message, and use **Stop** during generation.
Saved history is fetched in pages of 100; **Load more** pages the conversation list.
**Refresh history** reconciles durable state after an interrupted request. No send
is automatically retried. If history cannot be fetched, sending stays disabled until
refresh succeeds. An active server turn may return 409 until it finishes or its lease
expires. Profile settings apply to the next turn; greeting settings retain the
backend's existing behavior and do not schedule proactive messages.

Manual smoke checklist (use a disposable development database):

- Invalid token shows an error; valid token loads settings and conversations.
- Create a conversation, send, observe incremental text, and stop a long response.
- Reload, reconnect, and select the conversation to verify saved history.
- Save profile changes and verify them after reconnecting.
- Interrupt a stream and refresh history before deciding whether to resend.
- With a configured real provider, compare default/customized behavior using the
  evaluation CLI above. Real-model smoke tests make paid provider calls.

Run `pytest -q` (set `TEST_DATABASE_URL` for database tests) and
`node --test examples/stream-client.test.mjs`. The example re-exports the same stream
implementation shipped with the browser client.

## Personal interface

Open `/ui/` on the running API for the everyday chat interface. Connect with the
same bearer token used by the API; it stays in tab memory. The original
`/test-client/` remains available for diagnostics. Personalize opens appearance
and communication controls. “Shorter” and “More detail” prepare a follow-up for
review before sending and do not change saved preferences.

Appearance is saved per assistant in PostgreSQL. Run `alembic upgrade head` before
using this version. In Personalize, choose a curated look or describe one, review
the preview, then Apply. Reset restores the clean default. Generating/refining a
theme and trying a live communication sample each make one bounded model request;
saving or switching an appearance does not. Failed previews leave saved settings
unchanged. Generation requires the existing model, API key, and context budget.

The authenticated appearance API is `GET/PUT /assistant/theme`, with
`POST /assistant/theme/generate` for an unsaved preview. Themes contain only
validated style tokens, with 4.5:1 text/accent contrast on both surfaces.
`POST /assistant/preview` accepts `{ "changes": { "verbosity": 0.2 } }` and
returns a live style sample without saving preferences or conversation messages.

Memory is explicit: use “Remember this” on one of your own messages, review the
text, then Save note. Personalize → Memory also supports adding, editing, and
deleting notes directly. Up to 20 notes of 300 characters are allowed per user.
Tone and language remain in Communication. No notes are extracted automatically.

The authenticated API is `GET/POST /memories`, and `PATCH/DELETE /memories/{id}`.
Creation accepts `content` and an optional `source_message_id` belonging to one
of your user messages; editing accepts only `content`. Notes are ordered by latest
update, then ID. Requests include whole notes within at most 1024 estimated tokens
and at most one quarter of the input remaining after required instructions and
the current message. Skipped IDs are returned as `omitted_memory_ids` in JSON
turn results and streaming `turn.started`; the UI identifies skipped notes for
the current request. The existing estimator counts UTF-8 bytes conservatively.

Edits and deletion affect requests assembled afterwards, including new
conversations. They cannot change an in-flight request, remove original messages
from chat history, or undo information already sent to the model provider.
The model receives notes as quoted user context, with explicit precedence for
platform rules, current requests, and communication settings.

### Browser regression checks

With the disposable `TEST_DATABASE_URL` configured as described above, run
`.venv/bin/python -m tests.ui_server` in one terminal. This test-only server uses
synthetic responses and a fixed test identity on `127.0.0.1:8011`; do not run it
against your development data or use it as your actual assistant.

In another terminal, run `node tests/ui.e2e.cjs` with Playwright resolvable by Node
and Google Chrome installed. If using a bundled Playwright installation, point
`NODE_PATH` at its `node_modules` directory. Screenshots go to
`/tmp/assistant-ui-validation` (override with `UI_TEST_OUTPUT`). The test verifies
the fixture identity before changing data. Stop the fixture server afterwards.

The first release is implemented. In-app reminders and an agenda/weather Today
card remain the separate follow-up milestone in the personalization plan.
