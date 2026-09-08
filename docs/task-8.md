# Task 8 execution plan: streaming and message lifecycle

Status: proposed; implementation has not started.

## Objective and scope

Stream assistant text as it is generated, expose durable lifecycle outcomes, let
clients stop generation, and recover safely from provider, connection, and process
failures. Preserve Task 7 context selection and the existing non-streaming API.

The repository already has `in_progress`, `completed`, `cancelled`, and `failed`
message states, a conversation-row lock, and lazy expired-lease recovery.
`send_message` currently performs reservation, synchronous generation, and
finalization together. Task 8 should reuse those invariants and split their
implementation into shared lifecycle operations.

This milestone covers the backend and a documented client consumption example.
UI implementation, automatic retries, request idempotency, resumable SSE replay,
background generation jobs, and new providers remain separate work.

## Proposed API and lifecycle contract

- Keep `POST /conversations/{id}/messages` and its HTTP 201 JSON response.
- Add `POST /conversations/{id}/messages/stream` with the same validated request
  body and bearer authentication. Successful setup returns HTTP 200 with
  `Content-Type: text/event-stream`.
- Add `POST /conversations/{id}/messages/{message_id}/cancel`. Scope the message
  to the owned conversation. Return the persisted message after cancellation;
  repeated requests for an already terminal assistant message return its existing
  state without changing it. Missing/foreign resources return 404; a user-message
  target returns 409.
- User messages are saved as `completed` at reservation. Assistant messages move
  from `in_progress` to exactly one of `completed`, `cancelled`, or `failed`.
  Terminal states are immutable. The first valid committed terminal transition
  wins a completion/cancellation race.
- Provider-confirmed, nonblank complete output is required for `completed`.
  EOF alone, partial output, and output-limit termination are not success.
- Preserve partial assistant text for streaming cancellations and failures, but
  exclude the entire unsuccessful turn from future context. The existing JSON
  endpoint retains its empty-content behavior for provider failures.
- Client disconnect requests cancellation and closes the provider stream.
  If completion already committed, retain `completed`. A lost connection cannot
  carry a terminal event; clients reconcile through message history.

### SSE events

Use JSON payloads, safely serialized within SSE frames. Include the assistant
message ID on every message event and monotonically increasing per-stream sequence
numbers. Sequence numbers support ordering checks, not reconnection/replay.

| Event | Meaning and payload |
| --- | --- |
| `turn.started` | Reservation committed; includes saved user and assistant messages |
| `message.delta` | Append this text delta to the displayed assistant content |
| `message.completed` | Completion committed; includes the authoritative saved message |
| `message.cancelled` | Cancellation committed; includes the authoritative saved message |
| `message.failed` | Failure committed; includes saved partial text and a sanitized error code |
| `stream.error` | Persistence/transport processing failed; durable outcome is unknown, so fetch history |

Send periodic SSE comments as keepalives. An ordinarily connected, finalized stream
emits one terminal message event, then closes. Never claim completion or another
durable outcome before its database commit succeeds. A database failure may allow
only a best-effort `stream.error` or connection close, not a terminal message event.

Authentication, ownership, input validation, provider/model configuration, context
overflow, and active-turn checks run before response headers are sent. Preserve
their existing HTTP error semantics. Failures after streaming starts use events;
HTTP status cannot be changed at that point. Do not expose SDK exception text,
credentials, prompts, or database details.

## Implementation checkpoints

### 1. Lock down contracts and resource limits

Define typed event payloads, transition rules, safe failure codes, and client
reconciliation behavior in `app/schemas/conversation.py` and provider contracts.
Specify configurable overall generation deadline, upstream idle timeout, heartbeat
interval, cancellation polling interval, partial-save interval, output byte cap,
and bounded send-buffer behavior. Validate their relationships to the lease.
Establish one explicit policy for slow consumers: bounded buffering followed by
cancellation when the send deadline expires.

Acceptance: contract tests cover event serialization (including newlines and
Unicode), invalid transitions, and configuration boundaries.

### 2. Extract shared lifecycle operations

Refactor `app/services/conversation.py` into reservation, partial checkpoint,
cancellation, and terminal finalization operations. Keep context assembly and
budget/model snapshots unchanged. Use short independent transactions and the same
conversation-first lock ordering for every writer. Return immutable values across
the database/provider boundary.

Every update must target the original assistant message, require `in_progress`,
and check lease validity. A late worker must never revive an expired or cancelled
message, modify a terminal message, or overwrite a newer turn. Use explicit lease
timestamps if needed rather than overloading public `updated_at`; add a migration
only for required persisted fields. Existing status values need no migration.

Acceptance: existing JSON pipeline tests pass, including ownership, concurrent
sends, transaction release, expired-worker protection, and context overflow with
no reservation. Test competing terminal transitions using independent DB sessions.

### 3. Add a cancellable provider streaming interface

