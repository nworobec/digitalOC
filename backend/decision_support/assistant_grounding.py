"""Server-owned facts, hypothetical transitions and reviewable coaching content.

The language model may select catalog IDs; it cannot author facts or statistics.
Unsupported hypothetical wording is clarified rather than guessed.
"""
import re

from .game import advance_play
from .plans import draft_plan, validate_content
from .suitability import suggest_concepts

WORDS = dict(zip(('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty').split(), range(21)))
NUMBER = r'(?:\d+|' + '|'.join(WORDS) + r')'
FAILURE = r"incomplete|incompletion|comes? up empty|comes? up short|stopped short|falls? short|miss(?:es|ed)? the sticks|short of the sticks|no gain|no yards|fail(?:s|ed)? to convert|do not convert|don't convert|not get (?:a |the )?first down|don't get (?:a |the )?first down"


def normalize(message):
    return message.lower().replace('’', "'").replace('–', '-').replace('—', '-').replace('‑', '-')


def number(text):
    return int(text) if text.isdigit() else WORDS[text]


def field_position(state):
    distance = state['yardline_100']
    return f'Own {100-distance}' if distance > 50 else 'Midfield' if distance == 50 else f'Opponent {distance}'


def situation_text(context):
    brief, state = context['situation_brief'], context['state']
    delta = state['offense_score'] - state['defense_score']
    score = 'The game is tied' if delta == 0 else f'Your offense leads by {delta}' if delta > 0 else f'Your offense trails by {-delta}'
    return (f"{brief['score']} · {brief['clock']} · {brief['down_distance']} · {brief['field_position']}. "
            f"{score}. {brief['clock_explanation']}. Timeouts: {brief['timeouts']}. "
            f"There are {state['yardline_100']} yards to the goal line and {state['ydstogo']} yards to the first-down marker. "
            f"Objective: {brief['objective']}.")


def response(context, explanation, adjustment=None, plan=None):
    return dict(reply='Situation: ' + situation_text(context) + '\n\n' + explanation +
                ('\n\nAdjustment: ' + adjustment if adjustment else ''), plan=plan)


def plan_request(message):
    q = normalize(message)
    if re.search(r"\b(?:don't|do not|no need to)\s+(?:draft|create|build|generate|revise)", q):
        return False
    return bool(re.search(r'\b(draft|create|build|generate|revise|write|make)\b', q) and
                re.search(r'plan|script|opening|counter', q))


def requested_count(question, noun, default):
    match = re.search(r'\b(' + NUMBER + r')\s+(?:conditional\s+)?' + noun, question)
    return min(15, max(1, number(match[1]))) if match else default


def grounded_plan(message, session, context):
    """Every plan response has an editable, eligible proposal or a clear constraint."""
    calls = context['available_calls']
    if not calls:
        return response(context, 'Plan: No installed calls meet the current situation and preferences. Adjust those constraints before drafting; no empty proposal was created.')
    q = normalize(message)
    opening_count = requested_count(q, r'opening(?:\s+calls)?', 3)
    counter_count = requested_count(q, r'counters?', 2)
    proposal = draft_plan(session, context['evaluation']['defense'])
    ordered = {call['id']: call for call in calls}
    # draft_plan is ordered by suitability; extend with other eligible catalog calls.
    order = list(dict.fromkeys([row['call_id'] for row in proposal['opening_script']] + list(ordered)))
    proposal['opening_script'] = [dict(call_id=id, purpose=ordered[id]['summary'], watch=ordered[id]['read'])
                                  for id in order[:opening_count]]
    counters = {row['call_id']: row for row in proposal['counters']}
    for id in order:
        counters.setdefault(id, dict(call_id=id,
            condition=f"If the observed defense and protection fit {ordered[id]['name']}, recheck eligibility before switching",
            reason=ordered[id]['read']))
    proposal['counters'] = list(counters.values())[:counter_count]
    proposal['notes'] = situation_text(context) + ' Review order only, not a prediction of successive snaps. Recheck eligibility after every play. Starter-template reads require coach review.'
    proposal = validate_content(proposal, session)
    explanation = (f"Plan: Prepared {len(proposal['opening_script'])} opening calls and {len(proposal['counters'])} conditional counters from currently eligible templates. "
                   'Review and edit the proposal below; it is not saved until you choose Save coaching plan. '
                   'This is a rules-based draft, not an optimized sequence or a prediction of the opponent.')
    if len(order) < max(opening_count, counter_count):
        explanation += f' Only {len(order)} distinct eligible calls are available, so the requested count is limited.'
    return response(context, explanation, plan=proposal)


