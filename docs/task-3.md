# Task 3 API contract

- Configure AUTH_TOKEN (at least 32 ASCII bearer-token characters) and AUTH_USER_ID
  (UUID) together. With neither configured, protected routes return 503; partial
  or invalid configuration fails settings validation. Health remains public.
- Authenticate Authorization: Bearer using constant-time comparison. Missing,
  malformed, or incorrect credentials return 401 with WWW-Authenticate: Bearer.
- Run python -m app.db.provision after migrations to create the configured user
  and a profile named Assistant. Repeated/concurrent runs preserve existing data.
- GET /assistant returns the configured user's profile or 404 when unprovisioned.
- PATCH /assistant accepts only editable profile fields. Omitted fields remain
  unchanged; only preferred_user_name and preferred_model accept null. Empty
  patches succeed without changing updated_at. IDs, ownership, and timestamps
  are read-only. Invalid payloads return 422 and make no changes.
- Strings follow storage limits and nonblank names are trimmed. Personality
  values must be finite numbers in [0, 1]. Booleans are strict. Language is a
  nonblank identifier up to 35 characters; switching is follow_user or fixed.
- Holiday preferences map nonblank holiday identifiers (max 100 characters) to
  greeting strings (max 1000 characters), with at most 100 entries. An update
  replaces the whole object; {} clears it. This accommodates existing storage.
- Responses include profile fields, id, user_id, created_at, and updated_at.
  Writes commit atomically; sessions close and roll back on failure.
- No schema change is expected. Validate each implementation checkpoint with
  focused tests and configured static checks before committing; finish with
  live PostgreSQL integration, migration, and schema-drift validation.