Preserve `generate()` for the JSON endpoint and evaluation runner. Add an async
streaming contract with text deltas and an explicit successful completion signal,
plus deterministic scripted streaming fakes. Implement the OpenAI adapter after
checking the installed SDK's streaming event and cleanup contracts.

Retain the resolved model/output allowance, `store=False`, disabled provider-side
truncation, and zero automatic retries. Map timeout, upstream error, incomplete
response, blank output, and unexpected EOF into sanitized failures. Ensure stream
resources close on success, failure, cancellation, and deadline expiry. Manage the
async client through application lifespan alongside the existing sync client.

Acceptance: mocked adapter tests verify deltas, explicit completion, failure
mapping, request options, and cleanup without live calls.

### 4. Build the streaming coordinator and SSE endpoint

Add a focused streaming service and wire it into `app/api/conversations.py`.
Reserve before returning the streaming response; emit `turn.started` only after
commit. Consume provider events while independently handling keepalives,
cancellation checks, deadlines, and disconnects, including before the first token.

Keep synchronous SQLAlchemy work off the event loop. Each DB operation creates,
uses, and closes its own session within one worker invocation; do not share a
request session across threads or concurrent tasks. Do not hold a transaction
while awaiting the provider or sending bytes to the client.

Checkpoint accumulated partial text on a bounded cadence, with a final save on
normal terminal transitions. Preserve delta order and enforce output/buffer caps.
Disable caching and document proxy buffering/timeout requirements. Stop and await
all per-stream helper tasks when the stream closes, even if iteration never starts.

Acceptance: a controlled provider proves the first delta arrives before generation
finishes, keepalives work during a stall, and independent streams remain responsive.

### 5. Implement cancellation and race handling

Make cancellation authoritative in PostgreSQL so requests handled by another
worker can stop the active generation. Commit `cancelled` with the latest durable
partial text; poll that state from the generation coordinator at a bounded interval.
Local notification may improve latency but cannot be the source of truth.

Explicit cancellation can preserve less text than the client already displayed:
uncheckpointed deltas are provisional. The terminal event's saved content is
authoritative. Disconnect cleanup may save its buffered prefix if it wins the
terminal transition. No worker may append text after cancellation commits.

Apply shared cancellation state checks to the JSON path as well: its synchronous
provider call may finish before it observes cancellation, but it must not overwrite
it; return a documented 409 when cancellation wins. Immediate upstream interruption
is guaranteed only for the new cancellable streaming path.

Acceptance: cancel before the first token, mid-output, repeatedly, from another
worker, and against completion. Confirm upstream cleanup and availability of the
conversation for a subsequent turn.

### 6. Complete failure recovery and observability

Use an overall wall-clock deadline in addition to upstream idle timeouts. Renew
active leases only while generation remains within that deadline. Lease renewal
must continue during quiet provider periods without allowing a hung worker to
extend a turn indefinitely. Expired workers cannot renew or finalize.

Retain lazy recovery on the next valid send: mark expired active messages failed
and preserve their latest saved partial content. Document that GET can still show
`in_progress` until recovery runs, and a process crash can lose uncheckpointed text.
If persistence fails, stop upstream generation and leave lease recovery available.

Record content-free outcome, time-to-first-delta, total duration, cancellation
latency, and recovery diagnostics. Never log generated text or upstream payloads.

Acceptance: deterministic tests cover timeout after partial output, upstream EOF,
disconnect, final-commit failure, failed cleanup, expired leases, and late workers.

### 7. Validate transport, regression behavior, and document usage

Use a real local ASGI server and HTTP streaming client for incremental delivery
and disconnect tests; buffered in-process response tests alone are insufficient.
Use disposable PostgreSQL for durability and concurrency tests. Exercise slow
readers, worker-independent cancellation, process-loss recovery, and resource
cleanup with bounded test deadlines and synchronization rather than timing guesses.

Run the full pytest suite with PostgreSQL, Ruff lint/format checks, mypy, and
migration/schema-drift checks if storage changes. Preserve evaluation and Task 7
regression coverage. No paid provider calls are required.

Update README, this task document, configuration examples, and VALIDATION.md.
Include `curl -N`, authenticated POST streaming via `fetch`/ReadableStream,
cancellation, and history reconciliation examples. The client example must parse
frames across arbitrary network chunk boundaries and treat a missing terminal
event as an unknown outcome. Native EventSource is not the proposed client API
for this authenticated POST flow. Document that resending creates a new turn.

## Definition of done

Text is observable before generation completes; saved terminal states match
reported outcomes; cancellation closes streaming work within the configured bound;
failed/cancelled partial output never enters future context; races and crashes
cannot overwrite terminal state or strand a conversation beyond lease recovery;
the existing JSON API and evaluations retain their tested behavior. Record actual
validation results and any environment-dependent limitations before completion.