def evidence_text(context):
    evaluation = context['evaluation']
    comparison = evaluation.get('comparison')
    text = ('Evidence: Named-concept EPA, conversion probability, kicking probability and guaranteed outcomes are unavailable. '
            'EPA is measured in expected points, not yards. Historical call frequency is not conversion probability. ')
    if comparison:
        text += 'Current-situation run/pass estimates only: '
        text += '; '.join(f"{row['action']}: {row['expected_epa']:+.3f} expected points added, {row['expected_yards']:.2f} expected yards, "
                          f"{100*row['historical_call_probability']:.1f}% historical call probability" for row in comparison['options']) + '. '
        text += 'These observational estimates do not establish the benefit of choosing a named play or a fourth-down kicking decision. '
    else:
        text += 'The run/pass outcome model is unavailable for this session. '
    defense = evaluation.get('defense', {})
    if defense.get('status') == 'historical_frequencies':
        text += (f"Opponent coverage evidence: {defense['sample_count']} labeled dropbacks; seasons {', '.join(map(str, defense['seasons']))}; "
                 f"scope: {defense['scope']}; source: {defense['source']}. These frequencies do not identify the next defensive look.")
    else:
        text += 'Opponent coverage evidence is unavailable. '
    return text


def transition_text(state, gain, preferences, elapsed=0):
    kind = 'touchdown' if gain == state['yardline_100'] else 'safety' if state['yardline_100']-gain == 100 else 'gain'
    after, status = advance_play(state, dict(kind=kind, yards=gain, elapsed_seconds=elapsed))
    prefix = f'With a {gain}-yard gain, '
    if status == 'finished':
        return prefix + 'the regulation clock expires; set the official result before considering another snap.', []
    if status != 'active':
        end = 'the play reaches the end zone for a touchdown' if kind == 'touchdown' else 'the play results in a safety' if kind == 'safety' else 'failure on fourth down ends possession' if state['down'] == 4 and gain < state['ydstogo'] else 'the period transition requires setting the next possession'
        return prefix + end + '; set the next possession before considering another offensive call.', []
    ordinal = {1:'first', 2:'second', 3:'third', 4:'fourth'}[after['down']]
    fit = suggest_concepts(after, preferences)['eligible_call_ids']
    return prefix + f"it would be {ordinal} and {after['ydstogo']} at {field_position(after)}.", fit


