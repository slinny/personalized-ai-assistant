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

Personality bands are low [0, 0.25), balanced [0.25, 0.75), and high [0.75, 1].
All four traits use these same boundaries, with 0.5 selecting balanced behavior.
Wording and trait order live in app/behavior/personality.py. Raw numbers are never
emitted. These are initial product mappings; live effectiveness is evaluated in Task 6.

Output order: IDENTITY, COMMUNICATION, LANGUAGE, CUSTOM INSTRUCTIONS. Names and
language identifiers are JSON quoted. Custom instructions are a losslessly encoded
JSON string, preserving whitespace, Unicode, newlines, and the entire accepted value.
Quoting provides structural separation, not a security guarantee against prompt injection.

Precedence: higher-priority platform instructions, configured identity/language,
explicit custom instructions, then communication defaults. The future provider
integration must preserve platform instruction priority. Fixed mode uses the primary
language. Follow-user mode selects language independently each turn; mixed messages
use the dominant request language, with primary language as the ambiguous-input fallback.
These tests verify compiled directions, not a model's actual language compliance.
