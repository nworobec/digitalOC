"""Execution annotations stay separate from immutable pre-snap plans."""
import copy
from .designs import default_design


def empty_execution():
    return dict(relationship='unknown', strength='unknown', motion='', assignments=default_design()['assignments'],
                motion_verified=False, assignments_verified=False)


def validate_execution(value, review, play):
    if not isinstance(value, dict) or set(value) != set(empty_execution()):
        raise ValueError('Provide complete execution review fields')
    if value['relationship'] not in ['unknown', 'as_planned', 'audible', 'modified', 'no_plan']:
        raise ValueError('Unsupported execution relationship')
    if value['strength'] not in ['unknown', 'left', 'right', 'balanced']:
        raise ValueError('Unsupported executed strength')
    for key in ['motion_verified', 'assignments_verified']:
        if type(value[key]) is not bool:
            raise ValueError('Execution verification must be true or false')
    if not isinstance(value['motion'], str) or len(value['motion']) > 500:
        raise ValueError('Motion instructions must be text of at most 500 characters')
    if not isinstance(value['assignments'], list) or len(value['assignments']) != 11:
        raise ValueError('Provide 11 execution assignments')
    for row in value['assignments']:
        if not isinstance(row, dict) or set(row) != {'role', 'route', 'blocking'}:
            raise ValueError('Execution assignments require role, route, and blocking')
        if any(not isinstance(v, str) or len(v) > (100 if k == 'role' else 500) for k, v in row.items()):
            raise ValueError('Invalid execution assignment text')
        if value['assignments_verified'] and any(not v.strip() for v in row.values()):
            raise ValueError('Describe every verified assignment; use N/A where appropriate')
    if value['motion_verified'] and not value['motion'].strip():
        raise ValueError('Describe verified motion, or explicitly enter No motion')
    if value['motion_verified'] or value['assignments_verified']:
        if not review['source_reference'].strip() or not review['reviewer'].strip():
            raise ValueError('Execution verification requires evidence and a reviewer')
    planned = (play.get('decision_context') or {}).get('play_design')
    if value['relationship'] == 'as_planned':
        if not planned:
            raise ValueError('No saved design snapshot exists for an as-planned comparison')
        definition = planned['definition']
        if (review['actual_call_id'] != play['call_id'] or review['actual_personnel'] != definition['personnel']
                or review['actual_formation'] != definition['formation'] or value['strength'] != definition['strength']
                or value['motion'] != definition['motion'] or value['assignments'] != definition['assignments']):
            raise ValueError('As-planned labels must match the recorded design; use Modified or Audible for differences')
    if value['relationship'] == 'no_plan' and planned:
        raise ValueError('This play has a saved design; describe its execution relationship')
    if value['relationship'] in ['modified', 'audible'] and not review['notes'].strip():
        raise ValueError('Explain the audible or assignment change in review notes')
    return copy.deepcopy(value)


def execution_blockers(review):
    execution = (review or {}).get('execution')
    execution = execution if isinstance(execution, dict) else empty_execution()
    reasons = []
    if execution.get('relationship', 'unknown') == 'unknown':
        reasons.append('Execution relationship is unknown')
    if execution.get('strength', 'unknown') == 'unknown':
        reasons.append('Executed formation strength is unknown')
    if execution.get('motion_verified') is not True:
        reasons.append('Executed motion has not been verified')
    if execution.get('assignments_verified') is not True:
        reasons.append('Executed assignments have not been verified')
    return reasons
