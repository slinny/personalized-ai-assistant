# Task 7: conversation history and token budgeting

## Context policy

Every request preserves platform instructions, the latest compiled behavior, and
the current user message exactly once. Input allowance is the configured model
context capacity minus the output reserve and safety margin. Mandatory content
that exceeds that allowance is rejected before reserving a turn or calling a
provider; instructions and current input are never silently shortened.

History uses the newest contiguous suffix of eligible, completed adjacent
user/assistant pairs. Failed and interrupted turns are ineligible. At the first
eligible pair that does not fit, stop: do not cherry-pick smaller older turns.
History trimming affects only the provider request; stored messages remain intact.

Budgets are explicit per model name, with no guessed model limits. Counting is a
conservative offline estimate, with request/message overhead and a safety margin;
it is not an exact provider usage count. Output reserve includes reasoning tokens.
Provider-side automatic truncation must remain disabled.

## Implementation checkpoints

1. Define and test context allocation and retention policy.
2. Validate explicit model budget configuration and resolution.
3. Add an injectable local token estimator.
4. Select complete recent turns within the token allowance.
5. Map mandatory-content overflow to a pre-reservation validation error.
6. Read history in bounded batches beyond the old 40-message limit.
7. Carry one resolved output allowance through generation and evaluations.
8. Record content-free context diagnostics.
9. Expand regression tests and review/fix the complete implementation.
10. Validate all checks and finish configuration/operator documentation.

Each checkpoint is tested before its commit. No schema migration was needed.

## Configuration and resolution

`CONTEXT_MODEL_BUDGETS` is a JSON object keyed by exact model names. There is no
automatic alias/prefix matching or built-in model-capacity registry. Explicit
entries avoid silently applying stale limits to a different model. Unconfigured
selected models produce `ProviderUnavailable`, mapped to a sanitized HTTP 503.
The live evaluation CLI reports a usage error before constructing a client.

| Setting | Contract |
| --- | --- |
| `context_window_tokens` | Required positive integer per model; operator-verified capacity or a smaller application limit |
| `max_output_tokens` | Optional integer 1–16000 per model; falls back to `OPENAI_MAX_OUTPUT_TOKENS` (default 2048) |
| `safety_margin_tokens` | Positive integer per model, default 1024 |
| `CONTEXT_HISTORY_SCAN_LIMIT` | Integer 2–100000, default 10000 stored messages, including ineligible messages |

Output plus margin must be less than capacity for every configured entry.
Unknown entry fields, noninteger budget values, and blank/untrimmed model keys
are rejected. No credentials are needed to resolve or count context. Choose an
output allowance supported by the actual provider model as well as the application.

At reservation time the service reads the latest profile, resolves its preferred
model or the configured fallback, and snapshots the budget and history scan limit.
The immutable `GenerationRequest` carries the resolved model and output allowance.
The adapter uses that request's allowance rather than separate client settings.
Profile changes take effect on the next send. Restart after changing environment
configuration. Configuration can make previously acceptable messages too large;
no stored content is modified as a result.

## Estimation and request assembly

`TokenCounter` is an injectable additive interface: nonnegative per-message costs
plus one request-level overhead. `utf8_bytes_v1` uses:

```text
estimated input = 16 + sum(16 + UTF8_bytes(role) + UTF8_bytes(content))
input allowance = context capacity - maximum output - safety margin
```

One token per byte intentionally overestimates ordinary byte-tokenized text,
including CJK, emoji, combining marks, code, and special-token-looking strings.
It needs no tokenizer downloads or remote counting calls. Framing constants and
the safety margin are application estimates, not an OpenAI serialization contract
or proof that every possible provider request fits. This implementation supports
plain-text messages only. Adding tools, images, audio, or another provider requires
reviewing the estimator and overhead. Diagnostics are estimates, not billing data.

This tradeoff keeps context assembly deterministic and local while the owned
conversation row is locked. It can omit useful history sooner than a model-specific
tokenizer. An exact tokenizer or remote preflight would be separate work; a remote
count must not be added inside the reservation transaction.

