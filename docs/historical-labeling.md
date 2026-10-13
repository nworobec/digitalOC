# Historical play labeling

Open **Data & review → Build a real-play labeling queue**. The local raw PBP and participation files can now supply real source records for labeling; no game needs to be manually replayed into the dashboard first.

## Starter queue

28 actual KC offensive plays have been staged in seven review-only batches from the 2024 season. Each batch contains two run-intent and two pass-intent plays. These are a small labeling exercise selected across the season, not a representative training dataset. All concepts remain unlabeled, and no records were approved automatically.

| Source game | Date | Staged plays |
| --- | --- | ---: |
| 2024_01_BAL_KC | 2024-09-05 | 4 |
| 2024_04_KC_LAC | 2024-09-29 | 4 |
| 2024_08_KC_LV | 2024-10-27 | 4 |
| 2024_12_KC_CAR | 2024-11-24 | 4 |
| 2024_15_KC_CLE | 2024-12-15 | 4 |
| 2024_18_KC_DEN | 2025-01-05 | 4 |
| 2024_22_KC_PHI | 2025-02-09 | 4 |

Choose a batch in the **Saved game** selector, then review its records under **Data & review**. These batches persist in the existing local SQLite database. The 2024 season includes postseason games in 2025.

## Browse and stage more plays

1. Choose a season and click **Browse source games**.
2. Choose a game and optionally filter by run/pass intent.
3. Select records or the current page, then click **Stage plays for review**.
4. Inspect the description, source game/play IDs, date, raw route, formation, personnel, and coverage labels in the evidence panel.
5. Use film or trustworthy concept-level charting to identify the actual full concept. Record the evidence reference and reviewer, verify pre-snap state and outcome, and save a draft, approval, or exclusion.

Source metadata prefills game ID, play ID, date, source type, and the source's no-penalty flag. Full concept, actual formation/personnel, observed coverage, verification checkboxes, and evidence reference remain for the reviewer to establish. An individual receiver's route, a broad SHOTGUN formation label, or a play description does not uniquely identify Mesh, Flood, or another complete concept. The playbook template descriptions also still need coach review.

## Import guarantees and limits

- Each season requires both raw PBP shards and its participation CSV. Missing/duplicate game-play keys block source loading rather than multiplying records in a join.
- The first browser currently offers penalty-free run/pass plays with valid regulation pre-snap fields, excluding kneels and spikes. Scrambles and sacks retain pass intent. This is an explicitly limited initial labeling pool, not all football plays.
- Source values, file names, raw description/labels, and a SHA-256 of the imported source evidence are retained. The digest covers selected source fields, not the entire file.
- Reimporting the same source records is idempotent. Additional plays merge into the same game batch without overwriting reviews. Changed evidence for an already imported play produces a conflict instead of silently replacing it.
- Batches are review-only: they cannot be converted into a live drive. There are no invented suggestions, displayed candidate lists, model versions, or coach-entered settings. The context is explicitly marked `historical_pre_snap_reconstruction`; preference defaults are placeholders, not observed historical coach inputs, and are not dataset features.
- Post-play state and elapsed seconds remain missing. They are not simulated to fill gaps.
- Approvals must preserve the source game/play/date identity and match its run/pass intent. Disagreements should be excluded or resolved from source evidence.
- Observed EPA is retained as raw evidence only. The current reviewed concept dataset still exports verified yardage, not an automatically approved EPA target.

The dataset pipeline revalidates historical records just like live records and exports their source-row digest, file names, and context origin in provenance (`concept-dataset-2`). Unreviewed historical plays remain excluded from training.

## API

- `GET /api/labeling/games?season=2024`
- `GET /api/labeling/plays?season=2024&game_id=...&action=all&page=0` — pages of 20.
- `POST /api/labeling/import` with `{game_id, play_ids}` — 1–50 unique IDs per request, selected server-side from the source files.

Imports use one database transaction and deterministic game-batch identity. They do not edit source CSVs. Source catalogs cache by file path, size, and modification time.

## What is still required

The staging work is complete; concept verification is not. We still need coach-reviewed film timestamps, a licensed concept-level charting source, or trustworthy existing labels before approving these examples. This phase does not train a concept model or establish better play-calling outcomes.
