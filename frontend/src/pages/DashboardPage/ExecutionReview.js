import React, {useState} from 'react';
import {playerLabels} from '../PreviewPage/formationPositions';

export const emptyExecution = () => ({relationship: 'unknown', strength: 'unknown', motion: '', motion_verified: false, assignments_verified: false,
    assignments: playerLabels.map(role => ({role, route: '', blocking: ''}))});

export default function ExecutionReview({play, value, onChange}) {
    const [selected, setSelected] = useState(0);
    const planned = play.decision_context?.play_design;
    const change = (key, val) => onChange({...value, [key]: val});
    const assignment = value.assignments[selected];
    return <section className="oc-design-controls" aria-label="Planned versus executed review">
        <h3>Planned vs. Executed</h3>
        <p className="oc-inline-help">Compare execution against film or charting. Actual concept, personnel, and formation are entered above. Blank assignments remain unknown; use N/A only when the assignment does not apply.</p>
        {planned ? <details><summary>Recorded plan · design version {planned.version}</summary><p>{planned.definition.personnel} personnel · {planned.definition.formation} · Strength: {planned.definition.strength}</p><p>Motion: {planned.definition.motion || 'Not specified'}</p><ul>{planned.definition.assignments.map((item, index) => <li key={index}>{item.role}: route {item.route || 'unknown'}; blocking {item.blocking || 'unknown'}</li>)}</ul></details> : <p>No planned design snapshot was recorded. You can still label execution from evidence.</p>}
        <div className="oc-review-grid">
            <label>Execution compared with plan<select value={value.relationship} onChange={e => change('relationship', e.target.value)}>{[['unknown', 'Unknown'], ['as_planned', 'Ran as planned'], ['audible', 'Audibled to another call'], ['modified', 'Changed alignment or assignments'], ['no_plan', 'No recorded design']].map(([id, title]) => <option key={id} value={id} disabled={(id === 'as_planned' && !planned) || (id === 'no_plan' && !!planned)}>{title}</option>)}</select></label>
            <label>Executed strength<select value={value.strength} onChange={e => change('strength', e.target.value)}>{['unknown', 'left', 'right', 'balanced'].map(item => <option key={item}>{item}</option>)}</select></label>
            <label>Executed motion<input maxLength={500} value={value.motion} placeholder="Describe motion, or No motion" onChange={e => change('motion', e.target.value)}/></label>
        </div>
        <label>Execution player<select value={selected} onChange={e => setSelected(Number(e.target.value))}>{playerLabels.map((role, index) => <option key={role} value={index}>{index + 1}. {role}</option>)}</select></label>
        <div className="oc-review-grid">{[['role', 'Executed player role'], ['route', 'Executed route / progression'], ['blocking', 'Executed blocking assignment']].map(([key, title]) => <label key={key}>{title}<input maxLength={key === 'role' ? 100 : 500} value={assignment[key]} onChange={e => change('assignments', value.assignments.map((row, index) => index === selected ? {...row, [key]: e.target.value} : row))}/></label>)}</div>
        <label className="oc-review-checkbox"><input type="checkbox" checked={value.motion_verified} onChange={e => change('motion_verified', e.target.checked)}/>I verified executed motion against the evidence</label>
        <label className="oc-review-checkbox"><input type="checkbox" checked={value.assignments_verified} onChange={e => change('assignments_verified', e.target.checked)}/>I verified all 11 player assignments against the evidence</label>
        <p className="oc-inline-help">Audibles and modifications require an explanation in review notes. Choosing Ran as planned does not copy or verify labels automatically.</p>
    </section>;
}
