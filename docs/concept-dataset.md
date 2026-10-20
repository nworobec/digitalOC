# Reviewed concept dataset pipeline

The **Data & review** screen now includes **Prepare the concept training dataset**. It validates reviewed plays across all saved sessions, proposes chronological splits, and downloads a reproducible JSON snapshot. It does not train or replace a model.

## Before validating

For each real recorded play, review actual execution and verify the original pre-snap state and outcome. Supply a consistent **Source game ID**, **Source play ID**, game date, evidence reference, and reviewer. Use the provider's stable play identifier (or a documented, consistent film play numbering convention). Game/play IDs are trimmed and uppercased for duplicate checks; arbitrary aliases cannot be reconciled automatically.

Old reviews without a source play ID remain readable and exportable, but the dataset builder excludes them until a new review supplies the missing identifier. Saving a review remains append-only. An approval is a human annotation, not a training certification.

## Validation and exclusion rules

The builder:

- Revalidates latest reviews rather than trusting stored readiness flags.
- Requires approved real-game records with verified pre-snap state, known catalog concept/personnel/formation, verified outcome, source details, and no effective or unresolved penalty.
- Requires the original decision-time snapshot to match the recorded pre-snap state. It validates game-state ranges and team identities.
- Quarantines every non-excluded copy of a duplicate source game/play pair, even across sessions. Review the copies and explicitly mark duplicate copies **Excluded** to select the authoritative record; no copy is silently preferred.
- Excludes conflicting dates or team pairs for a source game. Correct the source labels or explicitly exclude the bad records. Swapping offense and defense within the same matchup is allowed.
- Excludes corrected outcomes and all later records in that session while the recorded game-state history remains unreconciled. Accepted/offsetting penalty annotations trigger the same conservative check. Annotation alone does not replay downstream game state.
- Reports the session/play ID and all exclusion reasons for each rejected record.

## Feature boundary

Each included row contains separate sections:

- `features`: down, distance, field position, quarter, remaining game clock, score differential, timeouts, offense, and defense. These come only from the original pre-snap state.
- `action`: the reviewed concept ID and run/pass type. This is the action to condition an outcome estimate on, not a target to imitate historical calls.
- `targets`: reviewed actual `yards_gained` only.
- `provenance`: source game/play IDs, date, session/local play IDs, reviewer/review number, evidence reference, catalog and model/rule identities where recorded.

Observed coverage, actual personnel/formation, end-of-play state, prior predicted outcomes, and drawing coordinates are not input features. There is no verified manual EPA target; expected EPA is never substituted for one. This first dataset contract supports concept-yardage experiments only, not calibrated defensive-response, conversion, or multi-play models.

## Chronological splitting and planning gates

Default splitting sorts distinct game dates: approximately 60% training, 20% validation, and 20% test. All plays from a game and all games on the same date stay together. Fewer than three distinct dates leaves rows **unassigned**, with training blocked. Game date conflicts are quarantined before splitting.

Optional explicit cutoffs freeze the boundaries: games on or before the training cutoff go to train, later games through the validation cutoff go to validation, and games after that go to test. Supply both dates in YYYY-MM-DD format; training must end before validation. Empty splits are blocking errors.

Initial planning gates require at least two concepts, each with:

| Split | Plays per concept | Distinct games per concept |
| --- | ---: | ---: |
| Train | 100 | 3 |
| Validation | 20 | 2 |
| Test | 20 | 2 |

These constants live in `dataset.py`. They are planning minimums, not demonstrated statistical power or deployment acceptance criteria. Passing them means **eligible for experimental training**, not that a model is accurate. Concepts with sparse support stay visible in the support table; a future trainer must explicitly restrict its supported action set.

## Snapshots and API

- `GET /api/data/dataset` returns the validation report without row payloads.
- `GET /api/data/dataset?download=1` includes rows and sends a JSON attachment.
- Both accept `train_through` and `validation_through` query parameters.

The JSON contains the dataset/version ID, full SHA-256 digest, source snapshot SHA-256, configuration, included rows, excluded record IDs/reasons, and support counts. Identical session data and configuration produce the same dataset ID. Later reviews or changed cutoffs produce a new ID. Archive session JSON exports alongside the dataset for full original context and annotation history; the dataset keeps only the input/target contract and provenance needed for validation.

From the repository root:

```sh
python3 -m backend.decision_support.dataset \
  --db backend/instance/digitaloc.sqlite \
  --output backend/instance/datasets
```

To freeze dates, add `--train-through YYYY-MM-DD --validation-through YYYY-MM-DD`. The CLI opens SQLite read-only and writes a new ID-named snapshot without overwriting an existing artifact. It writes blocked reports too, so insufficient data is documented rather than replaced with synthetic examples. Files under `backend/instance/` remain gitignored.

## Current result and next dependency

The first local run on September 29, 2026 found **zero completed reviewed training records** after temporary smoke-test sessions were removed. It produced a blocked snapshot with no training rows. The historical source audit also found no populated recognized full-concept columns, so raw route labels have not been promoted into concept labels.

Next: collect and independently spot-check real concept-labeled examples using stable source IDs. Once the planning gates are met, build an experimental yardage model, compare it against simple per-action baselines on held-out games, assess coverage/support and uncertainty, and then decide whether it deserves a dashboard integration. Better yardage prediction alone does not prove that a call changes outcomes causally or is the best strategic choice.

## Historical source staging

The [historical labeling browser](historical-labeling.md) now stages raw source plays directly into review-only batches. The initial queue contains 28 real plays across seven games, all unreviewed. Dataset schema `concept-dataset-2` retains historical context origin and source-evidence provenance. Staging alone does not create eligible training rows.
