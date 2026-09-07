# Task 6: behavioral evaluation

## Contract and checkpoints

1. Document the evaluation contract.
2. Add validated, versioned JSON case schemas.
3. Build a database-free runner using production context and provider contracts.
4. Add 15–20 focused initial cases.
5. Add objective scoring and JSON/Markdown reports.
6. Compare default and customized profiles with identical model settings.
7. Test the harness offline and document explicit live execution.
8. Run final checks and record evidence and limitations.

Each checkpoint is validated before its commit. Harness correctness is established
with fake providers; only live responses can provide evidence of model behavior.
Live execution is opt-in and uses configured credentials, bounded repetitions and
output tokens, no retries, and no database writes. Greeting scheduling and token
budgeting beyond the existing context policy remain outside this task.

Cases include stable IDs, versions, categories, validated profiles, completed seed
history, user turns, objective checks, and human review criteria. Invalid suites
are rejected before generation. Each repetition and comparison arm starts fresh.
A failed generation stops that case repetition and is recorded separately from
an objective-check failure. Subjective behavior remains pending human review.

Reports preserve model, provider settings, case definitions, compiled instructions,
requests, responses, and outcomes. They contain evaluation text and should be
stored locally with suitable care. They never include credentials. Reproducibility
means traceable inputs and settings, not identical stochastic model outputs.

Acceptance: the initial suite loads, offline execution and reports work, comparison
arms use the same model/settings, errors cannot masquerade as passes, and all
available regression/lint/type checks pass. Live results are optional when provider
configuration is unavailable and must never be inferred from fake responses.
