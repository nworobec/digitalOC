# Connected DigitalOC dashboard

The default `/` and `/dashboard` routes use persisted game sessions and the local outcome-comparison API. `/preview` keeps the labeled visual mockup. `/welcome`, `/situation`, and `/result` retain the legacy flow using port 5000.

## Start locally

With the existing Python and frontend dependencies installed, run from the repository root:

```sh
# Only needed when the local trained artifact is missing:
python3 -m backend.decision_support.train
python3 -u -m backend.decision_support.api
```

In a second terminal:

```sh
cd frontend
npm start
```

Open http://localhost:3000. The dashboard API listens on http://127.0.0.1:5001. `REACT_APP_DASHBOARD_API_URL` overrides its frontend address at build/start time. `DIGITALOC_ALLOWED_ORIGINS` sets comma-separated CORS origins; localhost and 127.0.0.1 on port 3000 are allowed by default.

Sessions persist in `backend/instance/digitaloc.sqlite`; set `DIGITALOC_DB_PATH` to change this location. The model lives in `backend/models/decision_support/baseline.joblib`. Both are local, gitignored artifacts. Tracking remains available without the model, with comparisons shown as unavailable. This is a local development service without user accounts or session access controls.

## Connected features

- Create, select, and resume game sessions; edit game state without inventing completed plays.
- Compare run/pass expected EPA and yards separately from historical call likelihood.
- Browse 12 starter concepts with distinct schematic diagrams, queue calls, and record actual outcomes.
- Get a three-call situational-fit shortlist from saved game state, personnel, formation, anticipated coverage, coaching objective, and available playbook. Explanations distinguish eligibility filters from provisional coaching preferences.
- Advance field position, down/distance, score, and clock from recorded outcomes. Undo the last recording until another mutation occurs.
- Begin the next possession explicitly after touchdowns, turnovers, safeties, and halftime. PATs, kicks, returns, penalties, and overtime need manual handling.
- Show historical opponent coverage frequencies with sample counts and fallback scope, based on labeled dropbacks from the local 2020–2024 data.
- Re-evaluate hypothetical first-down and zero-gain branches while holding the clock constant.

Concepts have no individual outcome scores. Coverage frequencies are descriptive, not calibrated next-snap forecasts. Coverage observations and recorded history are stored but are not inputs to the current outcome model. Conversion probability, turnover risk, uncertainty intervals, and optimized multi-play sequences remain unavailable. Estimated EPA rankings do not establish causal improvement over coaches' decisions.

## Playbook fit and decision logging

`backend/decision_support/playbook.py` defines the `starter-2` catalog and its editable suitability tags. `suitability.py` applies `situational-fit-1` rules. These are provisional templates requiring review by the team's coach, not learned rankings. Diagrams show each concept on a shared illustrative alignment, not a complete installed personnel/formation assignment.

Hard filters exclude calls outside the available playbook, run/pass constraint, personnel, formation, or minimum field space. Remaining calls receive internal rule weights: distance-band match +4, anticipated-coverage tag +3, objective tag +3, short-yardage conversion tag on a later down +2, distance-compatible pass on a long later down +2, compact-field tag +2, and a modest balanced-objective preference for runs when leading or passes when trailing in the last two minutes of Q4 (+2). Ties use stable call IDs. These weights have no probability or outcome interpretation. Coverage mismatches are not hard exclusions.

Choose preferences under **Coach's controls → Playbook fit preferences**, then **Save situation & evaluate**. The action models still rank broad run/pass outcomes by EPA; the coaching objective affects only the concept shortlist. Selecting “Use clock” does not create a clock or win-probability model. Related-concept links are coaching references, not optimized follow-up predictions.

Selected and queued calls are preserved when new constraints change the shortlist. Ineligible calls cannot be newly queued. Actual results can still be recorded for an excluded call, with the exclusion reasons retained so the log reflects what happened. Empty playbooks produce an explicit empty state, not a fallback recommendation.

Creation and state-edit endpoints accept an optional complete `preferences` object:

```json
{
  "personnel": "11",
  "formation": "gun_trips",
  "anticipated_coverage": "MAN",
  "objective": "conversion",
  "installed_call_ids": ["mesh", "stick", "verticals"]
}
```

`/api/meta` supplies supported values and defaults. Old sessions receive compatible defaults without rewriting history. `/evaluation` returns `situational_fit` even when the outcome model is unavailable. It includes suggestions, eligible IDs, exclusions, and catalog/rule versions.

Queued calls and recorded plays retain the pre-snap situation, preferences, shortlist, and model/catalog/rule versions in `decision_context`. Recordings also preserve the original queued context when applicable. The UI supplies a `presentation` with evaluation revision and candidate IDs; the backend validates it and labels visibility as `client_reported`. API clients omitting it receive `displayed_candidate_ids: null`, rather than an invented assertion that the OC saw the suggestions.

Anticipated coverage is distinct from `outcome.observed_coverage`, and resets to Unknown after a recording. Undo restores it with the prior game state and queue. These records lay groundwork for future training; they do not establish actual formation/personnel execution, concept outcome quality, or counterfactual value. Older records lack these snapshots and should not be silently treated as complete training examples.

### Quick comparison checks

With default preferences, all concepts available, and KC vs BUF at their own 25:

| Saved input | Expected rule shortlist |
| --- | --- |
| 3rd & 1 | Power, Slant-flat, Sprint-out flat |
| 3rd & 15 | Flood concept, RB screen, Four verticals |
| 3rd & 5, 11 personnel, Gun trips, anticipated MAN | Mesh sit, Flood concept, Stick |
| No available concepts | Empty shortlist with explanations |

