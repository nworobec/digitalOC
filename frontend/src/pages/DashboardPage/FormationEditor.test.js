import React from 'react';
import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import FormationEditor from './FormationEditor';
import {anchoredRoute, defaultPositions, clampPosition} from '../PreviewPage/formationPositions';
const play = {id: 'mesh', name: 'Mesh sit'};

test('move two players, save positions, and keep route landmarks fixed', async () => {
    const onSave = jest.fn().mockResolvedValue({id: 'saved'});
    render(<FormationEditor play={play} onSave={onSave} onEditing={() => {}}/>);
    fireEvent.click(screen.getByText('Adjust player spots'));
    fireEvent.keyDown(screen.getByRole('button', {name: /^Left wide player/}), {key: 'ArrowRight'});
    fireEvent.change(screen.getByLabelText('Player to move'), {target: {value: '1'}});
    fireEvent.click(screen.getByLabelText('Move selected player back'));
    expect(screen.getByText('2 adjusted spots')).toBeInTheDocument();
    const route = document.querySelector('path[d="M78 202V142L440 142"]');
    expect(route).not.toBeNull();
    fireEvent.click(screen.getByText('Save alignment'));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][0][0]).toEqual([78, 202]);
    expect(onSave.mock.calls[0][0][1]).toEqual([160, 207]);
});

test('cancel discards edits; resetting remains a draft until saved', () => {
    const positions = defaultPositions.map(point => [...point]); positions[0] = [96, 210];
    const onSave = jest.fn();
    render(<FormationEditor play={{...play, layout: {custom: true, positions}}} onSave={onSave} onEditing={() => {}}/>);
    fireEvent.click(screen.getByText('Adjust player spots'));
    fireEvent.click(screen.getByText('Reset to template'));
    expect(screen.getByText('0 adjusted spots')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Cancel adjustments'));
    expect(onSave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Adjust player spots'));
    expect(screen.getByRole('button', {name: /^Left wide player, x 96, y 210/})).toBeInTheDocument();
});

test('bounds and route starts preserve downfield geometry', () => {
    expect(clampPosition(-10, 150)).toEqual([20, 202]);
    expect(clampPosition(900, 500)).toEqual([600, 290]);
    const positions = defaultPositions.map(point => [...point]); positions[10] = [400, 280];
    expect(anchoredRoute('M366 266Q404 264 411 213L432 194', positions)).toBe('M400 280Q404 264 411 213L432 194');
});

test('football edits submit confirmed metadata and marker assignments', async () => {
    const onSave = jest.fn().mockResolvedValue({id: 'saved'});
    render(<FormationEditor play={play} onSave={onSave} onEditing={() => {}} meta={{personnel: {any: 'Any', '11': '11'}, formations: {any: 'Any', gun_trips: 'Gun trips'}}} preferences={{personnel: 'any', formation: 'any'}}/>);
    fireEvent.click(screen.getByText('Adjust player spots'));
    fireEvent.change(screen.getByLabelText('Type of change'), {target: {value: 'football'}});
    fireEvent.change(screen.getByLabelText('Confirmed formation'), {target: {value: 'gun_trips'}});
    fireEvent.change(screen.getByLabelText('Confirmed personnel'), {target: {value: '11'}});
    fireEvent.change(screen.getByLabelText('Route / progression'), {target: {value: 'Shallow cross'}});
    fireEvent.click(screen.getByText('Save alignment'));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][1].formation).toBe('gun_trips');
    expect(onSave.mock.calls[0][1].personnel).toBe('11');
    expect(onSave.mock.calls[0][1].assignments[0].route).toBe('Shallow cross');
});
