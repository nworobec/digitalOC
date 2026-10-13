"""Coach-declared play design metadata; never inferred from schematic coordinates."""
import copy
from .playbook import PERSONNEL, FORMATIONS

ROLES = ['Left wide player', 'Left slot player', 'Left tackle', 'Left guard', 'Center',
         'Right guard', 'Right tackle', 'Right slot player', 'Right wide player', 'Quarterback', 'Running back']


def default_design():
    return dict(personnel='any', formation='any', strength='unknown', motion='',
                assignments=[dict(role=role, route='', blocking='') for role in ROLES])


def validate_design(value, call):
    if not isinstance(value, dict) or set(value) != set(default_design()):
        raise ValueError('Provide complete design metadata')
    for key, choices in [('personnel', PERSONNEL), ('formation', FORMATIONS),
                         ('strength', ['unknown', 'left', 'right', 'balanced'])]:
        if not isinstance(value[key], str) or value[key] not in choices:
            raise ValueError(f'Unsupported design {key}')
    if value['personnel'] != 'any' and value['personnel'] not in call['personnel']:
        raise ValueError('Personnel does not match this installed concept template')
    if value['formation'] != 'any' and value['formation'] not in call['formations']:
        raise ValueError('Formation does not match this installed concept template')
    def text(v, limit):
        if not isinstance(v, str) or len(v) > limit:
            raise ValueError(f'Design notes must be text of at most {limit} characters')
    text(value['motion'], 500)
    if not isinstance(value['assignments'], list) or len(value['assignments']) != 11:
        raise ValueError('Provide assignments for all 11 markers')
    for row in value['assignments']:
        if not isinstance(row, dict) or set(row) != {'role', 'route', 'blocking'}:
            raise ValueError('Each assignment requires role, route, and blocking')
        for key in row:
            text(row[key], 100 if key == 'role' else 500)
        if not row['role'].strip():
            raise ValueError('Every marker needs a player role')
    return copy.deepcopy(value)
