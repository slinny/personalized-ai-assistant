# Lightweight personalization plan

## Goal

Make one user's assistant feel familiar through its appearance, communication,
and a small amount of explicit memory. The first release should let you describe
the interface you want, tune how the assistant speaks, and carry a few chosen
preferences into a new conversation.

This follows our Muse discussion's emphasis on a personal daily experience.
Letta's emphasis on persistent memory is useful inspiration
([Letta](https://www.letta.com/)); adopting its runtime is not necessary for this
small version. The earlier Muse discussion was retrieved; the earlier Letta
discussion was not available in the retrieved context.

## Starting point

The project already has FastAPI, PostgreSQL, assistant settings, a behavior
compiler, saved conversations, bounded context, streaming, cancellation, and a
browser test client. Extend these foundations. Keep the single-user model,
existing provider, and modular monolith.

## First release: three small deliverables

### 1. A personal chat interface

- Evolve the existing browser client into a responsive everyday chat screen.
  Keep chat central, with one settings drawer for Appearance, Communication,
  and Memory.
- Start with three curated themes: clean, warm, and dark. Support readable font
  sizes and compact or comfortable spacing.
- Map three communication presets onto existing settings: concise and direct,
  warm and supportive, and detailed and explanatory. Keep fine-tuning optional.
- Show a sample response for each preset, clearly marked as an example. Offer
  an explicit live preview when testing the actual model's behavior.
- Preserve streaming and Stop, and make loading, failure, and interrupted-turn
  states understandable. Add “Shorter” and “More detail” as follow-up actions;
  these affect the current exchange unless the user saves a lasting preference.

Done when: a user can customize appearance and tone, reload, and continue a
conversation comfortably on desktop and mobile.

### 2. Describe your theme

Example: “A cozy reading room, cream background, forest-green accents, larger text.”

- Add a theme prompt and one preview. Allow refinement, Apply, and Reset.
- Have the model return a validated theme object: approved colors, font family,
  font size, spacing, and corner radius. Render through CSS variables and fixed
  components. Exclude generated HTML, JavaScript, arbitrary CSS, and remote assets.
- Validate supported values and text/control contrast before previewing. Keep
  the last valid theme if generation fails. Preserve keyboard focus visibility
  and reduced-motion preferences.
- Save one active custom theme per user. Theme libraries, generated artwork,
  and layout generation can wait.
- Keep appearance independent from assistant personality. Generate only when
  requested; applying a saved theme needs no model call.

Implementation: one versioned theme JSON field and one authenticated generation
endpoint, using the existing provider and bounded output.

Done when: a prompt produces a readable preview, Apply survives reload, Reset
works, and invalid output cannot break the interface.

### 3. Small, visible memory

- Provide “Remember this” on selected user messages and a simple add/edit/delete
  list. Let the user review the exact text being saved.
- Start with at most 20 short notes, such as an ongoing project or preferred
  explanation style. Keep tone/language settings in the existing profile to
  avoid two competing sources of truth.
- Store user ownership, text, optional source-message ID, and timestamps in one
  table. No automatic extraction, embeddings, vector database, or background
  reflection in this release.
- Include saved notes across conversations within a small explicit context
  budget. Treat notes as user context, subordinate to platform rules and the
  current request. Show when a note is omitted because of the budget.
- Edits and deletion affect the next request. Explain that forgetting a note
  does not erase its original chat message; avoid claiming complete erasure.

Done when: a saved preference works in a new conversation, a correction replaces
  it, and deletion removes it from the memory supplied on subsequent requests.

## Follow-up milestone: a simple daily routine

Only start after using the first release for a week.

1. Add a manually managed in-app agenda and one-time reminders with an explicit
   date/time and timezone, plus edit, dismiss, and snooze. Show overdue items on
   reopening. Initially these are in-app notices while open; closed-app delivery
   requires a separate notification milestone.
2. Add an on-demand Today card combining the agenda with weather for a manually
   chosen location. Use one read-only weather source, show freshness, and handle
   missing data explicitly. Schedule briefings only after delivery is reliable.

Defer traffic and local news until source coverage, freshness, and relevance can
be validated. Also defer external calendar sync, account connectors, autonomous
actions, voice, multi-agent systems, and a general scheduler.

## Validation and scope limit

Ship the interface, theme generation, and explicit memory in that order. No new
infrastructure service is required. Extend existing checks for theme validation,
ownership, memory correction/deletion, context limits, and streaming regressions;
manually check mobile layout and keyboard navigation.

Use five paired prompts with the same model to compare default and personalized
responses. Check preference adherence without reducing correctness. Over one
week, track whether you keep the chosen theme, repeat preferences less often,
and prefer the personalized responses. Model quality remains unproven until
these live comparisons are reviewed.

The release is complete when the assistant looks the way you chose, communicates
the way you prefer, and remembers only the notes you deliberately saved.

## Implementation status

The three first-release deliverables are implemented and committed: personal UI,
validated AI theme previews with persistence, and explicit editable memory.
Backend, migration, and browser validation are recorded in `VALIDATION.md`.
The one-week personal trial and the daily-routine follow-up remain future work;
this implementation does not introduce reminders, weather, or scheduled delivery.
