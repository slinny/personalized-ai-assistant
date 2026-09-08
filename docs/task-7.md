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

Each checkpoint is tested before its commit. No schema migration is planned.
