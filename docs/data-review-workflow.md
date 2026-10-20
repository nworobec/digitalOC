# Data audit, play-log exports, and label review

Open **Data & review** in the dashboard sidebar. The existing local API on port 5001 and frontend on port 3000 serve this workflow. No new dependency or database migration is required; older recorded plays remain unreviewed.

## Workflow

1. Run **Data audit** to inspect the local raw source inventory, missing label fields, duplicate keys, PBP/participation matching, and saved-session review counts. The first scan reads the canonical raw CSVs; subsequent requests cache by file names, sizes, and modification times.
2. Select a saved session and recorded play. Review its original pre-snap state and consult film or another identified source.
3. Label actual execution: concept, personnel, formation, observed coverage, outcome, and penalty status. Planned personnel/formation and the selected concept are not automatically copied into verified labels.
4. Identify the reviewer, source type, evidence reference, source game ID, and date. The reviewer name is self-reported; the local app has no account authentication. Practice/test records must be labeled accordingly.
5. Save as **Draft**, **Approved**, or **Excluded**. Approval requires known execution labels, source details, and explicit verification of both pre-snap state and outcome. Exclusion requires a reason. Changes to the recorded concept/outcome require correction notes.
6. Download **JSON** or **CSV** for the selected session. Exports include every completed play, including unreviewed and excluded records, with readiness flags and blockers. Queue-only entries are not completed-play training rows; JSON also contains the saved session and queue for context.

Reviews append to history with their timestamp, version, and original session revision. They do not overwrite the original decision snapshot, outcome, or game state. Corrected yardage does not silently replay subsequent downs. Saving a review disables the latest-play Undo operation so a reviewed record cannot disappear through Undo. Existing revision checks and mutation IDs reject stale edits and prevent duplicate review submissions.

## Candidate checks, not automatic training

- **Yardage candidate:** latest review approved, real-game source, original pre-snap decision context present, pre-snap state verified, no unresolved/effective penalty, and no outcome correction awaiting state reconciliation.
- **Defensive-label candidate:** the same checks plus known observed coverage.
- **EPA candidate:** always false for these manual records. We have no independently computed/verified EPA label, and never substitute the recommendation model's predicted EPA.

These flags identify annotation candidates, not a certified training dataset. Cross-session duplicate source plays, game-grouped chronological splits, source accuracy, catalog mapping, sample sizes, and leakage checks must be assessed before training. An approved test/practice record remains excluded from real-game candidates. An unknown/out-of-catalog concept can be saved as a draft or excluded record; it cannot be approved as a known catalog concept. Penalties and state corrections are annotated, not automated in the live game tracker.

CSV serializes nested context and review history as JSON cells. Text beginning with spreadsheet formula characters is prefixed with an apostrophe; the JSON download preserves original text exactly. JSON is the richer archival format and includes the entire session.

## API

- `GET /api/data/audit` — historical source audit and current review totals across saved sessions.
- `GET /api/sessions/<id>/review` — original plays, latest review, and readiness blockers.
- `POST /api/sessions/<id>/plays/<play_id>/review` — `{revision, mutation_id, review}`; complete review object required.
- `GET /api/sessions/<id>/export?format=json|csv` — versioned attachment; default JSON.

Review fields (plus optional `source_play_id`, required for dataset inclusion): `status`, `reviewer`, `source_type`, `source_reference`, `game_id`, `game_date`, `actual_call_id`, `actual_personnel`, `actual_formation`, `observed_coverage`, `actual_kind`, `actual_yards`, `penalty_status`, `before_state_verified`, `outcome_verified`, `notes`. Supported choices are exposed in the UI; concepts, personnel, formations, and coverages use the existing catalog metadata. Approval checks are enforced by the API, not just the form.

Run the audit independently, from the repository root:

```sh
python3 -m backend.decision_support.audit --output backend/instance/data-audit.json
```