Mandatory content is counted before history is consumed. Exact equality with the
allowance is accepted. An overflow maps to HTTP 422 with a suggestion to shorten
the input or assistant instructions, and rolls back the reservation transaction.
No current message or assistant placeholder is saved. Even lazy expired-lease
recovery is rolled back if the new request fails before reservation. Existing
provider failure/timeout behavior remains 502/504 with a failed saved turn.

The adapter explicitly sets `truncation="disabled"`; it does not delegate history
selection to the provider. The output allowance covers visible text and reasoning
tokens, as documented in the [official Responses API reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create)
(checked 2026-09-08). No paid calls were needed for implementation or validation.

## History retrieval and diagnostics

The database iterator reads at most 100 rows per page using descending position
keyset pagination, scoped to the owned conversation. The caller holds the conversation
lock during assembly. Scalar columns avoid retaining ORM objects for the entire
history. Pair matching spans page boundaries; only adjacent completed user then
assistant positions qualify. The builder consumes newest-first history and reverses
selected pairs into chronological request order. A partial pair at the scan limit
is excluded. Reading stops after the first eligible pair that does not fit or at
the scan limit/end of history. One fetched page may contain rows beyond what the
builder consumes. There is no full-history count query.

An INFO record from `app.services.conversation` is emitted after successful
reservation, before generation. Configure an INFO-capable logging handler/formatter
to collect its `context_budget` structured extra field and
`history_scan_limit_reached`. Default console formatting may omit structured extras.
The record contains only the estimator name and numeric/boolean diagnostics: no
conversation text, compiled instructions, model name, IDs, or credentials.

`context_budget` records capacity, input allowance, mandatory/selected token
estimates, output/margin reserves, consumed history-message count, included turns,
and whether selection stopped at the budget. `dropped_scanned_turns` is 0 or 1:
it counts the first eligible pair rejected by the budget, not every older omitted
turn. Older unscanned turns are deliberately not counted. Similarly, reaching the
scan limit does not prove that additional rows exist. These names avoid reporting
incomplete counts as whole-conversation totals. Failed/orphaned messages contribute
to `scanned_messages` but not to either turn count.

Evaluation JSON includes the same diagnostics and output allowance for successful
context builds, plus the run's resolved budget. A context overflow leaves the
turn's request empty and records `ContextOverflow`, then stops that case.

## Checkpoint validation and review

| Checkpoint | Validation before commit |
| --- | --- |
| Policy | 5 allocation tests; Ruff, formatting, mypy |
| Model configuration | 31 configuration/provider tests; Ruff, mypy |
| Estimator | 26 estimator/budget tests; Ruff, formatting, mypy |
| Selection | Full PostgreSQL suite, 192 passed; focused context/evaluation tests |
| Overflow | 15 PostgreSQL pipeline tests; mypy |
| Pagination | 18 PostgreSQL pipeline tests and 17 context/evaluation tests; Ruff, mypy |
| Request consistency | 51 focused tests and 19 PostgreSQL pipeline tests; Ruff, mypy |
| Diagnostics | 19 context/evaluation tests and 20 PostgreSQL pipeline tests; Ruff, mypy |
| Review | Full PostgreSQL suite, 220 passed; 14 evaluation tests after two CLI additions; Ruff, formatting, mypy |
| Final validation | 222 tests passed on both local Python 3.13 and Docker Python 3.12 with PostgreSQL; all static/dependency checks and offline CLI smoke passed |

Review checked retention order, pre-reservation failures, ownership, bounded reads,
pair boundaries, model changes, output consistency, evaluation reporting, and
diagnostic privacy. It tightened the scan-limit snapshot and added a deterministic
multilingual brute-force suffix comparison. Integration tests prove that a budget
stop avoids older-page queries, failed runs do not hide eligible older history,
and trimmed history remains persisted and can be included again under a larger
model budget. See [VALIDATION.md](../VALIDATION.md) for final runtime results.
