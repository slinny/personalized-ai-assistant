# Task 5 conversation pipeline

Implementation checkpoints: API contract, provider interface/fake, OpenAI adapter,
context assembly, lifecycle orchestration, integration tests, final documentation
and regression validation. Each checkpoint is validated before committing.

API: authenticated POST /conversations, GET /conversations (limit 1–100, offset),
GET /conversations/{id}/messages (limit 1–100, after_position), and
POST /conversations/{id}/messages with {"content": "..."}. Send returns a complete
user_message/assistant_message pair. Content is 1–20,000 characters, nonblank,
with whitespace preserved; extra request fields are rejected. Missing and foreign
conversations return the same 404. Creation requires an existing owned profile.
Conversation listings sort newest first, messages by their integer position.

The send endpoint is wired at the lifecycle checkpoint. Existing tables are reused.

## Provider and context

The synchronous provider protocol accepts immutable model/message values and returns
complete text. Production uses the OpenAI Python SDK Responses API with stream=false,
store=false, and no SDK retries. The application owns history in PostgreSQL; no
OpenAI conversation IDs or previous-response IDs are used. The SDK client is shared
for the application lifespan and closed at shutdown. Sync routes run in FastAPI's
thread pool.

OPENAI_API_KEY enables the production provider. The latest assistant profile's
preferred_model takes precedence over OPENAI_MODEL. No model is hardcoded. Missing
provider/model configuration returns 503 without reserving a turn. Timeout defaults
to 30 seconds; output is capped at 2,048 tokens. GENERATION_LEASE_SECONDS defaults
to 180 and must exceed the configured provider timeout. SDK timeouts apply to network
operations, not a strict wall-clock generation deadline; the lease also guards late
finalization. No automatic retry is performed after uncertain upstream outcomes.

Every request contains platform instructions as a system message, compiled behavior
as a developer message, eligible history, and the current user message exactly once.
Behavior is recompiled from the latest profile for each turn. Greeting/holiday
scheduling remains outside this milestone, consistent with Task 4.

Context considers the last 40 stored messages, includes only adjacent completed
user/assistant pairs, and drops both messages of failed or interrupted turns. It
keeps a contiguous recent suffix of eligible pairs, at most 20 turns, within a
100,000-character total including instructions and the current user message. Old
messages remain retrievable. This is a conservative application character bound,
not a model-specific token guarantee; full token budgeting belongs to Task 7.

The paragraph above describes the original Task 5 policy. Task 7 supersedes it
with explicit model budgets, output/margin reserves, offline token estimates,
and bounded paginated history. See [Task 7](task-7.md) for the current policy;
the old 40-message, 20-turn, and 100000-character limits no longer apply.

## Transactions and failure behavior

1. Lock the owned conversation row. Reject an unexpired active generation with 409.
   Mark expired reservations failed, assemble context, allocate consecutive positions,
   insert a completed user message and in_progress assistant placeholder, and commit.
2. Call the provider with no database transaction or row lock held.
3. Lock the conversation again. Finalize only the same unexpired in_progress message;
   save completed text or mark it failed, update timestamps, and commit before returning.

Success returns HTTP 201 with user_message and assistant_message objects. An upstream
timeout returns 504; other provider failures, incomplete responses, or blank output
return a sanitized 502. Failed assistant content stays empty and its user message
remains completed. Clients can retrieve the stored failure using the messages endpoint.
Unexpected provider exceptions are sanitized as well. Validation failures return 422.

Recovery is lazy on the next send: expired assistant reservations become failed and
a new turn can proceed. A late worker gets 409 and cannot overwrite recovered state.
An expired response is failed even if no new turn has begun. There is no background
sweeper; GET may show an interrupted reservation as in_progress until the next send.
Database outages can leave a reservation pending until recovery is possible. Database
errors propagate as server failures rather than falsely reporting a saved reply.

A repeated POST creates a new turn; this API does not promise idempotent retries.
After a lost HTTP response, retrieve history before deciding whether to send again.
Only application service writes enforce the one-active-turn rule; administrative
SQL must respect the same contract. No schema migration is needed.

## Automated validation

FakeProvider scripts text or errors, captures immutable requests, and fails when its
script is exhausted. It is injected through get_provider overrides, never selected
through production configuration. Adapter tests mock the SDK client. The global
test fixture rejects live HTTP transport calls; PostgreSQL integration tests use
real independent connections for concurrency and durability.

Coverage includes ownership, input validation, pagination, profile/model updates,
multi-turn history, lifecycle transitions, sanitized failures, transaction release,
concurrent sends, independent conversations, stale-worker recovery, final-commit
failure recovery, and persistence across application restarts. Tests establish the
pipeline contract, not live model quality or language/personality compliance.

Checkpoint validation before commits:

- API contract: full PostgreSQL suite, 123 passed; Ruff and mypy passed.
- Provider interface/fake: 7 focused provider/auth tests; Ruff and mypy passed.
- OpenAI adapter: 24 focused tests; Ruff, mypy, and dependency checks passed.
- Context assembly: 56 context/compiler tests; Ruff and mypy passed.
- Lifecycle: 2 PostgreSQL API/lifecycle tests; Ruff and mypy passed.
- Expanded automated tests: full PostgreSQL suite, 153 passed; Ruff and mypy passed.
- Final documentation/runtime validation: see VALIDATION.md for verified results.
