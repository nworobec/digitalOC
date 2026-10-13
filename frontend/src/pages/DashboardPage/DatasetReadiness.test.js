import React from 'react';
import {render, screen, fireEvent} from '@testing-library/react';
import DatasetReadiness from './DatasetReadiness';
import {dashboardRequest} from './api';
jest.mock('./api', () => ({dashboardRequest: jest.fn()}));
const report = {status: 'blocked', dataset_id: 'concept-test', summary: {included_plays: 0, excluded_plays: 1, unique_games: 0, duplicate_source_groups: 0, splits: {}},
    config: {features: ['down'], train_through: null, validation_through: null}, concept_support: [], exclusions: [{session_id: 'session1', recorded_play_id: 'play1', source_game_id: 'GAME', source_play_id: '', blockers: ['missing_source_play_id']}],
    training_blockers: ['No eligible reviewed real-game records'], limitations: ['No model trained']};
beforeEach(() => jest.clearAllMocks());
test('shows blockers instead of claiming training is ready', async () => {
    dashboardRequest.mockResolvedValue(report);
    render(<DatasetReadiness/>);
    fireEvent.click(screen.getByText('Validate training dataset'));
    expect(await screen.findByText('More data or review is needed')).toBeInTheDocument();
    expect(screen.getByText('No eligible reviewed real-game records')).toBeInTheDocument();
    expect(screen.getByText(/missing_source_play_id/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Train through (optional)'), {target: {value: '2024-09-01'}});
    expect(screen.queryByText('More data or review is needed')).not.toBeInTheDocument();
});
test('passes explicit boundaries and shows validation failures', async () => {
    dashboardRequest.mockRejectedValue(new Error('Supply both cutoffs'));
    render(<DatasetReadiness/>);
    fireEvent.change(screen.getByLabelText('Train through (optional)'), {target: {value: '2024-09-01'}});
    fireEvent.click(screen.getByText('Validate training dataset'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Supply both cutoffs');
    expect(dashboardRequest.mock.calls[0][0]).toContain('train_through=2024-09-01');
});
