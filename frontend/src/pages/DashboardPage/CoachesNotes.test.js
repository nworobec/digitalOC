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
