# Coaches Notes assistant

Open **Coaches Notes** in the dashboard sidebar or **Open game-plan assistant** beneath a selected call. Select a live game session to ask questions about its saved situation, evaluation, eligible playbook calls, designs, and recorded plays. The conversational assistant runs through a local Ollama service; it does not require a hosted model API key.

Install Ollama separately, start its local service, and pull a model (the default is `llama3.2`, for example `ollama pull llama3.2`). Configure `DIGITALOC_OLLAMA_MODEL` to use another installed model. `DIGITALOC_OLLAMA_URL` defaults to `http://127.0.0.1:11434` and only loopback hosts are accepted. If Ollama is unavailable or the model is missing, the assistant reports an error; it does not silently substitute a different model. The deterministic **Draft with coaching rules** action remains available.

Conversation messages are held only in the browser for the current view and sent to the local Ollama service with current session context. They are not written to the session database. The assistant can explain existing evaluation outputs but does not calculate new statistics or change model inputs. Game plans requested in chat are returned as structured proposals in the editor. Review and edit the proposal, then explicitly save it. A chat message or generated proposal never changes game state, queues a call, or records a play.

The assistant saves a title, notes, up to five opening calls, and up to five conditional alternatives. The opening order comes from existing situational-fit rules, constrained by the installed playbook, run/pass filter, personnel, formation, and field space. Opponent historical coverage tags inform conditional alternatives; catalog-related calls supply additional review options. These are templates for review, not optimized sequences or concept outcome predictions.

Choose **Edit plan** to change notes, select calls, edit purposes and observations, add/remove entries, or move entries earlier. Both script and counter sections allow up to 15 entries. Save persists the draft in the session; discard restores the saved content. Navigation and game switching are disabled during edits, and browser unload warns about unsaved edits. Regeneration asks before replacing the previous draft and coach edits. There is one current saved plan per session, not a version history.

Each plan retains the generation-time game state, preferences, catalog version, and opponent evidence (source, seasons, sample size, matching scope, and coverage frequencies). Missing coverage is explicitly shown, and playbook-only drafting still works. Free-text edits are coach-authored notes, not verified evidence. No player availability, film analysis, new model training, or next-snap forecast is inferred.

Situation or preference changes make the previous plan stale. It remains readable, but regeneration is required before editing/saving for the new situation. Opening calls require fresh eligibility checks after each snap. Plans do not enqueue calls, record outcomes, or change game state. Saving or regenerating does clear latest-play undo, following other session mutations.

## API

- `POST /api/sessions/<id>/plan/generate`: `{revision, mutation_id}` generates and saves a replacement draft.
- `POST /api/sessions/<id>/assistant`: `{revision, message, history}` reads a live session and returns a reply plus an optional validated plan proposal. This endpoint is read-only and requires local Ollama.
- `PUT /api/sessions/<id>/plan`: `{revision, mutation_id, context_id, content, source?}` validates and saves coach-approved content. Creating or replacing a plan requires `source: "local_assistant"`; ordinary edits update the current plan without a source field.
- `GET /api/sessions/<id>` includes `coaching_plan` when present.

Both mutations use revision conflict protection and retry deduplication. The server owns evidence and generation context; the editor can only change content. Invalid/unavailable call IDs and oversized sections/text are rejected. Historical review batches cannot generate plans. This remains a local service with the existing authentication limitations.
