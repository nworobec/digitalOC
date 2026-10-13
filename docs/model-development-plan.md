# DigitalOC: play recommendation and opponent response plan

## Objective and working scope

Help an offensive coordinator compare executable plays, anticipate defensive responses, and choose the next call after the result becomes known.

Working assumption pending product clarification: begin with NFL historical analysis and defensive responses during the user's offensive possession. Supporting a team's own playbook requires importing its calls and charted outcomes. Predicting the opponent's offensive calls after a possession change is a separate tendency model that can reuse the situation/history infrastructure.

The product should answer:

1. What are my best supported options for this situation and available personnel?
2. What might the defense do against each visible formation or motion?
3. How does each option perform across those possibilities?
4. What is the next call if the current play succeeds, stalls, or changes possession?

“Best” means highest estimated value among supported, available candidates under the OC's objective. Historical data alone cannot establish the true best unchosen play.

## Findings in the current repository

Review performed September 15, 2026. These are findings from local source and CSV inspection, not measured performance of the deployed release artifacts. No training or production changes were performed.

| Finding | Evidence | Required update |
| --- | --- | --- |
| Historical call prediction drives recommendations | `backend/app.py` chooses run/pass first; run/pass trainers classify observed play attributes | Keep tendency prediction as a baseline; compare both run and pass candidates by outcome value |
| Candidate ordering is not outcome ranking | Candidate helpers combine equally ranked individual attribute predictions; expected values are calculated afterward | Generate valid complete candidates, score each, then sort |
| Categorical inputs disappear at serving time | Trainers and inference independently call `get_dummies(..., drop_first=True)`; a one-row inference batch has only one category per field | Save a fitted encoder and model together in one pipeline |
| Additional training/serving mismatches | Run candidate inference omits the saved scaler and sets quarter to 1; situation inference does not encode coverage or calculate its trained Elo feature | Use shared feature construction and a versioned schema |
| EPA and yards are mixed | Both expected-yards trainers target `epa`; pass evaluation compares the combined estimate against yards gained | Separate numeric `expected_epa` and `expected_yards`; retrain with explicit target definitions |
| Passing downside is omitted | Pass outcome training excludes sacks/interceptions and multiplies completion probability by completion-only EPA | Model all dropback outcomes; incompletions also have nonzero EPA |
| Limited seasons actually enter training | Situation/run trainers load 2024; pass trainer returns the first existing file, which is 2020 in this checkout | Explicit multi-season dataset manifests and chronological evaluation |
| Leakage and unrealistic inputs can inflate results | Run formation is both input and target; personnel-derived inputs describe the personnel target; actual air yards train the pass outcome model while API supplies 10 | Separate decision-time information, candidate attributes, and post-play labels; remove target-derived inputs |
| Probability labels are misleading | API scalar conversion takes the first run/pass class probability regardless of selected class; candidate confidence uses one attribute probability | Use class-aware probabilities and distinguish tendency, outcome probability, and evidence strength |
| History is too limited for drive planning | API consumes two-play flags; result page derives yards from the original route-state yardline and stores run/pass plus yards | Persist explicit play events and advance from the immediately previous state |

The current Flask/React application, diagrams, situation inputs, coverage selector, and top-three result interface are useful foundations.

## Data feasibility

Local participation file audit (nonempty coverage labels; denominator includes every row, not just eligible pass plays):

| Season | Rows | Coverage labels |
| --- | ---: | ---: |
| 2020 | 48,513 | 18,927 |
| 2021 | 50,714 | 19,610 |
| 2022 | 50,150 | 18,975 |
| 2023 | 46,168 | 22,916 |
| 2024 | 45,919 | 22,408 |

These counts establish availability, not label quality. Audit duplicate game/play keys, join retention, definitions, and missingness by play type, team, and season before training. Never label missing coverage as a real defensive scheme or missing rush counts as zero rushers.

