import React from 'react';
import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import HistoricalLabeling from './HistoricalLabeling';
import {initialReview} from './DataReview';
import {dashboardRequest} from './api';
jest.mock('./api', () => ({dashboardRequest: jest.fn()}));
test('browse, select, and stage real IDs without assigning concepts', async () => {
    dashboardRequest.mockResolvedValueOnce({games: [{game_id: '2024_01_KC_BUF', game_date: '2024-09-08', plays: 1}]})
        .mockResolvedValueOnce({total: 1, page_size: 20, plays: [{play_id: '83', action: 'pass', before: {down: 1, ydstogo: 10}, outcome: {yards: 4}, source: {description: 'Source play', raw_labels: {route: 'SCREEN'}}}]});
    const onImport = jest.fn();
    render(<HistoricalLabeling onImport={onImport}/>);
    fireEvent.click(screen.getByText('Browse source games'));
    await screen.findByLabelText('Source game');
    fireEvent.change(screen.getByLabelText('Source game'), {target: {value: '2024_01_KC_BUF'}});
    await screen.findByText('Source play');
    fireEvent.click(screen.getByText('Select this page'));
    fireEvent.click(screen.getByText('Stage 1 plays for review'));
    await waitFor(() => expect(onImport).toHaveBeenCalledWith('2024_01_KC_BUF', ['83']));
    expect(screen.getByText(/Full concept: unlabeled/)).toBeInTheDocument();
});
test('historical review prefills source identity, never concept or verification', () => {
    const review = initialReview({original: {outcome: {kind: 'gain', yards: 4}, historical_source: {game_id: 'G', play_id: '83', game_date: '2024-09-08', penalty_flag: 0}}});
    expect(review).toMatchObject({game_id: 'G', source_play_id: '83', source_type: 'real_game', penalty_status: 'none', actual_call_id: 'unknown', source_reference: '', before_state_verified: false, outcome_verified: false});
});
