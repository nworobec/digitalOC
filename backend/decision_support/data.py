"""Decision-time features and explicit labels for ordinary scrimmage plays."""

from pathlib import Path

import numpy as np
import pandas as pd


NUMERIC_FEATURES = [
    "down", "ydstogo", "yardline_100", "qtr", "game_seconds_remaining",
    "score_differential", "posteam_timeouts_remaining", "defteam_timeouts_remaining",
]
CATEGORICAL_FEATURES = ["posteam", "defteam"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGETS = ["epa", "yards_gained"]
RAW_COLUMNS = FEATURES + TARGETS + [
    "game_id", "play_id", "season", "play_type", "qb_dropback", "qb_scramble",
    "qb_kneel", "qb_spike", "sack", "interception", "fumble_lost",
]
TEAM_ALIASES = {"LAR": "LA", "OAK": "LV", "SD": "LAC"}


def normalize_teams(frame):
    frame = frame.copy()
    for column in CATEGORICAL_FEATURES:
        frame[column] = frame[column].astype("string").str.strip().str.upper().replace(TEAM_ALIASES)
    return frame


def prepare_plays(raw):
    """Never use actual coverage, air yards, or end-of-play state as input."""
    missing = sorted(set(RAW_COLUMNS) - set(raw.columns))
    if missing:
        raise ValueError(f"Missing data columns: {missing}")
    frame = normalize_teams(raw[RAW_COLUMNS])
    numeric = set(RAW_COLUMNS) - set(CATEGORICAL_FEATURES + ["game_id", "play_type"])
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    if frame[["game_id", "play_id", "season"]].isna().any().any():
        raise ValueError("Game, play, and season identifiers must be present")
    if frame.duplicated(["game_id", "play_id"]).any():
        raise ValueError("Duplicate game/play keys; fix input shards before training")

    eligible = (
        frame.play_type.isin(["run", "pass"])
        & frame.qb_kneel.eq(0) & frame.qb_spike.eq(0)
        & frame.down.isin([1, 2, 3, 4]) & frame.qtr.isin([1, 2, 3, 4])
        & frame.ydstogo.between(1, 100) & frame.yardline_100.between(1, 99)
        & frame.game_seconds_remaining.between(1, 3600)
        & frame.posteam_timeouts_remaining.between(0, 3)
        & frame.defteam_timeouts_remaining.between(0, 3)
    )
    frame = frame.loc[eligible].dropna(subset=FEATURES + TARGETS).copy()
    frame = frame.loc[frame.posteam.ne("") & frame.defteam.ne("")]
    # Scrambles are outcomes of pass intent, even when play_type says run.
    pass_intent = frame.play_type.eq("pass") | frame.qb_dropback.eq(1) | frame.qb_scramble.eq(1) | frame.sack.eq(1)
    frame["action"] = np.where(pass_intent, "pass", "run")
    return frame.sort_values(["season", "game_id", "play_id"]).reset_index(drop=True)


def load_seasons(data_dir, seasons):
    """Require both known shards per season; never silently pick one season."""
    frames, sources = [], []
    for season in seasons:
        for shard in (0, 1):
            path = Path(data_dir) / f"pbp_{season}_{shard}.csv"
            part = pd.read_csv(path, usecols=lambda c: c in RAW_COLUMNS, low_memory=False)
            if "season" not in part or not pd.to_numeric(part.season, errors="coerce").eq(season).all():
                raise ValueError(f"Incorrect or missing season in {path.name}")
            frames.append(part)
            sources.append({"file": path.name, "rows": len(part)})
    if not frames:
        raise ValueError("At least one season is required")
    raw = pd.concat(frames, ignore_index=True)
    prepared = prepare_plays(raw)
    audit = {
        "sources": sources, "raw_rows": len(raw), "eligible_rows": len(prepared),
        "excluded_rows": len(raw) - len(prepared),
        "season_counts": {str(k): int(v) for k, v in prepared.groupby("season").size().items()},
        "action_counts": {str(k): int(v) for k, v in prepared.action.value_counts().items()},
        "retained_sacks": int(prepared.sack.eq(1).sum()),
        "retained_interceptions": int(prepared.interception.eq(1).sum()),
        "retained_scrambles": int(prepared.qb_scramble.eq(1).sum()),
        "retained_lost_fumbles": int(prepared.fumble_lost.eq(1).sum()),
    }
    return prepared, audit


def chronological_split(frame, train_end=2022, validation_season=2023, test_season=2024):
    if not train_end < validation_season < test_season:
        raise ValueError("Require train_end < validation_season < test_season")
    splits = {
        "train": frame.loc[frame.season.le(train_end)].copy(),
        "validation": frame.loc[frame.season.eq(validation_season)].copy(),
        "test": frame.loc[frame.season.eq(test_season)].copy(),
    }
    seen_games = set()
    for name, split in splits.items():
        if split.empty or set(split.action.unique()) != {"run", "pass"}:
            raise ValueError(f"{name} must contain both run and pass plays")
        games = set(split.game_id)
        if seen_games & games:
            raise ValueError("A game crosses chronological splits")
        seen_games.update(games)
    return splits
