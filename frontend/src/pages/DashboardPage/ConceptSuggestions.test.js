import React from 'react';
import {render, screen, fireEvent} from '@testing-library/react';
import ConceptSuggestions from './ConceptSuggestions';
import {playDiagrams} from '../PreviewPage/playDiagrams';

const calls = [
    {id: 'mesh', name: 'Mesh sit', type: 'PASS', tag: '11 personnel', diagram_key: 'mesh'},
    {id: 'power', name: 'Power', type: 'RUN', tag: '21 personnel', diagram_key: 'power'},
];
const suggestion = (call_id, reason) => ({call_id, reasons: [reason], cautions: []});
const fit = {suggestions: [suggestion('mesh', 'Fits anticipated man coverage.')], excluded: [], eligible_call_ids: ['mesh'], rule_version: 'test', review_status: 'Coach review required'};

test('saved evaluation changes cards and diagrams, with no invented concept estimates', () => {
    const onSelect = jest.fn();
    const {rerender} = render(<ConceptSuggestions fit={fit} calls={calls} selectedId="mesh" onSelect={onSelect}/>);
    expect(screen.getByRole('button', {pressed: true})).toHaveTextContent('Mesh sit');
    const meshPaths = [...screen.getByRole('img').querySelectorAll('path')].map(path => path.getAttribute('d'));
    const next = {...fit, suggestions: [suggestion('power', 'Fits short yardage.')], eligible_call_ids: ['power']};
    rerender(<ConceptSuggestions fit={next} calls={calls} selectedId="mesh" onSelect={onSelect}/>);
    expect(screen.queryByText('Mesh sit')).not.toBeInTheDocument();
    expect(screen.getByText('Fits short yardage.')).toBeInTheDocument();
    const powerPaths = [...screen.getByRole('img').querySelectorAll('path')].map(path => path.getAttribute('d'));
    expect(powerPaths).not.toEqual(meshPaths);
    fireEvent.click(screen.getByRole('button', {pressed: false}));
    expect(onSelect).toHaveBeenCalledWith('power');
    expect(screen.queryByText(/expected EPA/i)).not.toBeInTheDocument();
});

test('empty shortlist explains constraints and keeps exclusions accessible', () => {
    render(<ConceptSuggestions fit={{...fit, suggestions: [], eligible_call_ids: [], excluded: [{call_id: 'mesh', name: 'Mesh sit', reasons: ['Not installed.']}]}} calls={calls} onSelect={() => {}}/>);
    expect(screen.getByText(/No compatible calls/)).toBeInTheDocument();
    expect(screen.getByText('Why 1 calls are excluded')).toBeInTheDocument();
    expect(screen.getByText(/Not installed/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

test('every starter concept has a distinct schematic', () => {
    expect(Object.keys(playDiagrams)).toHaveLength(12);
    expect(new Set(Object.values(playDiagrams).map(value => JSON.stringify(value))).size).toBe(12);
});
