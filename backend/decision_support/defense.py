"""Descriptive historical coverage frequencies, not calibrated forecasts."""

from functools import lru_cache
from pathlib import Path
import pandas as pd


@lru_cache(maxsize=2)
def coverage_rows(data_dir):
    frames = []
    for year in range(2020, 2025):
        folder = Path(data_dir)
        parts = folder / f"pbp_participation_{year}.csv"
        shards = [folder / f"pbp_{year}_{i}.csv" for i in (0, 1)]
        if not parts.exists() or not all(path.exists() for path in shards):
            continue
        pbp = pd.concat([pd.read_csv(path, usecols=["game_id", "play_id", "defteam", "down", "ydstogo", "qb_dropback"], low_memory=False)
                         for path in shards], ignore_index=True)
        participation = pd.read_csv(parts, usecols=["nflverse_game_id", "play_id", "defense_coverage_type"], low_memory=False).rename(columns={"nflverse_game_id": "game_id"})
        if pbp.duplicated(["game_id", "play_id"]).any() or participation.duplicated(["game_id", "play_id"]).any():
            raise ValueError("Duplicate coverage join keys")
        merged = pbp.merge(participation, on=["game_id", "play_id"], how="inner", validate="one_to_one")
        merged = merged.loc[merged.qb_dropback.eq(1) & merged.defense_coverage_type.notna()].copy()
        merged = merged.loc[~merged.defense_coverage_type.isin(["UNKNOWN", "", "NA"])]
        merged["season"] = year
        frames.append(merged)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def describe_defense(data_dir, state):
    try:
        rows = coverage_rows(str(data_dir))
    except (OSError, ValueError, KeyError) as error:
        return {"status": "unavailable", "reason": f"Coverage data could not be loaded: {error}"}
    if rows.empty:
        return {"status": "unavailable", "reason": "No local coverage data available"}
    opponent = rows.loc[rows.defteam.eq(state["defteam"])]
    same_down = opponent.loc[opponent.down.eq(state["down"])]
    distance = state["ydstogo"]
    low, high = (1, 3) if distance <= 3 else (4, 6) if distance <= 6 else (7, 10) if distance <= 10 else (11, 100)
    matched = same_down.loc[same_down.ydstogo.between(low, high)]
    scope = "opponent, down, and distance band"
    if len(matched) < 50:
        matched, scope = same_down, "opponent and down"
    if len(matched) < 50:
        matched, scope = opponent, "opponent across all downs"
    if matched.empty:
        return {"status": "unavailable", "reason": "No labeled dropbacks for this opponent"}
    counts = matched.defense_coverage_type.value_counts()
    distribution = [{"coverage": str(label), "count": int(count), "frequency": float(count / len(matched))}
                    for label, count in counts.items()]
    return {"status": "historical_frequencies", "distribution": distribution, "sample_count": len(matched),
            "seasons": sorted(int(year) for year in matched.season.unique()), "scope": scope,
            "description": "Observed coverage on labeled historical dropbacks; not a forecast for the next snap.",
            "source": "NFL NGS / FTN via nflverse", "observed_look": state["coverage"]}
