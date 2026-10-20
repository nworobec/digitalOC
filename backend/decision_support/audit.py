"""Read-only local source audit. Run with python3 -m backend.decision_support.audit."""
import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .data import FEATURES

CONCEPT_FIELDS = ['concept_id', 'play_concept', 'concept', 'offensive_concept']
LABEL_FIELDS = CONCEPT_FIELDS + ['route', 'offense_formation', 'offense_personnel', 'defense_coverage_type']
AUDIT_FIELDS = list(dict.fromkeys(FEATURES + LABEL_FIELDS + ['game_id', 'nflverse_game_id', 'play_id', 'play_type', 'epa', 'yards_gained']))
CANONICAL = re.compile(r'^(pbp_20\d\d_[01]|pbp_participation_20\d\d)\.csv$')


def audit_sources(data_dir):
    root = Path(data_dir).resolve()
    manifest = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(root.glob('*.csv')))
    return _audit(str(root), manifest)


@lru_cache(maxsize=2)
def _audit(root, manifest):
    files, errors = [], []
    groups = {name: Counter() for name in ('pbp', 'participation')}
    for name, size, modified in manifest:
        item = dict(file=name, bytes=size, modified_ns=modified, scope='inventory_only')
        try:
            path = Path(root) / name
            with path.open(newline='', encoding='utf-8-sig') as stream:
                headers = next(csv.reader(stream))
            item['available_label_columns'] = [key for key in LABEL_FIELDS if key in headers]
            if not CANONICAL.match(name):
                files.append(item)
                continue
            group = 'participation' if 'participation' in name else 'pbp'
            item.update(scope=group, rows=0, missing_key_rows=0, scrimmage_rows=0,
                        populated={key: 0 for key in AUDIT_FIELDS if key in headers}, samples={},
                        missing_columns=[key for key in LABEL_FIELDS if key not in headers],
                        scrimmage_with_both_targets=0)
            usecols = [key for key in AUDIT_FIELDS if key in headers]
            if not usecols:
                raise ValueError('No recognized audit fields')
            for frame in pd.read_csv(path, usecols=usecols, dtype='string', chunksize=20000):
                frame = frame.apply(lambda col: col.str.strip().replace({'': pd.NA, 'UNKNOWN': pd.NA, 'Unknown': pd.NA}))
                item['rows'] += len(frame)
                for key in usecols:
                    values = frame[key]
                    valid = values.notna()
                    if key in ('epa', 'yards_gained'):
                        valid &= np.isfinite(pd.to_numeric(values, errors='coerce').astype(float))
                    item['populated'][key] += int(valid.sum())
                    if key in LABEL_FIELDS:
                        item['samples'][key] = sorted(set(item['samples'].get(key, [])) | set(values.dropna().unique()))[:12]
                game_key = 'nflverse_game_id' if 'nflverse_game_id' in frame else 'game_id'
                if game_key in frame and 'play_id' in frame:
                    ids = pd.to_numeric(frame.play_id, errors='coerce')
                    valid_ids = ids.notna() & np.isfinite(ids.astype(float)) & (ids % 1 == 0)
                    good = frame[game_key].notna() & valid_ids
                    item['missing_key_rows'] += int((~good).sum())
                    groups[group].update(zip(frame.loc[good, game_key], ids.loc[good].astype(int)))
                else:
                    item['missing_key_rows'] += len(frame)
                if 'play_type' in frame:
                    scrimmage = frame.play_type.isin(['run', 'pass'])
                    item['scrimmage_rows'] += int(scrimmage.sum())
                    if {'epa', 'yards_gained'} <= set(frame):
                        targets = frame[['epa', 'yards_gained']].apply(pd.to_numeric, errors='coerce').astype(float)
                        item['scrimmage_with_both_targets'] += int((scrimmage & np.isfinite(targets).all(axis=1)).sum())
        except (OSError, ValueError, StopIteration, pd.errors.ParserError) as error:
            item['error'] = str(error)
            errors.append(dict(file=name, error=str(error)))
        files.append(item)
    pbp, participation = groups['pbp'], groups['participation']
    expected = {f'pbp_{year}_{shard}.csv' for year in range(2020, 2025) for shard in (0, 1)} | {f'pbp_participation_{year}.csv' for year in range(2020, 2025)}
    canonical = [f for f in files if f['scope'] != 'inventory_only']
    return dict(schema_version=1, generated_at=datetime.now(timezone.utc).isoformat(),
                freshness='Cached by local file names, sizes, and modification times; not content hashes.',
                status='incomplete' if errors or expected - {f[0] for f in manifest} else 'complete',
                files=files, errors=errors, missing_expected_files=sorted(expected - {f[0] for f in manifest}),
                summary=dict(canonical_files=len(canonical),
                             pbp_rows=sum(f.get('rows', 0) for f in canonical if f['scope'] == 'pbp'),
                             participation_rows=sum(f.get('rows', 0) for f in canonical if f['scope'] == 'participation'),
                             scrimmage_rows=sum(f.get('scrimmage_rows', 0) for f in canonical),
                             scrimmage_with_both_targets=sum(f.get('scrimmage_with_both_targets', 0) for f in canonical),
                             recognized_concept_label_cells=sum(sum(f.get('populated', {}).get(k, 0) for k in CONCEPT_FIELDS) for f in canonical)),
                keys={group: dict(unique_keys=len(counts), duplicate_extra_rows=sum(n - 1 for n in counts.values()),
                                  duplicate_examples=[dict(game_id=k[0], play_id=k[1], rows=n) for k, n in sorted(counts.items()) if n > 1][:10]) for group, counts in groups.items()},
                join=dict(matched_unique_keys=len(pbp.keys() & participation.keys()),
                          pbp_without_participation=len(pbp.keys() - participation.keys()),
                          participation_without_pbp=len(participation.keys() - pbp.keys())),
                limitations=[
                    'Counts cover raw files, including non-scrimmage records; scrimmage means play_type run/pass, not final training eligibility.',
                    'Cleaned, merged, and aggregate files are inventoried only, not pooled with raw records, to avoid double counting.',
                    'A route label is not a full play concept. Recognized concept columns require semantic review before catalog mapping.',
                    'Formation/personnel strings are not automatically mapped to the dashboard catalog.',
                    'Actual route and coverage labels describe the play after the snap; do not use them as pre-snap predictors.',
                    'Populated fields and matched keys do not establish label accuracy or a safe one-to-one join; inspect duplicates.',
                ])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'data')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps(audit_sources(args.data_dir), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result + '\n')
    else:
        print(result)