This is read-only with respect to source CSVs and recorded sessions. It does not train or promote models. The audit inventories cleaned/merged/aggregate files but counts only raw `pbp_<year>_<shard>.csv` and `pbp_participation_<year>.csv`, avoiding duplicate counting of derived datasets. Expected files cover 2020–2024. Raw scrimmage counts use `play_type` run/pass, not the narrower baseline training eligibility rules. Populated means present (and finite for outcome targets), not accurate or mapped to the catalog.

## Local source findings — September 29, 2026

| Check | Result |
| --- | ---: |
| Canonical raw files | 15 |
| PBP rows / unique game-play keys | 246,218 |
| Participation rows / unique game-play keys | 241,464 |
| Duplicate extra key rows in either source group | 0 |
| Matched unique PBP/participation keys | 239,147 |
| PBP keys without participation | 7,071 |
| Participation keys without PBP | 2,317 |
| Raw run/pass rows with finite EPA and yardage | 176,084 |
| Populated recognized full-concept label cells | 0 |

Participation label completeness (raw records include non-scrimmage plays):

| Season | Rows | Route | Formation | Personnel | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2020 | 48,513 | 18,214 | 35,444 | 36,924 | 18,927 |
| 2021 | 50,714 | 18,937 | 37,021 | 38,664 | 19,610 |
| 2022 | 50,150 | 18,176 | 36,792 | 38,228 | 18,975 |
| 2023 | 46,168 | 19,616 | 36,959 | 46,168 | 22,916 |
| 2024 | 45,919 | 19,110 | 36,682 | 45,919 | 22,408 |

The audit recognizes `concept_id`, `play_concept`, `concept`, and `offensive_concept` as candidate full-concept columns. None are populated in the canonical files. This does not establish that concepts cannot be labeled from other evidence. A receiver route such as SCREEN is not a reliable mapping to an entire installed play, and broad formation strings do not establish Gun trips versus Gun doubles.

**Next dependency:** coach-reviewed concept labeling and mappings with traceable source evidence, followed by a dataset validation pipeline. Actual route/coverage labels belong on the observed side of the record, not among pre-snap features. No concept model or defensive forecast has been trained in this phase.

## Training dataset preparation

The [concept dataset pipeline](concept-dataset.md) now performs cross-session duplicate checks, correction quarantine, input/target separation, and chronological splitting. Open **Prepare the concept training dataset** in Data & review. Per-record review candidates may still be rejected by these dataset-wide checks.

## Label historical source plays

Use the [historical play browser and starter queue](historical-labeling.md) to stage genuine source records for review without replaying them through live tracking. Full concepts and approvals are never inferred from receiver-route labels.

## Planned vs. Executed

Select a completed play in **Data & review → Review recorded plays**. The new panel shows its immutable recording-time design version (when captured), alongside independently entered execution labels. Select Ran as planned, Audible, Modified, No recorded design, or Unknown. Actual concept/personnel/formation remain in the main review fields. Enter strength, motion, and role/route/blocking instructions for each of the 11 marker slots. The slot labels are locator aids, not verified player identities.

Verification is explicit: unknown motion is blank, while verified absence should say “No motion.” Verified assignments require all fields; use N/A for inapplicable assignments. Evidence reference and reviewer are required for verification. Audibles/modifications require review notes. As-planned claims must match the captured design and actual concept/personnel/formation; selecting that option never copies or approves labels. Legacy records without designs can still receive evidence-backed execution labels.

Execution annotations use the existing append-only review history and optimistic session revision checks. JSON includes the full annotations and original design snapshots; CSV adds `execution_json`. Review schema version 2 accepts legacy reviews without execution labels. The original play, planned design, and game state remain unchanged.

Dataset schema `concept-dataset-3` adds `design_review` alongside (not inside) model features. Only records passing all existing concept dataset checks contribute to execution-label support. The report groups verified rows by concept/formation and chronological split, counts distinct games, and lists missing execution labels among otherwise eligible rows. At least two groups must meet the existing per-split planning minimums; this is a planning gate, not model validation. These labels are not automatically used as pre-snap features, and no model is trained or EPA estimate changed.
