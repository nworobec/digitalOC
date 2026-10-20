import React from 'react';
import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import DataReview, {initialReview} from './DataReview';
import {dashboardRequest, downloadPlayLog} from './api';
jest.mock('./api', () => ({dashboardRequest: jest.fn(), downloadPlayLog: jest.fn()}));
const row = {play_id: 'p1', original: {id: 'p1', name: 'Mesh', drive: 1, call_id: 'mesh', outcome: {kind: 'gain', yards: 4}, decision_context: {preferences: {personnel: '11', formation: 'gun_trips'}}}, latest_review: null,
    readiness: {yardage_candidate: false, defensive_label_candidate: false, yardage_blockers: ['Latest review is not approved'], defensive_label_blockers: ['Observed coverage is unknown'], epa_blockers: ['EPA unavailable']}};
const meta = {personnel: {any: 'Any', '11': '11 personnel'}, formations: {any: 'Any', gun_trips: 'Gun trips'}, coverages: ['UNKNOWN', 'MAN']};
beforeEach(() => {jest.clearAllMocks(); dashboardRequest.mockResolvedValue({records: [row]}); downloadPlayLog.mockResolvedValue();});
test('planned inputs never become verified labels by default', () => {
    expect(initialReview(row)).toMatchObject({actual_call_id: 'unknown', actual_personnel: 'unknown', actual_formation: 'unknown', outcome_verified: false});
});
test('review form submits explicit labels and exports the selected session', async () => {
    const onSave = jest.fn();
    render(<DataReview session={{id: 's1', revision: 1}} calls={[{id: 'mesh', name: 'Mesh'}]} meta={meta} onSave={onSave}/>);
    await screen.findByLabelText('Reviewer (self-reported)');
    fireEvent.change(screen.getByLabelText('Reviewer (self-reported)'), {target: {value: 'Coach'}});
    fireEvent.change(screen.getByLabelText('Actual concept'), {target: {value: 'mesh'}});
    fireEvent.click(screen.getByText('Save review'));
    expect(onSave).toHaveBeenCalledWith('p1', expect.objectContaining({reviewer: 'Coach', actual_call_id: 'mesh', status: 'draft', outcome_verified: false}));
    fireEvent.click(screen.getByText('Export CSV'));
    await waitFor(() => expect(downloadPlayLog).toHaveBeenCalledWith('s1', 'csv'));
    expect(screen.getByText('Latest review is not approved')).toBeInTheDocument();
});
test('empty and failed review queues are visible', async () => {
    dashboardRequest.mockRejectedValue(new Error('Backend unavailable'));
    render(<DataReview session={{id: 's2'}} calls={[]} meta={meta} onSave={() => {}}/>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable');
    expect(screen.queryByText('Save review')).not.toBeInTheDocument();
});

test('execution annotations remain unknown until explicitly entered', async () => {
    const onSave = jest.fn();
    render(<DataReview session={{id: 's3', revision: 1}} calls={[{id: 'mesh', name: 'Mesh'}]} meta={meta} onSave={onSave}/>);
    await screen.findByLabelText('Execution compared with plan');
    expect(screen.getByLabelText('Executed motion')).toHaveValue('');
    expect(screen.getByLabelText('I verified all 11 player assignments against the evidence')).not.toBeChecked();
    fireEvent.change(screen.getByLabelText('Execution compared with plan'), {target: {value: 'no_plan'}});
    fireEvent.change(screen.getByLabelText('Executed motion'), {target: {value: 'No motion'}});
    fireEvent.click(screen.getByText('Save review'));
    expect(onSave).toHaveBeenCalledWith('p1', expect.objectContaining({execution: expect.objectContaining({relationship: 'no_plan', motion: 'No motion', motion_verified: false, assignments_verified: false})}));
});
