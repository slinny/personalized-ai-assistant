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
