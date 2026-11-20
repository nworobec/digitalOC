import React from 'react';
import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import CoachesNotes from './CoachesNotes';
const calls = [{id: 'mesh', name: 'Mesh sit', type: 'PASS', personnel: ['11'], formations: ['gun_trips'], minimum_field_space: 1}];
const state = {posteam: 'KC', defteam: 'BUF', down: 1, ydstogo: 10, yardline_100: 75, action_filter: 'all'};
const preferences = {installed_call_ids: ['mesh'], personnel: 'any', formation: 'any', anticipated_coverage: 'UNKNOWN'};
const content = {title: 'Opening plan', notes: 'Check protection', opening_script: [{call_id: 'mesh', purpose: 'Crossers', watch: 'Leverage'}], counters: []};
const session = {id: 'one', state, preferences, coaching_plan: {context_id: 'hash', context: {state, preferences}, updated_at: '2026-10-13', content, evidence: {status: 'unavailable', reason: 'No coverage data'}}};
const props = {session, calls, onEditing: jest.fn(), onGenerate: jest.fn(), onSave: jest.fn()};

test('edit and save structured notes and counters with missing evidence', async () => {
    const save = jest.fn().mockResolvedValue(session);
    render(<CoachesNotes {...props} onSave={save}/>);
    expect(screen.getByText(/No coverage data/)).toBeInTheDocument();
    fireEvent.click(screen.getByText('Edit plan'));
    fireEvent.change(screen.getByLabelText('Game-plan notes'), {target: {value: 'Protect right tackle'}});
    fireEvent.click(screen.getByText('Add counter'));
    fireEvent.change(screen.getByLabelText('condition 1'), {target: {value: 'If man coverage is confirmed'}});
    fireEvent.click(screen.getByText('Save coaching plan'));
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls[0][0]).toBe('hash');
    expect(save.mock.calls[0][1].notes).toBe('Protect right tackle');
    expect(save.mock.calls[0][1].counters[0].call_id).toBe('mesh');
});

test('failed save retains edits; discard restores saved content', async () => {
    render(<CoachesNotes {...props} onSave={jest.fn().mockResolvedValue(undefined)}/>);
    fireEvent.click(screen.getByText('Edit plan'));
    fireEvent.change(screen.getByLabelText('Game-plan notes'), {target: {value: 'Unsaved'}});
    fireEvent.click(screen.getByText('Save coaching plan'));
    await waitFor(() => expect(screen.getByText('Save coaching plan')).not.toBeDisabled());
    expect(screen.getByLabelText('Game-plan notes')).toHaveValue('Unsaved');
    fireEvent.click(screen.getByText('Discard edits'));
    expect(screen.getByText('Check protection')).toBeInTheDocument();
});

test('stale plans block edits and regeneration requires replacement', async () => {
    const generate = jest.fn().mockResolvedValue(session);
    render(<CoachesNotes {...props} session={{...session, state: {...state, ydstogo: 15}}} onGenerate={generate}/>);
    expect(screen.getByText('Edit plan')).toBeDisabled();
    fireEvent.click(screen.getByText('Regenerate draft'));
    expect(generate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Replace with new draft'));
    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1));
});

test('assistant proposal stays in review until explicitly saved', async () => {
    const liveSession = {...session, coaching_plan: undefined, revision: 3};
    const save = jest.fn().mockResolvedValue(liveSession);
    const assistant = jest.fn().mockResolvedValue({
        reply: 'Here is a proposed plan for review.',
        plan: content,
        context_id: 'current-context',
        session_revision: liveSession.revision,
    });
    render(<CoachesNotes {...props} session={liveSession} onAssistant={assistant} onSave={save}/>);
    fireEvent.change(screen.getByLabelText('Message the session assistant'), {target: {value: 'Draft a plan'}});
    fireEvent.click(screen.getByText('Send message'));
    await waitFor(() => expect(screen.getByText(/Assistant proposal/)).toBeInTheDocument());
    expect(await screen.findByText('Here is a proposed plan for review.')).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
    expect(liveSession.coaching_plan).toBeUndefined();
    fireEvent.change(screen.getByLabelText('Game-plan notes'), {target: {value: 'Reviewed by coach'}});
    fireEvent.click(screen.getByText('Save coaching plan'));
    await waitFor(() => expect(save).toHaveBeenCalledWith('current-context', expect.objectContaining({notes: 'Reviewed by coach'}), 'local_assistant'));
});

