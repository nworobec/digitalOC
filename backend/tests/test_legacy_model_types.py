"""Regression checks for the model loaders and pandas type boundaries."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.model_trainers import pass_model, run_model


class ModelTypeRegressionTests(unittest.TestCase):
    def test_pass_loader_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing.csv")
            with self.assertRaisesRegex(FileNotFoundError, "No pass-model data files"):
                pass_model.load_first_existing([missing])

    def test_pass_defaults_keep_filtered_row_index(self):
        result = pass_model.add_football_intelligence_features(pd.DataFrame(index=[21, 47]))
        self.assertEqual(result.index.tolist(), [21, 47])
        self.assertEqual(result["play_type"].tolist(), ["pass", "pass"])
        self.assertEqual(result["yardline_100"].tolist(), [50, 50])
        self.assertEqual(result["is_first_down"].tolist(), [1, 1])

    def test_pass_encoding_and_training_preserve_pandas_metadata(self):
        frame = pd.DataFrame({
            "down": [1.0, np.nan, 3.0, 4.0] * 20,
            "posteam": ["KC", "BUF", "KC", None] * 20,
        }, index=range(100, 180))
        with contextlib.redirect_stdout(io.StringIO()):
            encoded, columns = pass_model.global_encode(frame, ["down", "posteam"])
            trained = pass_model.train_target_model(
                encoded, pd.Series(["short", "deep"] * 40, index=frame.index), "pass_length"
            )
        self.assertEqual(encoded.index.tolist(), frame.index.tolist())
        self.assertFalse(encoded.isna().any().any())
        self.assertEqual(trained["feature_columns"], columns)
        self.assertEqual(trained["classes"], ["deep", "short"])

    def test_run_training_handles_absent_participation_file(self):
        frame = pd.DataFrame({
            "play_type": ["run"] * 80, "qb_scramble": [0] * 80,
            "down": [1, 2] * 40, "ydstogo": [10, 4] * 40,
            "run_gap": ["guard", "end"] * 40,
            "run_location": ["left", "right"] * 40,
            "temp": [70.0, np.nan] * 40,
        })
        with patch.object(run_model.pd, "read_csv", side_effect=[
            frame.iloc[:40], frame.iloc[40:], FileNotFoundError("participation missing")
        ]), contextlib.redirect_stdout(io.StringIO()):
            models = run_model.train_run_models()
        self.assertEqual(set(models), {"run_gap", "run_location"})
        self.assertIn("temp", models["run_gap"]["columns"])
        self.assertIsNotNone(models["run_gap"]["scaler"])


if __name__ == "__main__":
    unittest.main()
