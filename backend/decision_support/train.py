"""Run from the repository root: python3 -m backend.decision_support.train."""

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, log_loss, mean_absolute_error, mean_squared_error

from .data import FEATURES, TARGETS, load_seasons, chronological_split
from .model import fit_bundle

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "models" / "decision_support"


def outcome_metrics(actual, predicted):
    return {
        target: {
            "mae": float(mean_absolute_error(actual[:, i], predicted[:, i])),
            "rmse": float(np.sqrt(mean_squared_error(actual[:, i], predicted[:, i]))),
        }
        for i, target in enumerate(TARGETS)
    }


def evaluate(bundle, frame):
    tendency = bundle["tendency"]
    probabilities = tendency.predict_proba(frame[FEATURES])
    classes = list(tendency.classes_)
    pass_probability = probabilities[:, classes.index("pass")]
    pass_actual = frame.action.eq("pass").to_numpy(dtype=float)
    prior = bundle["action_priors"]["pass"]
    bins = []
    for low in np.arange(0, 1, 0.1):
        mask = (pass_probability >= low) & (pass_probability < low + 0.1)
        if low > 0.89:
            mask = (pass_probability >= low) & (pass_probability <= 1)
        if mask.any():
            bins.append({"count": int(mask.sum()), "predicted": float(pass_probability[mask].mean()),
                         "observed": float(pass_actual[mask].mean())})
    report = {
        "rows": len(frame), "games": int(frame.game_id.nunique()),
        "tendency": {
            "log_loss": float(log_loss(frame.action, probabilities, labels=classes)),
            "accuracy": float(accuracy_score(frame.action, tendency.predict(frame[FEATURES]))),
            "pass_brier": float(np.mean((pass_probability - pass_actual) ** 2)),
            "prior_log_loss": float(log_loss(pass_actual, np.full(len(frame), prior), labels=[0, 1])),
            "prior_pass_brier": float(np.mean((prior - pass_actual) ** 2)),
            "calibration_bins": bins,
        },
        "outcomes": {},
    }
    for action in ("run", "pass"):
        rows = frame.loc[frame.action.eq(action)]
        predictions = bundle["outcomes"][action].predict(rows[FEATURES])
        actual = rows[TARGETS].to_numpy()
        baseline = np.tile(bundle["action_means"][action], (len(rows), 1))
        report["outcomes"][action] = {
            "rows": len(rows), "model": outcome_metrics(actual, predictions),
            "training_mean_baseline": outcome_metrics(actual, baseline),
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--train-start", type=int, default=2020)
    parser.add_argument("--train-end", type=int, default=2022)
    parser.add_argument("--validation-season", type=int, default=2023)
    parser.add_argument("--test-season", type=int, default=2024)
    args = parser.parse_args()
    if not args.train_start <= args.train_end < args.validation_season < args.test_season:
        parser.error("Require train_start <= train_end < validation_season < test_season")
    seasons = list(range(args.train_start, args.train_end + 1)) + [args.validation_season, args.test_season]
    print(f"Loading seasons {seasons}", flush=True)
    frame, audit = load_seasons(args.data_dir, seasons)
    for source in audit["sources"]:
        source["sha256"] = hashlib.sha256((args.data_dir / source["file"]).read_bytes()).hexdigest()
    splits = chronological_split(frame, args.train_end, args.validation_season, args.test_season)
    print(f"Training on {len(splits['train']):,} plays; all other seasons held out", flush=True)
    bundle = fit_bundle(splits["train"])
    report = {
        "status": "experimental_baseline", "data_audit": audit,
        "features": FEATURES, "target_units": bundle["target_units"],
        "sklearn_version": bundle["sklearn_version"],
        "split": {"train": bundle["train_seasons"], "validation": args.validation_season, "test": args.test_season},
        "limitations": [
            "Metrics evaluate only the observed action, not unchosen counterfactuals.",
            "Previously used repository seasons are benchmarks, not a pristine prospective test.",
            "No calibration fit or hyperparameter selection performed on holdout seasons.",
            "Action-mean baseline is minimal; opponent/situation baselines and uncertainty gates remain.",
        ],
    }
    report["training_recipe"] = {
        "model": "RandomForest", "n_estimators": 60, "max_depth": 12,
        "min_samples_leaf": 40, "random_state": 42,
        "outcome_target_scaling": "StandardScaler fitted on training action only",
    }
    identity = {"sources": audit["sources"], "split": report["split"],
                "recipe": report["training_recipe"], "features": FEATURES,
                "schema_version": bundle["schema_version"], "sklearn_version": bundle["sklearn_version"]}
    bundle["model_id"] = "baseline-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    report["model_id"] = bundle["model_id"]
    for split in ("validation", "test"):
        print(f"Evaluating {split}", flush=True)
        report[split] = evaluate(bundle, splits[split])
    bundle["evaluation"] = report
    args.output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.output_dir / "baseline.joblib", compress=3)
    (args.output_dir / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Saved local model and evaluation to {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
