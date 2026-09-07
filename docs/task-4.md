# Task 4 behavior compiler contract

BehaviorCompiler.compile accepts a validated, immutable BehaviorProfile snapshot
and returns deterministic instruction text. BehaviorProfile.model_validate accepts
an already-loaded ORM profile or API response without requiring storage metadata.
The caller loads records; compilation performs no I/O and reads no clock or environment.
Existing API field constraints are reused, including the 10,000-character custom
instruction maximum. Invalid input raises a validation error, never silent truncation.

Implementation checkpoints: validated contract, personality mappings, structured
compiler, language/custom instructions, greeting boundary, expanded tests, final
validation/documentation. Each checkpoint is validated before its commit.
