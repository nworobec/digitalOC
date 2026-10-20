# Coaches Notes assistant

Open **Coaches Notes** in the dashboard sidebar or **Open game-plan assistant** beneath a selected call. Select a live game session, then choose **Draft game plan**. The first release is a deterministic coaching-rule assistant, without an external LLM or API key.

The assistant saves a title, notes, up to five opening calls, and up to five conditional alternatives. The opening order comes from existing situational-fit rules, constrained by the installed playbook, run/pass filter, personnel, formation, and field space. Opponent historical coverage tags inform conditional alternatives; catalog-related calls supply additional review options. These are templates for review, not optimized sequences or concept outcome predictions.

Choose **Edit plan** to change notes, select calls, edit purposes and observations, add/remove entries, or move entries earlier. Both script and counter sections allow up to 15 entries. Save persists the draft in the session; discard restores the saved content. Navigation and game switching are disabled during edits, and browser unload warns about unsaved edits. Regeneration asks before replacing the previous draft and coach edits. There is one current saved plan per session, not a version history.

Each plan retains the generation-time game state, preferences, catalog version, and opponent evidence (source, seasons, sample size, matching scope, and coverage frequencies). Missing coverage is explicitly shown, and playbook-only drafting still works. Free-text edits are coach-authored notes, not verified evidence. No player availability, film analysis, new model training, or next-snap forecast is inferred.

Situation or preference changes make the previous plan stale. It remains readable, but regeneration is required before editing/saving for the new situation. Opening calls require fresh eligibility checks after each snap. Plans do not enqueue calls, record outcomes, or change game state. Saving or regenerating does clear latest-play undo, following other session mutations.

## API

- `POST /api/sessions/<id>/plan/generate`: `{revision, mutation_id}` generates and saves a replacement draft.
- `PUT /api/sessions/<id>/plan`: `{revision, mutation_id, context_id, content}` validates and saves coach edits.
- `GET /api/sessions/<id>` includes `coaching_plan` when present.

Both mutations use revision conflict protection and retry deduplication. The server owns evidence and generation context; the editor can only change content. Invalid/unavailable call IDs and oversized sections/text are rejected. Historical review batches cannot generate plans. This remains a local service with the existing authentication limitations.
