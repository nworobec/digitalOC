import json
from pathlib import Path
import tempfile
import unittest
from typing import cast

import joblib
import numpy as np
import pandas as pd

from backend.decision_support.api import create_app
from backend.decision_support.data import FEATURES, prepare_plays, chronological_split, load_seasons
from backend.decision_support.model import fit_bundle, compare_options


def raw_play(play_id=1, **updates):
    row = {
        "game_id": "2022_01_KC_BUF", "play_id": play_id, "season": 2022,
        "down": 2, "ydstogo": 6, "yardline_100": 45, "qtr": 2,
        "game_seconds_remaining": 2100, "score_differential": 0,
        "posteam_timeouts_remaining": 3, "defteam_timeouts_remaining": 3,
        "posteam": "KC", "defteam": "BUF", "play_type": "run",
        "qb_dropback": 0, "qb_scramble": 0, "qb_kneel": 0, "qb_spike": 0,
        "sack": 0, "interception": 0, "fumble_lost": 0,
        "epa": -0.2, "yards_gained": 3,
    }
    row.update(updates)
    return row


class DataTests(unittest.TestCase):
    def test_pass_intent_keeps_negative_outcomes_and_excludes_special_actions(self):
        raw = pd.DataFrame([
            raw_play(1),
            raw_play(2, play_type="pass", sack=1, epa=-2, yards_gained=-8),
            raw_play(3, play_type="pass", interception=1, epa=-4),
            raw_play(4, qb_scramble=1, qb_dropback=1),
            raw_play(5, qb_kneel=1),
            raw_play(6, play_type="pass", qb_spike=1),
            raw_play(7, play_type="no_play"),
        ])
        rows = prepare_plays(raw)
        self.assertEqual(rows.play_id.tolist(), [1, 2, 3, 4])
        self.assertEqual(rows.action.tolist(), ["run", "pass", "pass", "pass"])
        self.assertEqual(rows.loc[1, "yards_gained"], -8)
        self.assertEqual(rows.loc[2, "epa"], -4)
        self.assertFalse(set(FEATURES) & {"epa", "air_yards", "defense_coverage_type", "yards_gained", "sack"})

    def test_duplicate_keys_fail(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            prepare_plays(pd.DataFrame([raw_play(), raw_play()]))

    def test_missing_targets_are_not_imputed_as_success(self):
        rows = prepare_plays(pd.DataFrame([raw_play(1), raw_play(2, epa=np.nan)]))
        self.assertEqual(len(rows), 1)

    def test_loader_includes_every_season_and_shard(self):
        with tempfile.TemporaryDirectory() as directory:
            for season in (2020, 2021):
                for shard in (0, 1):
                    pd.DataFrame([raw_play(shard, season=season, game_id=f"{season}_01_KC_BUF")]).to_csv(
                        Path(directory) / f"pbp_{season}_{shard}.csv", index=False,
                    )
            rows, audit = cast(tuple[pd.DataFrame, dict], load_seasons(directory, [2020, 2021]))
        self.assertEqual(len(rows), 4)
        self.assertEqual(len(audit["sources"]), 4)

    def test_chronological_splits_keep_games_separate(self):
        raw = [raw_play(i, season=s, game_id=f"{s}_01_KC_BUF", play_type=a)
               for s in (2022, 2023, 2024) for i, a in enumerate(("run", "pass"))]
        splits = chronological_split(prepare_plays(pd.DataFrame(raw)))
        self.assertEqual(splits["train"].season.unique().tolist(), [2022])
        self.assertEqual(splits["test"].season.unique().tolist(), [2024])
        with self.assertRaises(ValueError):
            chronological_split(prepare_plays(pd.DataFrame(raw)), train_end=2024)


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Runs are much more common, but passes have higher EPA in this fixture.
        raw = [raw_play(i, play_type="pass" if i % 5 == 0 else "run",
                        epa=1.5 if i % 5 == 0 else -0.2,
                        yards_gained=9 if i % 5 == 0 else 3,
                        posteam="KC" if i % 2 else "BUF",
                        defteam="BUF" if i % 2 else "KC") for i in range(200)]
        cls.train = prepare_plays(pd.DataFrame(raw))
        cls.bundle = fit_bundle(cls.train, n_estimators=8, min_samples_leaf=2)
        cls.situation = {key: raw_play()[key] for key in FEATURES}

    def test_outcome_order_does_not_copy_most_common_call(self):
        result = compare_options(self.bundle, self.situation)
        best, other = result["options"]
        self.assertEqual(best["action"], "pass")
        self.assertLess(best["historical_call_probability"], other["historical_call_probability"])
        self.assertAlmostEqual(best["expected_epa"], 1.5)
        self.assertAlmostEqual(best["expected_yards"], 9)
        self.assertAlmostEqual(sum(x["historical_call_probability"] for x in result["options"]), 1)

    def test_one_row_encoding_matches_batch_and_preserves_team(self):
        transform = self.bundle["tendency"].named_steps["features"]
        batch = transform.transform(self.train[FEATURES])
        single = transform.transform(self.train[FEATURES].iloc[[0]])
        np.testing.assert_allclose(single[0], batch[0])
        self.assertFalse(np.array_equal(batch[0], batch[1]))

    def test_serialized_bundle_matches_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.joblib"
            joblib.dump(self.bundle, path)
            restored = joblib.load(path)
        original = compare_options(self.bundle, self.situation)
        reloaded = compare_options(restored, self.situation)
        # Parallel forest reductions can differ at floating-point roundoff.
        original_options = original.pop("options")
        reloaded_options = reloaded.pop("options")
        self.assertEqual(original, reloaded)
        self.assertEqual(len(original_options), len(reloaded_options))
        for expected, actual in zip(original_options, reloaded_options):
            for key in ("expected_epa", "expected_yards", "historical_call_probability"):
                self.assertAlmostEqual(expected.pop(key), actual.pop(key), places=12)
            self.assertEqual(expected, actual)

    def test_constraints_keep_original_tendency_probability(self):
        unconstrained = compare_options(self.bundle, self.situation)
        constrained = compare_options(self.bundle, self.situation, ["run"])
        self.assertEqual(len(constrained["options"]), 1)
        self.assertAlmostEqual(constrained["options"][0]["historical_call_probability"],
                         unconstrained["options"][1]["historical_call_probability"])

    def test_api_validates_inputs_and_emits_numeric_units(self):
        client = create_app(bundle=self.bundle).test_client()
        response = client.post("/evaluateOptions", json={"current_situation": self.situation})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json(silent=True) or {}
        self.assertIsInstance(payload["options"][0]["expected_epa"], float)
        invalid_payloads = [
            None,
            [],
            {},
            {"current_situation": {**self.situation, "qtr": 4}},
            {"current_situation": {**self.situation, "down": True}},
            {"current_situation": {**self.situation, "posteam": "ZZZ"}},
            {"current_situation": {**self.situation, "defense_coverage_type": "COVER_3"}},
            {"current_situation": self.situation, "allowed_actions": []},
            {"current_situation": self.situation, "play_history": []},
        ]
        for invalid_payload in invalid_payloads:
            with self.subTest(payload=invalid_payload):
                self.assertEqual(
                    client.post(
                        "/evaluateOptions",
                        data=json.dumps(invalid_payload),
                        content_type="application/json",
                    ).status_code,
                    400,
                )

    def test_missing_model_has_explicit_not_ready_response(self):
        with tempfile.TemporaryDirectory() as directory:
            client = create_app(Path(directory) / "absent.joblib").test_client()
            self.assertEqual(client.get("/health").status_code, 503)
            self.assertEqual(client.post("/evaluateOptions", json={}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