def grounded_answer(message, session, context):
    """Resolve supported factual requests; return None for catalog-selection questions."""
    q, state = normalize(message), context['state']
    if re.fullmatch(r"(?:what about |and |why )?(?:the )?(?:other one|that one|that|it)\??", q.strip()):
        return response(context, 'Clarification needed: Name the call or scenario you mean so I do not choose a referent for you.')
    if plan_request(message):
        return grounded_plan(message, session, context)
    if re.search(r'\b(probability|probabilities|epa|guarantee\w*|percentage|odds)\b', q):
        return response(context, evidence_text(context))
    hypothetical = bool(re.search(r'\b(hypothetically|suppose|what if|if we were|imagine)\b', q))
    deficit = re.search(r'\b(?:down|trailing(?: by)?)\s+(' + NUMBER + r')\b', q)
    clock = re.search(r'\b(' + NUMBER + r')\s+(seconds?|minutes?)\s+(?:left|remaining)', q)
    if hypothetical:
        if deficit and 'field goal' in q:
            margin = number(deficit[1]) - 3
            result = f'leave a {margin}-point deficit' if margin > 0 else 'tie the game' if margin == 0 else f'give a {-margin}-point lead'
            timing = f" With {number(clock[1])} {clock[2]} left in your hypothetical, time to regain possession matters." if clock else ''
            return response(context, f'Hypothetical only: A successful field goal while trailing by {number(deficit[1])} would {result}.{timing} '
                            'If still behind, you would need another scoring possession. Kicker range, possession recovery and win probabilities are not modeled; this does not establish the best decision. Saved game unchanged.')
        # Other scenarios are handled below only when their outcome can be computed.
    if not hypothetical and (deficit or clock):
        claimed_deficit = number(deficit[1]) if deficit else None
        claimed_clock = number(clock[1]) * (60 if clock[2].startswith('minute') else 1) if clock else None
        if ((claimed_deficit is not None and claimed_deficit != state['defense_score'] - state['offense_score']) or
                (claimed_clock is not None and claimed_clock != state['quarter_seconds_remaining'])):
            return response(context, 'Context check: The score or clock in your question conflicts with the saved situation above. '
                            'I have not treated that premise as a game update. Confirm the intended hypothetical or update the game controls before choosing a play.')
    if re.search(r'penalt|flag|intercept|fumble', q):
        return response(context, 'Clarification needed: Specify the official turnover result or penalty enforcement before calculating possession and the next down.')
    if re.search(r'\b(fourth|4th)[ -]down\b', q) and re.search(r'fail|unsuccessful|stopped', q):
        return response(context, 'Rules: A failed fourth-down conversion ends possession, assuming no penalty changes the result. '
                        'There is no subsequent offensive snap to punt or kick a field goal on that drive. Choose whether to kick or go for it before the fourth-down attempt. '
                        'This answers your hypothetical; the saved down has not changed.')
    gain_match = re.search(r'\b(?:gain(?:s|ed|ing)?(?: of)?|pick(?:s|ed|ing)? up)\s+(' + NUMBER + r')\s+yards?', q)
    if not gain_match:
        gain_match = re.search(r'\b(' + NUMBER + r')[ -]yard gain\b', q)
    loss_match = re.search(r'\b(?:lose|loses|lost|losing|loss of)\s+(' + NUMBER + r')\s+yards?', q)
    failure = re.search(FAILURE, q)
    if gain_match or loss_match or failure:
        if state['quarter_seconds_remaining'] == 0 or context['status'] != 'active':
            return response(context, 'The saved period or possession is not active. Set the next situation before calculating another snap.')
        specified = re.search(r'\b([1-4])(?:st|nd|rd|th)?\s*(?:&|and)\s*(\d+)', q)
        if specified and (int(specified[1]), int(specified[2])) != (state['down'], state['ydstogo']):
            return response(context, 'Clarification needed: The down and distance in your question differ from the saved state. Update the situation or provide the full hypothetical field position and down/distance.')
        if hypothetical and (deficit or clock):
            return response(context, 'Clarification needed: This combines a different score or clock with a play outcome. Provide the complete hypothetical situation so those assumptions are not mixed with the saved game.')
        if gain_match and loss_match:
            return response(context, 'Clarification needed: You described both a gain and a loss. Specify one net yardage result.')
        elapsed_match = re.search(r'\b(?:takes?|elapsed time(?: is| of)?)\s+(' + NUMBER + r')\s+seconds?', q)
        elapsed = number(elapsed_match[1]) if elapsed_match else 0
        gain = number(gain_match[1]) if gain_match else -number(loss_match[1]) if loss_match else None
        zero = bool(re.search(r'incomplete|incompletion|comes? up empty|no gain|no yards', q))
        gains = [gain] if gain is not None else [0] if zero else sorted({0, max(0, state['ydstogo']-5)})
        try:
            transitions = [transition_text(state, value, context['preferences'], elapsed)[0] for value in gains]
        except ValueError:
            return response(context, 'Clarification needed: The yardage or elapsed time is outside the supported bounds. Specify the net gain, time used and whether the play scored.')
        text = 'Next situation: ' + ' '.join(transitions)
        if gain is None and not zero:
            text += ' These are examples; provide the actual net gain for an exact result.'
        if state['down'] == 3 and elapsed < state['quarter_seconds_remaining'] and all(value < state['ydstogo'] for value in gains):
            text += (' Before the fourth-down snap, compare a field goal if within range, punting for field position, and going for it. '
                     'A failed fourth-down conversion ends possession; you cannot then kick on that drive. '
                     'Near the opponent goal line, consider the field-goal opportunity before risking a long fourth-down attempt. '
                     'No kicking or conversion model establishes the best choice.')
        return response(context, text, 'No game update was made. ' + (f'Applied {elapsed} elapsed seconds to the hypothetical only. ' if elapsed_match else 'Clock held constant because elapsed time was not supplied. ') + 'Assume no penalty or turnover. Recheck call eligibility for the resulting down, distance and field position.')
    if hypothetical:
        return response(context, 'Clarification needed: Provide the hypothetical down, distance, field position, score and time, or a specific gain from the saved situation. I will keep that scenario separate from the saved game.')
    if re.search(r'\b(clock|score|seconds|minutes|goal line|first.down marker|own 20|their 20|field position|current saved game)\b', q):
        return response(context, 'Context: The values above come directly from the saved game, not earlier chat examples. '
                        'The quarter clock is minutes:seconds. Score and time alone do not establish a must-score decision; no win-probability model is available.')
    return None


def render_selection(selection, context):
    """No model-authored prose, numbers or unvalidated IDs cross this boundary."""
    if not isinstance(selection, dict) or set(selection) != {'call_ids', 'focus'}:
        raise ValueError('Expected call_ids and focus')
    if selection['focus'] not in ('calls', 'evidence', 'clarify'):
        raise ValueError('Unsupported focus')
    ids = selection['call_ids']
    available = {call['id']: call for call in context['available_calls']}
    if (not isinstance(ids, list) or len(ids) > 3 or any(not isinstance(id, str) or id not in available for id in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('Calls must be unique and eligible in the current situation')
    if selection['focus'] == 'clarify':
        return response(context, 'Clarification needed: I can explain the saved situation, calculate a specified gain, compare available run/pass evidence, or draft a plan. State which decision you want to review; unsupported scenarios will not be guessed.')
    if selection['focus'] == 'evidence':
        return response(context, evidence_text(context))
    if not ids:
        raise ValueError('Select at least one eligible call or ask for clarification')
    paragraphs = ['Call options: These fit the current catalog constraints; they are not a prediction of the best outcome.']
    for id in ids:
        call = available[id]
        paragraphs.append(f"{call['name']} ({call['type']}): {call['summary']} Read: {call['read']}")
        low, high = call['distance_range']
        if not low <= context['state']['ydstogo'] <= high:
            paragraphs.append(f"Caution: Outside this template's preferred {low}–{high} yard distance band. Eligibility does not mean this is a suitable conversion choice.")
    paragraphs.append('Coverage is a coach hypothesis unless observed; historical coverage does not establish the next look. No named-call success probability is available.')
    return response(context, '\n\n'.join(paragraphs), 'Confirm protection and assignments, and recheck eligibility after the next snap. Starter templates require coach review.')
