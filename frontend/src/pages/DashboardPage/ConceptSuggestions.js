import React from 'react';
import {PlayField} from '../PreviewPage/preview';

export default function ConceptSuggestions({fit, calls, selectedId, onSelect, disabled}) {
    if (!fit) return <p className="oc-inline-help">Save an active game situation to see its current shortlist.</p>;
    return <section aria-label="Situational fit suggestions">
        <p className="oc-inline-help">Provisional coaching rules select up to three compatible calls. These are not trained concept predictions. {fit.review_status}.</p>
        {fit.suggestions.length ? <div className="oc-play-cards oc-fit-cards">{fit.suggestions.map(item => {
            const call = calls.find(candidate => candidate.id === item.call_id);
            if (!call) return null;
            return <button disabled={disabled} key={call.id} className={`oc-play-card ${selectedId === call.id ? 'selected' : ''}`} onClick={() => onSelect(call.id)} aria-pressed={selectedId === call.id}>
                <span className={`oc-play-type ${call.type.toLowerCase()}`}>{call.type}</span><h3>{call.name}</h3>
                <PlayField play={call}/><p>{call.tag}</p>
                <strong className="oc-fit-label">SITUATIONAL FIT</strong>
                <ul>{item.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
                {item.cautions.map(caution => <p className="oc-fit-caution" key={caution}>{caution}</p>)}
            </button>;
        })}</div> : <div className="oc-status-panel">No compatible calls. Adjust your available playbook, personnel, formation, or action constraint and save again.</div>}
        {fit.excluded.length > 0 && <details className="oc-fit-exclusions"><summary>Why {fit.excluded.length} calls are excluded</summary>{fit.excluded.map(item => <p key={item.call_id}><strong>{item.name}:</strong> {item.reasons.join(' ')}</p>)}</details>}
        <p className="oc-inline-help">{fit.eligible_call_ids.length} eligible calls · top {fit.suggestions.length} shown · {fit.rule_version}. Browse the Playbook for other templates.</p>
    </section>;
}
