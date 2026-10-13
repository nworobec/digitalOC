import React from 'react';
import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import {useLocation} from 'react-router-dom';
import Result from './result';
import {fetchSuggestedPlay} from '../SituationPage/situation';

jest.mock('react-router-dom', () => ({useLocation: jest.fn(), useNavigate: () => jest.fn()}), {virtual: true});
jest.mock('../SituationPage/situation', () => ({
    calculateGameSeconds: async () => 2100,
    calculateHalfSeconds: async () => 300,
    calculateQtrSeconds: async () => 300,
    fetchSuggestedPlay: jest.fn(),
    normalizeSuggestedPlays: data => data.plays,
}));

const response = {play_type: 'run', plays: [{play_type: 'run', expected_yards: '4', play_data: {}}]};

beforeEach(() => {
    jest.clearAllMocks();
    useLocation.mockReturnValue({state: {
        offenseTeam: 'KC', defenseTeam: 'BUF', offensePoints: '7', defensePoints: '7',
        ownOppMidfield: 'opp', ydLine50: '45', ydLine100: 45,
        down: '2', ydsToGo: '6', quarter: '2', minutes: '5', seconds: '0',
        offenseTimeouts: '3', defenseTimeouts: '3', suggestedPlays: response.plays,
    }});
    fetchSuggestedPlay.mockResolvedValue(response);
});

test('successful recordings advance the baseline and refresh leaves history unchanged', async () => {
    render(<Result />);
    fireEvent.change(screen.getByDisplayValue('45'), {target: {value: '40'}});
    fireEvent.click(screen.getByText('Record Play & Update'));
    await waitFor(() => expect(screen.getByText('Recorded plays this drive: 1')).toBeInTheDocument());
    fireEvent.change(screen.getByDisplayValue('40'), {target: {value: '37'}});
    fireEvent.click(screen.getByText('Record Play & Update'));
    await waitFor(() => expect(screen.getByText('Recorded plays this drive: 2')).toBeInTheDocument());
    expect(fetchSuggestedPlay.mock.calls[1][0].play_history.map(play => play.yards_gained)).toEqual([5, 3]);
    fireEvent.click(screen.getByText('Refresh Suggestions'));
    await waitFor(() => expect(fetchSuggestedPlay).toHaveBeenCalledTimes(3));
    expect(fetchSuggestedPlay.mock.calls[2][0].play_history).toHaveLength(2);
});

test('a failed request and retry do not commit duplicate history', async () => {
    const alert = jest.spyOn(window, 'alert').mockImplementation(() => {});
    const error = jest.spyOn(console, 'error').mockImplementation(() => {});
    fetchSuggestedPlay.mockRejectedValueOnce(new Error('Temporary failure'));
    render(<Result />);
    fireEvent.change(screen.getByDisplayValue('45'), {target: {value: '40'}});
    fireEvent.click(screen.getByText('Record Play & Update'));
    await waitFor(() => expect(alert).toHaveBeenCalled());
    expect(screen.getByText('Recorded plays this drive: 0')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Record Play & Update'));
    await waitFor(() => expect(screen.getByText('Recorded plays this drive: 1')).toBeInTheDocument());
    expect(fetchSuggestedPlay.mock.calls[1][0].play_history).toEqual([{play_type: 'run', yards_gained: 5}]);
    alert.mockRestore();
    error.mockRestore();
});
