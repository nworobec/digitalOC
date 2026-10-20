# First implementation: compare call likelihood with play value

## What is available

The experimental `backend/decision_support/` package trains and serves a local run/pass comparison. It uses the existing NFL CSV files without importing the old release uploader or downloading deployed models. The new [connected dashboard](connected-dashboard.md) uses this baseline. The legacy `/suggestPlay` flow remains available separately.

For the same OC situation it reports:

- `historical_call_probability`: estimated likelihood that a coach calls run or pass. This is not success probability.
- `expected_epa`: estimated outcome in points, trained against EPA for all eligible outcomes of that action.
- `expected_yards`: estimated outcome in yards, trained against actual yards gained.
- `estimated_rank`: ordering by expected EPA, independent of call probability.
- Training support counts, model identity, and explicit experimental limitations.

An optional `allowed_actions` list constrains the comparison. Original call probabilities remain unchanged under that constraint; they are not renormalized to suggest certainty.

## Use locally

From the repository root, with the existing backend Python dependencies installed:

```sh
python3 -m backend.decision_support.train
python3 -m backend.decision_support.api
```

Training writes `backend/models/decision_support/baseline.joblib` and `evaluation.json` locally. These generated files are gitignored. The artifact includes fitted preprocessing, models, target units, training seasons, data-file hashes, recipe, and evaluation. Nothing is uploaded to GitHub Releases. Load only model files produced locally or otherwise trusted; joblib is a Python serialization format.

The API listens on `127.0.0.1:5001`. From another terminal:

```sh
curl http://127.0.0.1:5001/health
curl -X POST http://127.0.0.1:5001/evaluateOptions \
  -H 'Content-Type: application/json' \
  --data-binary @backend/decision_support/example-situation.json
```

All situation fields in the example are required. Unknown fields, unsupported teams, contradictory clocks, and invalid values are rejected instead of silently ignored. For example, a coverage hypothesis is deliberately rejected until a model consumes it. The baseline covers ordinary regulation scrimmage decisions; a fourth-down comparison omits kick and punt alternatives. The dashboard stores coverage observations separately and explicitly states that this model does not consume them.

Run verification:

```sh
python3 -m unittest discover -s backend/tests -v
```

## Foundation changes

1. **One fitted preprocessing pipeline.** Training and prediction use the same categorical vocabulary. Single-row prediction preserves team inputs. Encoders follow scikit-learn's fitted-transform approach. [OneHotEncoder documentation](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html)
2. **Explicit decision-time features.** Inputs are down, distance, field position, quarter, game clock, score differential, timeouts, and teams. Outcomes, actual coverage, actual air yards, and end-of-play fields cannot enter the feature list.
3. **Explicit action intent.** Sacks and scrambles belong to pass intent. Interceptions and lost fumbles remain in training. Kneels, spikes, nullified plays, special teams, overtime, and incomplete feature/target rows are excluded from this initial scope.
4. **Correct units.** EPA and yardage targets are distinct. Separate run and pass outcome models allow their value difference to vary with the situation. The random forests jointly predict EPA and yards after target scaling so yardage magnitude does not dominate their fit. [Random forest documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html)
5. **Chronological evaluation.** Both shards of every requested season are loaded. Default split: train 2020–2022, validation 2023, test benchmark 2024. Whole games cannot cross splits. No random row split or holdout fitting is used.
6. **Reproducibility.** Data hashes, training settings, schema, model identity, target units, and evaluation are saved. Duplicate play keys or missing input shards fail explicitly.

## Measured baseline, September 15, 2026

The local run used 104,239 training plays, 35,290 validation plays, and 34,728 test-benchmark plays. Across all eligible seasons it retained 6,656 sacks, 2,149 interceptions, 5,014 scrambles, and 1,271 lost fumbles (these categories may overlap).

2024 benchmark against a simple training-set mean for each action:

| Metric | Simple baseline | New model |
| --- | ---: | ---: |
| Run EPA mean absolute error, points | 0.6858 | 0.6705 |
| Pass EPA mean absolute error, points | 1.1533 | 1.1447 |
| Run yards mean absolute error | 3.8051 | 3.7024 |
| Pass yards mean absolute error | 6.9411 | 6.8553 |
| Run/pass tendency log loss | 0.6720 | 0.5810 |

Lower is better. Tendency baseline uses the overall training action frequency. The outcome improvements are modest; no significance or policy-improvement claim has been established. An API smoke check returned valid numeric estimates for both actions. Eleven tests passed, covering intent/outcome retention, chronological data handling, preprocessing consistency, save/load equivalence, input validation, and ranking by outcome when the higher-value action is historically less common.

## What this does not establish

- The evaluation scores predictions for the action actually taken. It does not reveal the outcome of unchosen actions or establish optimal play calls.
- The model averages over historical defensive responses; it does not explicitly predict them.
- Run/pass categories are not executable playbook concepts. Formation, personnel, motion, and history have not yet entered this new model.
- Call probabilities are uncalibrated. Support counts are league-wide down/distance counts, not matchup-specific evidence or confidence intervals.
- Point estimates and their ordering are experimental. Small differences should not be treated as decisive.
- Since prior project work used these seasons, 2024 is a reproducible benchmark rather than a pristine prospective test.

## Next increments

1. Add a versioned play-event history and correct current frontend state advancement, then use the same history builder in training and prediction.
2. Audit and join participation labels; forecast coverage and rush counts from information available before the snap. Compare against opponent/situation frequency baselines and calibrate probabilities.
3. Import a small valid playbook catalog with formation/personnel constraints and charted intended-call labels. Score complete supported candidates.
4. Add conversion/turnover probabilities, evidence thresholds, and uncertainty; evaluate with game-level resampling and coach review.
5. Integrate the comparison interface into React after these gates, then add a bounded two-play planner with verified state transitions.

The broader delivery roadmap is in [model-development-plan.md](model-development-plan.md).
