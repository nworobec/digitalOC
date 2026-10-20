import React, {useEffect, useState} from 'react';
import {PlayField} from '../PreviewPage/preview';
import {defaultPositions, playerLabels, clampPosition} from '../PreviewPage/formationPositions';

export default function FormationEditor({play, busy, onSave, onEditing, meta, preferences}) {
    const saved = play.layout?.positions || defaultPositions;
    const [editing, setEditing] = useState(false);
    const [positions, setPositions] = useState(saved);
    const [selected, setSelected] = useState(0);
    const [error, setError] = useState('');
    const [changeKind, setChangeKind] = useState('visual');
    const [design, setDesign] = useState(null);
    const initialDesign = () => play.design?.definition || {
        personnel: preferences?.personnel || 'any', formation: preferences?.formation || 'any',
        strength: 'unknown', motion: '',
        assignments: playerLabels.map(role => ({role, route: '', blocking: ''})),
    };
    const updateAssignment = (key, value) => setDesign({...design, assignments: design.assignments.map((row, index) => index === selected ? {...row, [key]: value} : row)});
    useEffect(() => () => onEditing(false), [onEditing]);
    const begin = () => {setDesign(JSON.parse(JSON.stringify(initialDesign()))); setChangeKind('visual'); setPositions(saved.map(point => [...point])); setEditing(true); onEditing(true); setError('');};
    const cancel = () => {setEditing(false); onEditing(false); setError('');};
    const move = (index, point) => setPositions(previous => previous.map((value, i) => i === index ? point : value));
    const nudge = (dx, dy) => move(selected, clampPosition(positions[selected][0] + dx, positions[selected][1] + dy));
    const changed = positions.filter((point, index) => point.some((value, coordinate) => value !== defaultPositions[index][coordinate])).length;
    const save = async () => {
        if (positions.some((point, index) => positions.slice(index + 1).some(other => Math.hypot(point[0] - other[0], point[1] - other[1]) < 18))) {
            setError('Separate overlapping player markers before saving.'); return;
        }
        setError('');
        const result = await onSave(positions, changeKind === 'football' ? design : undefined);
        if (result) cancel();
    };
    return <section className="oc-formation-editor" aria-label="Call alignment editor">
        <div className="oc-button-row oc-formation-toolbar"><strong>{editing ? `${changed} adjusted spots` : play.layout?.custom ? 'Custom alignment · saved for this game' : 'Template alignment'}</strong>
            {!editing && <button type="button" className="oc-primary oc-plan-launch oc-alignment-launch" disabled={busy} onClick={begin}>Adjust player spots</button>}
        </div>
        {play.design && <p className="oc-inline-help">Design version {play.design.version} · Coach-declared, awaiting execution review.</p>}
        {editing && <>
            {meta && <div className="oc-design-controls">
                <label>Type of change<select disabled={busy} value={changeKind} onChange={e => setChangeKind(e.target.value)}><option value="visual">Visual adjustment only</option><option value="football">Football design change</option></select></label>
                <p className="oc-inline-help">Visual adjustments change the sketch only. A football change saves a design version and applies the formation and personnel you confirm below to Coach’s Controls.</p>
                {changeKind === 'football' && <>
                    <div className="oc-design-grid">
                        {[['personnel', 'Confirmed personnel', meta.personnel], ['formation', 'Confirmed formation', meta.formations], ['strength', 'Formation strength', {unknown: 'Unknown', left: 'Left', right: 'Right', balanced: 'Balanced'}]].map(([key, label, choices]) => <label key={key}>{label}<select disabled={busy} value={design[key]} onChange={e => setDesign({...design, [key]: e.target.value})}>{Object.entries(choices).map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label>)}
                    </div>
                    <label>Motion instructions<input disabled={busy} maxLength={500} value={design.motion} onChange={e => setDesign({...design, motion: e.target.value})}/></label>
                    <p className="oc-inline-help">Confirm the formation yourself; marker positions do not establish a legal formation. Formation and personnel must fit this concept’s installed template. “Any” clears that coaching constraint.</p>
                </>}
            </div>}
            <p className="oc-inline-help">Drag a player, or select one and use the move buttons. Keyboard: Tab to a player, then arrow keys (Shift for larger moves). Save or cancel before changing calls.</p>
            <div className="oc-formation-tools"><label>Player to move<select disabled={busy} value={selected} onChange={event => setSelected(Number(event.target.value))}>{playerLabels.map((label, index) => <option key={label} value={index}>{label}</option>)}</select></label>
                <div className="oc-button-row">{[['Left', -5, 0], ['Right', 5, 0], ['Up', 0, -5], ['Back', 0, 5]].map(([label, dx, dy]) => <button key={label} className="oc-secondary" disabled={busy} onClick={() => nudge(dx, dy)} aria-label={`Move selected player ${label.toLowerCase()}`}>{label}</button>)}</div>
            </div>
        </>}
        {editing && changeKind === 'football' && design && <div className="oc-design-controls">
            <h4>Assignments · {playerLabels[selected]}</h4>
            <div className="oc-design-grid">{[['role', 'Player role', 100], ['route', 'Route / progression', 500], ['blocking', 'Blocking assignment', 500]].map(([key, label, max]) => <label key={key}>{label}<input disabled={busy} maxLength={max} value={design.assignments[selected][key]} onChange={e => updateAssignment(key, e.target.value)}/></label>)}</div>
            <p className="oc-inline-help">Select a marker to edit its assignments. Instructions are saved as coach notes; they do not redraw routes or verify execution.</p>
        </div>}
        <PlayField play={play} positions={editing ? positions : saved} onMove={editing && !busy ? move : undefined} selectedPlayer={selected} onSelectPlayer={setSelected}/>
        {editing && <><div className="oc-button-row"><button className="oc-primary" disabled={busy} onClick={save}>Save alignment</button><button className="oc-secondary" disabled={busy} onClick={cancel}>Cancel adjustments</button><button className="oc-text-button" disabled={busy} onClick={() => {setPositions(defaultPositions.map(point => [...point])); setError('');}}>Reset to template</button></div>{error && <p role="alert" className="oc-error">{error}</p>}</>}
        <p className="oc-inline-help">Routes stay attached at their starting points; other route landmarks stay fixed. This is a coaching sketch, not a formation-legality check. Confirmed football changes refresh formation/personnel rules and make existing game plans outdated. Route, blocking, and motion edits require coach review. Run/pass EPA does not account for this design.</p>
    </section>;
}