Changing only coaching preferences must not change the run/pass model estimates. Changing actual game-state features can change those estimates. Repeating identical inputs should preserve the shortlist and explanations.

## API and consistency

Read metadata and the playbook at `/api/meta` and `/api/playbook`. `/api/sessions` lists or creates sessions. Each `/api/sessions/<id>` supports reading and editing state, with `/evaluation`, `/queue`, `/plays`, `/undo`, and `/drive` for dashboard actions.

Mutations require the current `revision` and a unique `mutation_id`. Stale revisions return HTTP 409; identical retries with the same ID do not apply a mutation twice. Reusing an ID for a different request is rejected. Queued calls remain separate from completed plays.

## Data audit and label review

The **Data & review** screen audits local sources, exports session play logs as JSON/CSV, and saves versioned human reviews. See the [workflow, API, and measured source gaps](data-review-workflow.md). It also provides [concept dataset validation and reproducible snapshots](concept-dataset.md), including cross-session duplicate checks and chronological splits. It does not automatically train models or alter recorded game state.

## Verify changes

```sh
python3 -m unittest discover -s backend/tests
cd frontend
CI=true npm test -- --watchAll=false --runInBand
npm run build
```

In Chrome DevTools, inspect Fetch/XHR requests for `/api/sessions`: queueing must leave completed plays unchanged, recording should advance revision once, and reload should recover saved state. Failed requests expose `X-Request-ID`, also included in the UI error where available. Match that ID to the backend's JSON terminal log to inspect status, latency, model identity, and evaluation session/revision. Shell history only shows commands; preserve actual server output when investigating requests:

```sh
python3 -u -m backend.decision_support.api 2>&1 | tee /private/tmp/digitaloc-dashboard-backend.log
```

Browser smoke coverage includes session creation, queueing, recording, undo, reload persistence, manual state edits, changing distance/personnel/formation/coverage, preserving selected and queued calls, snapshot contents, empty playbooks, and desktop/mobile overflow and runtime-error checks.

## Interactive call alignments

Select a playbook call in the command center, then choose **Adjust player spots**. Drag offensive markers with a mouse or touch, use the player selector and move buttons, or Tab to a player and use arrow keys (Shift moves farther). Save the alignment, cancel to discard drafts, or reset to the template and save.

Each call's alignment is saved for the current game session and appears in its diagrams and playbook cards after reload. Other game sessions keep their own alignments. While editing, save or cancel before changing calls or recording results. Players stay inside the offensive portion of the schematic; overlapping markers cannot be saved. These bounds are visual constraints, not a legal-formation check. The 11 marker identities stay fixed; visual-only edits do not change personnel, assignments, route landmarks, or concept identity. Football design mode adds coach-confirmed metadata, as described below.

Routes follow the moved player's starting point while retaining their original downstream landmarks. Visual-only edits do not reclassify the formation, rerank situational-fit suggestions, or change outcome-model inputs. Football design edits apply explicitly confirmed formation/personnel and refresh coaching rules; outcome-model inputs remain unchanged. Existing models have not been trained on marker coordinates.

`PUT /api/sessions/<id>/layouts/<call_id>` accepts `{revision, mutation_id, positions}` where positions contains the 11 `[x, y]` pairs in the template's stable marker order, or `null` to reset. Coordinates use the 620×310 SVG space. The same revision and retry protections apply as other session edits. Layout changes disable latest-play Undo, consistent with other intervening mutations.

Queued and recorded calls retain `decision_context.diagram_layout` snapshots; subsequent edits do not rewrite those snapshots. When recording a queued call after an alignment edit, the log keeps both the current decision layout and the original `queued_decision_context` layout. Those are planning context, not proof of the actual on-field alignment. JSON exports retain both.

## Versioned football designs

In **Adjust player spots**, select **Football design change** to confirm formation, personnel, strength, and motion. Select each marker to enter its role, route/progression, and blocking instructions. Save applies formation/personnel to the session's Coach’s Controls and refreshes the rule shortlist. Unsupported personnel/formation for the catalog concept is rejected atomically. Unknown/Any is explicit; coordinates never infer formation or legality.

The optional `design` object on the layout PUT endpoint contains `personnel`, `formation`, `strength`, `motion`, and 11 `assignments` (`role`, `route`, `blocking`). The backend saves `designs[call_id]` with an incrementing version, coach-declared provenance, and the football alignment at confirmation. Repeated unchanged saves do not advance the design version. Visual-only saves update the displayed sketch separately; they preserve the confirmed football design and do not invalidate game plans. Reset to template in visual mode resets only the sketch.

Football design changes invalidate the context of an existing Coaches Notes plan. The previous plan remains readable until explicitly regenerated. Notes include a reminder to review custom assignments against the template; this version does not interpret route or blocking prose into new counters or redraw route paths. Saved design details are reopened in the editor. These are planning records, not verified execution labels or training examples.

Queued calls and recorded outcomes snapshot `play_design` separately from `diagram_layout`, preserving both queued and recording-time versions. Evaluations return the current `design_versions`, an `outcome_input_snapshot`, and `design_outcomes: false`. Session revisions prevent older responses from being displayed as current. The existing run/pass model does not use design fields; the UI labels this limitation beside EPA.

Future work: validated structured route geometry and assignment analysis, execution review fields in the training dataset, and a trained design-aware outcome model. No design-specific EPA is produced by this phase.