The official dictionary identifies coverage, actual rushers, box counts at the snap, and the primary receiver's route. It does not provide a complete offensive play concept or a record of the OC's intended call. Actual route, target, and air yards can differ from the planned call; using them as candidate descriptors is initially a coarse retrospective approximation. Named concepts, protections, progressions, and motion-response claims require charted playbook labels. [Participation dictionary](https://nflreadr.nflverse.com/articles/dictionary_participation.html)

Participation sources change in 2023, and the documented FTN participation feed is published after the postseason rather than during the season. Start with manual live observations and historical priors; evaluate a separate feed only if automatic live ingestion becomes a requirement. Inspect newer seasons before adding them to the training manifest. [Data availability](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)

## Target design

### 1. Shared game state and coach controls

Required: game/drive/play identifiers, possession, teams, quarter, clock, down, distance, field position, scores, timeouts, and ordered completed-play history.

OC controls: available personnel, allowed formations/calls, optional run/pass override, preferred objective, and excluded calls. Begin with expected points added (EPA: how much a play changes the offense's expected points) as the default ranking objective. Expose conversion probability, turnover risk, and yards separately. Add explicit protect-lead and must-convert policies when validated; avoid an arbitrary mixture of incompatible units.

Optional observations: box count, safety shell, defensive personnel, pressure look, motion reaction, and a coach's coverage hypothesis. Record source, time, and certainty. Unknown remains unknown. A pre-snap shell is evidence about coverage, not confirmed coverage.

Store three distinct categories: known pre-snap state, proposed offensive action, and post-play observations/outcome. For a what-if coverage override, clearly indicate that the ranking is conditional on that assumption.

### 2. Legal candidate catalog

Start with a small curated catalog of combinations supported by the existing labels, with stable IDs and formation/personnel constraints. Present these as generic play descriptions. Do not assemble independent attribute predictions into potentially incompatible calls.

Then add team playbook imports: call name, concept family, personnel, formation, motion, protection, route assignments, reads, tags, and linked diagram. Enforce roster availability, substitution limits, and the OC's exclusions before scoring. NFL-derived estimates need separate validation before application to college or high-school football.

### 3. Defensive response model

Estimate probabilities for coverage family, rush count, and box/front categories where labels support them. Begin with league and opponent situational frequency baselines, then logistic/tree models with calibration. Only add granular classes after enough samples exist. A rush-count label is a pressure proxy, not a complete blitz design.

Condition on situation, opponent tendencies computed before the game, recent observed history, and the offense's visible presentation. The defense cannot see a hidden playbook call ID. Do not assume a hypothetical motion has a learned effect without motion-response data.

Use historical actual coverage as a target. At serving time, use probabilities or coach observations. If the outcome model trains against actual coverage, evaluate the full deployed chain using predicted coverage, not perfect hindsight. For any stacking, build upstream predictions out of fold.

Initial models may have separate outputs. Before simulation, model or constrain joint responses so coverage and pressure combinations are coherent; do not multiply correlated marginals as though independent.

### 4. Outcome model and ranking

For each candidate, estimate expected EPA, conversion probability, yardage distribution, sack probability, and turnover probability across plausible defensive responses. Include designed runs, completions, incompletions, sacks, scrambles, turnovers, and relevant penalty outcomes with consistent play-intent definitions.

Start with simple regression/classification baselines, then evaluate gradient-boosted trees against them. A single direct EPA model across all eligible plays provides a useful first outcome baseline; outcome-specific models can follow. Evaluate support for each action/state combination and back off to broader families where samples are sparse.

Rank by the probability-weighted outcome over defensive responses, subject to coach constraints. Present evidence strength and uncertainty alongside scores. A tiny score difference should appear as a close choice when uncertainty overlaps.

Observed call choice is confounded by player ability, coaching, and unrecorded reads. Matching historical outcomes or replaying a game cannot prove that an alternative call would have worked. Later evaluate supported policies with propensity/overlap diagnostics and doubly robust estimates, with assumptions documented, followed by coach review and a prospective pilot.

### 5. Two-play branching planner

After one-play evaluation passes its gate, add a bounded two-play simulator:

1. Score legal current calls.
2. Sample coherent defensive responses and outcomes.
3. Advance down, distance, clock, field position, score, possession, and history.
4. Re-estimate defensive probabilities for the resulting state.
5. Choose the next supported call per branch; show the main branches to the OC.

Handle touchdowns, first downs, turnovers, penalties, timeouts, and period endings explicitly. Replan after the real result is entered. Future calls are conditional branches, not a promised script. Do not claim a “setup play” caused a defensive adjustment without supporting sequence evidence.

Use a consistent value function: sum incremental EPA across the planning horizon or use terminal state value with appropriate rewards. Do not double-count expected future points already contained in EPA. Add late-game win-probability objectives only after validation. A sequence neural network or offline reinforcement-learning policy is an optional later experiment, gated by improvement over these simpler baselines.

## OC experience

1. Enter the situation, available personnel, and objective.
2. Add any observed defensive look or leave it unknown.
3. See three legal calls with expected EPA, conversion probability, downside risk, likely defensive responses, and evidence strength.
4. Expand a call to see a conditional audible and next-play branches.
5. Record the actual selected call, defensive response if known, outcome, and clock change.
6. Update the state and recommendations. Allow correction/undo of an event.

Illustrative interaction, not a model prediction: on second-and-six, compare two available pass concepts and a run. If motion suggests man coverage, update the defensive distribution and rankings. After the actual play, branch into first-down options or third-down options based on the observed result.

## Delivery phases and acceptance gates

Indicative schedule for a small team with usable charted data; data acquisition can extend it. Progress depends on gates, not elapsed weeks.

| Phase | Approximate window | Deliverable | Exit gate |
| --- | --- | --- | --- |
| 1. Correctness and baseline | Weeks 1–2 | Shared schema/pipelines; correct targets and units; reliable history; versioned artifacts; baseline report | Training and serving transform the same example identically; categorical values and scaler preserved; selected-class confidence correct; history and possession transitions verified |
| 2. Training data | Weeks 2–3 | Multi-season canonical table, decision-time feature inventory, label coverage report, chronological splits | No duplicate canonical play keys; missing labels tracked; no future-derived features; preprocessing fit only on training data |
| 3. Opponent forecasting | Weeks 4–5 | Calibrated coverage and rush/box models plus opponent baselines | Better held-out log loss/Brier score than situational frequency baselines; calibration and per-team/class support reported |
| 4. Outcome ranking | Weeks 6–7 | Legal catalog; full-outcome scoring; mixed run/pass top three | Outcome errors and probability calibration improve over simple baselines; joint input constraints pass; low-support cases back off; coaches review recommendations |
| 5. OC loop and branches | Weeks 8–9 | Event persistence, observation updates, conditional audibles, two-play planner | Replay state transitions pass; incomplete observations work; actual results replace hypothetical branches; latency measured end to end |
| 6. Shadow pilot | Weeks 10–12 | Predictions logged before outcomes, coach feedback, drift report | Agreed accuracy/calibration and latency gates met on unseen games; no unsupported automatic deployment claim |

Suggested latency objective: warm recommendation response p95 under two seconds on the chosen deployment, measured separately from diagram rendering and cold starts. This is a target, not current measured performance.

## Evaluation protocol

- Initial chronological split using local seasons: train 2020–2022, validate/tune/calibrate 2023, test once on 2024. Use rolling earlier folds where label coverage supports them; keep complete games together. If prior work already tuned on 2024, treat it as a benchmark rather than an untouched test and reserve newer verified data or a prospective pilot.
- Recompute Elo, team tendencies, and player aggregates using only information available before each prediction. Sort events explicitly before calculating shifted history; reset by game/possession/drive as appropriate.
- Fit imputation, encoding, scaling, class grouping, and feature selection on training data only; persist the transformations. This follows scikit-learn's guidance on consistent preprocessing and leakage prevention. [Common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html)
- Defense: log loss, Brier score, calibration plots, class recall, and top-k coverage; compare league, opponent, and situation frequency baselines.
- Outcomes: EPA and yards MAE/RMSE with correct units; Brier/log loss for conversion, sacks, and turnovers; distribution interval coverage; results by team, season, down/distance, red zone, and late-game state.
- Calibration means that events forecast at approximately 70% happen approximately 70% of the time. Use separate fitting/calibration data and report reliability alongside discrimination. [Calibration guide](https://scikit-learn.org/stable/modules/calibration.html)
- Report paired uncertainty using game-level resampling; do not claim gains from a small score difference. Choose numerical improvement thresholds after measuring baseline variability and lock them before final testing.
- Recommendation quality: candidate validity, data support, ranking stability, coach review, and prospective decision logs. Accuracy at copying historical calls is not recommendation quality.
- Sequence value: compare one-play and two-play policies under the same simulator, then assess on held-out real observations. Simulator improvement alone is not evidence of real-game benefit.

## Implementation map and first sprint

Preserve Flask and React initially. Suggested new modules: `backend/features/`, `backend/schemas/`, `backend/evaluation/`, `backend/services/candidate_generator.py`, `defense_predictor.py`, `outcome_scorer.py`, and `sequence_planner.py`. Keep `/suggestPlay` as a compatibility adapter while introducing a versioned request/response contract.

Responses should contain numeric metrics, candidate IDs, defensive distributions, support/uncertainty metadata, conditional branches, and model/data version. Package preprocessing, model, feature schema, target units, training cutoff, and evaluation summary together; train locally without automatically publishing releases. Cache verified artifacts and provide health/readiness handling.

First sprint, in dependency order:

1. Specify game state, play event, candidate, and recommendation schemas; declare EPA versus yards units and pre-/post-snap fields.
2. Add meaningful regression checks for encoder/scaler parity, actual quarter, selected-class probability, event yardage, possession resets, and candidate validity.
3. Replace ad hoc one-row encoding with fitted pipelines; fix the all-season loader and training/serving feature differences.
4. Correct outcome labels and include all intended pass outcomes; remove actual air yards as an assumed known live input.
5. Produce data coverage/leakage audit and chronological baseline reports before further model complexity.
6. Build a small legal candidate catalog and score both runs and passes with the corrected outcome baseline.

First useful milestone: an OC enters a situation and receives three valid, comparable calls with correctly labeled estimates, explicit uncertainty, and a history that updates correctly. Defensive forecasting and branching build on that foundation.