test('shows game context and retains response snapshot without sending metadata as history', async () => {
    const onAssistant = jest.fn().mockResolvedValue({reply: 'Situation\n\nProtect the lead.', plan: null, session_revision: 3,
        situation_brief: {score: 'KC 21 – BUF 17', clock: 'Q4 · 2:00', down_distance: 'Down 3 · 2 yards to go', field_position: 'Own 40', timeouts: 'Offense 2 · Defense 1', objective: 'clock'}});
    render(<CoachesNotes {...props} session={{...session, revision: 3}} onAssistant={onAssistant}/>);
    expect(screen.getByRole('region', {name: 'Situation used by assistant'})).toHaveTextContent('1 & 10');
    fireEvent.change(screen.getByLabelText('Message the session assistant'), {target: {value: 'Explain'}});
    fireEvent.click(screen.getByText('Send message'));
    expect(await screen.findByText(/KC 21 – BUF 17/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Message the session assistant'), {target: {value: 'Why?'}});
    fireEvent.click(screen.getByText('Send message'));
    await waitFor(() => expect(onAssistant).toHaveBeenCalledTimes(2));
    expect(onAssistant.mock.calls[1][1][1]).toEqual({role: 'assistant', content: 'Situation\n\nProtect the lead.'});
});


test('rules draft preserves source and stays unsaved until coach approval', async () => {
    const liveSession = {...session, coaching_plan: undefined, revision: 3};
    const save = jest.fn().mockResolvedValue(liveSession);
    const assistant = jest.fn().mockResolvedValue({reply: 'Prepared a rules-based draft.', plan: content,
        context_id: 'rules-context', session_revision: 3, provider: 'coaching_rules', proposal_source: 'coaching_rules'});
    render(<CoachesNotes {...props} session={liveSession} onAssistant={assistant} onSave={save}/>);
    fireEvent.change(screen.getByLabelText('Message the session assistant'), {target: {value: 'Draft three opening calls'}});
    fireEvent.click(screen.getByText('Send message'));
    expect(await screen.findByText('Coaching rules · saved facts and playbook')).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Save coaching plan'));
    await waitFor(() => expect(save).toHaveBeenCalledWith('rules-context', content, 'coaching_rules'));
});


test('Gemini analysis is labeled separately and included in follow-up history', async () => {
    const assistant = jest.fn().mockResolvedValue({reply: 'Saved facts: tied game.',
        analysis: 'Consider protection before selecting the passing concept.', provider: 'gemini', plan: null, session_revision: 3});
    render(<CoachesNotes {...props} session={{...session, revision: 3}} onAssistant={assistant}/>);
    fireEvent.change(screen.getByLabelText('Message the session assistant'), {target: {value: 'Explain the options'}});
    fireEvent.click(screen.getByText('Send message'));
    expect(await screen.findByText('Gemini coaching assistant')).toBeInTheDocument();
    expect(screen.getByText('Gemini analysis · review against the saved facts')).toBeInTheDocument();
    expect(screen.getByText('Saved facts: tied game.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Message the session assistant'), {target: {value: 'Why that option?'}});
    fireEvent.click(screen.getByText('Send message'));
    await waitFor(() => expect(assistant).toHaveBeenCalledTimes(2));
    expect(assistant.mock.calls[1][1][1].content).toContain('Consider protection');
    expect(assistant.mock.calls[1][1][1]).not.toHaveProperty('provider');
});


test('Gemini failure displays explicit fallback and keeps a reviewable draft', async () => {
    const assistant = jest.fn().mockResolvedValue({reply: 'Prepared a backend draft.', plan: content,
        session_revision: 3, context_id: 'fallback', provider: 'coaching_rules', proposal_source: 'coaching_rules',
        provider_warning: 'Gemini timed out.', analysis: null});
    const save = jest.fn();
    render(<CoachesNotes {...props} session={{...session, coaching_plan: undefined, revision: 3}} onAssistant={assistant} onSave={save}/>);
    fireEvent.change(screen.getByLabelText('Message the session assistant'), {target: {value: 'Draft a plan'}});
    fireEvent.click(screen.getByText('Send message'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Gemini analysis unavailable');
    expect(screen.getByText('Save coaching plan')).toBeInTheDocument();
    expect(screen.queryByText('Gemini coaching assistant')).not.toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
});

test('coverage evidence stays separate from Gemini analysis', async () => {
    const assistant = jest.fn().mockResolvedValue({reply: 'Fourth and 3 at Opponent 8.',
        analysis: 'Compare a field goal with going for the conversion.', provider: 'gemini', plan: null,
        coverage_context: 'No current defensive coverage is recorded. Historical sample: 207 labeled dropbacks.', session_revision: 3});
    render(<CoachesNotes {...props} session={{...session, revision: 3}} onAssistant={assistant}/>);
    fireEvent.change(screen.getByLabelText('Message the session assistant'), {target: {value: 'If we gain 12 yards?'}});
    fireEvent.click(screen.getByText('Send message'));
    expect(await screen.findByText('Coverage evidence · historical versus observed')).toBeInTheDocument();
    expect(screen.getByText(/Historical sample: 207/)).toBeInTheDocument();
    expect(screen.getByText('Compare a field goal with going for the conversion.')).toBeInTheDocument();
});

test('retains hypothetical context for follow-ups but drops it after a saved revision changes', async () => {
    const scenario = {session_id: 'one', revision: 3, outcome: {kind: 'gain', yards: 12, elapsed_seconds: 0}};
    const assistant = jest.fn().mockResolvedValue({reply: 'Fourth and three.', plan: null, session_revision: 3, scenario,
        discussion_scenario: {kind: 'hypothetical', situation: {down_distance: 'Down 4 · 3 yards to go', field_position: 'Opponent 8', clock: 'Q2 · 8:00'}}});
    const {rerender} = render(<CoachesNotes {...props} session={{...session, revision: 3}} onAssistant={assistant}/>);
    const send = text => {
        fireEvent.change(screen.getByLabelText('Message the session assistant'), {target: {value: text}});
        fireEvent.click(screen.getByText('Send message'));
    };
    send('If we gain 12 yards?');
    expect(await screen.findByText('Hypothetical · saved game unchanged')).toBeInTheDocument();
    expect(screen.getByText(/Down 4 · 3 yards to go/)).toHaveTextContent('Opponent 8');
    send('Why go for it?');
    await waitFor(() => expect(assistant).toHaveBeenCalledTimes(2));
    expect(assistant.mock.calls[1][2]).toEqual(scenario);
    await waitFor(() => expect(screen.getByLabelText('Message the session assistant')).toHaveValue(''));
    rerender(<CoachesNotes {...props} session={{...session, revision: 4}} onAssistant={assistant}/>);
    send('Does that mean you recommend going for it?');
    await waitFor(() => expect(assistant).toHaveBeenCalledTimes(3));
    expect(assistant.mock.calls[2][2]).toBeNull();
});
