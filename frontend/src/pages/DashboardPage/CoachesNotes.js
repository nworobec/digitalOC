import React, {useEffect, useState} from 'react';
import './coachesNotes.css';

const sameFields = (a, b) => Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(key => JSON.stringify(a[key]) === JSON.stringify(b[key]));

export default function CoachesNotes({session, calls, busy, onGenerate, onSave, onEditing}) {
    const plan = session?.coaching_plan;
    const [draft, setDraft] = useState(null);
    const [replace, setReplace] = useState(false);
    const [working, setWorking] = useState(false);
    const editing = draft !== null;
    useEffect(() => {onEditing(editing); return () => onEditing(false);}, [editing, onEditing]);
    useEffect(() => {
        if (!editing) return undefined;
        const prevent = event => {event.preventDefault(); event.returnValue = '';};
        window.addEventListener('beforeunload', prevent);
        return () => window.removeEventListener('beforeunload', prevent);
    }, [editing]);
    if (!session || session.mode === 'historical_review') return <section className="oc-panel"><h2>Coaches Notes</h2><p>Create or select a live game session in the command center to draft a game plan.</p></section>;
    const stale = plan && (!sameFields(plan.context.state, session.state) || !sameFields(plan.context.preferences, session.preferences) || !sameFields(plan.context.designs || {}, session.designs || {}));
    const content = draft || plan?.content;
    const evidence = plan?.evidence;
    const allowed = calls.filter(call => session.preferences.installed_call_ids.includes(call.id)
        && (session.state.action_filter === 'all' || call.type.toLowerCase() === session.state.action_filter)
        && (session.preferences.personnel === 'any' || call.personnel.includes(session.preferences.personnel))
        && (session.preferences.formation === 'any' || call.formations.includes(session.preferences.formation))
        && session.state.yardline_100 >= call.minimum_field_space);
    const change = (key, value) => setDraft({...draft, [key]: value});
    const rowChange = (key, index, field, value) => change(key, draft[key].map((row, i) => i === index ? {...row, [field]: value} : row));
    const generate = async () => {
        setWorking(true);
        try {if (await onGenerate()) {setDraft(null); setReplace(false);}} finally {setWorking(false);}
    };
    const save = async () => {
        setWorking(true);
        try {if (await onSave(plan.context_id, draft)) setDraft(null);} finally {setWorking(false);}
    };
    const disabled = busy || working;
    return <section className="oc-panel oc-coaches-notes">
        <div className="oc-panel-heading"><h2>Coaches Notes assistant</h2><span className="oc-tiny-badge">RULE-BASED DRAFT</span></div>
        <p>Build a starting plan from your saved situation, available calls, and historical opponent coverage. Review each call with your staff before using it.</p>
        <p className="oc-inline-help">Scripts are coaching templates, not predicted optimal sequences. Coverage history does not predict the next snap. Player strengths and availability require coach review.</p>
        {stale && <p role="status" className="oc-status-panel">The saved situation, playbook, or football design has changed. Your previous plan is preserved; regenerate it before editing for this situation.</p>}
        {!plan && <button className="oc-primary" disabled={disabled} onClick={generate}>Draft game plan</button>}
        {plan && <>
            <p className="oc-inline-help">{plan.edited_by_coach ? 'Coach-edited draft' : 'Generated draft'} · Saved {new Date(plan.updated_at).toLocaleString()}</p>
            <div className="oc-button-row">
                {!editing && <button className="oc-primary" disabled={disabled || stale} onClick={() => setDraft(JSON.parse(JSON.stringify(plan.content)))}>Edit plan</button>}
                {!editing && <button className="oc-secondary" disabled={disabled} onClick={() => setReplace(true)}>Regenerate draft</button>}
                {editing && <><button className="oc-primary" disabled={disabled || stale} onClick={save}>Save coaching plan</button><button className="oc-secondary" disabled={disabled} onClick={() => setDraft(null)}>Discard edits</button></>}
            </div>
            {replace && <div className="oc-status-panel"><p>Replace the saved plan and its edits with a new draft from the current situation?</p><button className="oc-secondary" disabled={disabled} onClick={() => setReplace(false)}>Keep saved plan</button> <button className="oc-primary" disabled={disabled} onClick={generate}>Replace with new draft</button></div>}
            {editing && <p role="status">Unsaved edits — save or discard before switching games or views.</p>}
            <fieldset disabled={disabled}>
                {editing ? <><label>Plan title<input maxLength={160} value={draft.title} onChange={e => change('title', e.target.value)}/></label><label>Game-plan notes<textarea rows={5} maxLength={6000} value={draft.notes} onChange={e => change('notes', e.target.value)}/></label></> : <><h3>{content.title}</h3><p className="oc-plan-text">{content.notes}</p></>}
                {[['opening_script', 'Opening script', ['purpose', 'watch']], ['counters', 'Conditional counters', ['condition', 'reason']]].map(([key, title, fields]) => <section key={key}>
                    <h3>{title}</h3>
                    {key === 'opening_script' && <p className="oc-inline-help">Review order for the current situation. Recheck eligibility after every snap; no calls are automatically queued.</p>}
                    {!content[key].length && <p>No entries. {allowed.length ? 'Edit the plan to add an eligible call.' : 'Update your available playbook or constraints to include calls.'}</p>}
                    {content[key].map((row, index) => <article className="oc-plan-entry" key={index}>
                        {editing ? <>
                            <label>{title} call {index + 1}<select value={row.call_id} onChange={e => rowChange(key, index, 'call_id', e.target.value)}>{!allowed.some(call => call.id === row.call_id) && <option value={row.call_id}>Unavailable: {row.call_id}</option>}{allowed.map(call => <option key={call.id} value={call.id}>{call.name}</option>)}</select></label>
                            {fields.map(field => <label key={field}>{field} {index + 1}<textarea maxLength={1200} value={row[field]} onChange={e => rowChange(key, index, field, e.target.value)}/></label>)}
                            <div className="oc-button-row"><button type="button" className="oc-secondary" disabled={index === 0} onClick={() => {const rows = [...draft[key]]; [rows[index - 1], rows[index]] = [rows[index], rows[index - 1]]; change(key, rows);}}>Move up</button><button type="button" className="oc-text-button" onClick={() => change(key, draft[key].filter((_, i) => i !== index))}>Remove entry</button></div>
                        </> : <><h4>{index + 1}. {calls.find(call => call.id === row.call_id)?.name || row.call_id}</h4>{fields.map(field => <p className="oc-plan-text" key={field}><strong>{field}: </strong>{row[field]}</p>)}</>}
                    </article>)}
                    {editing && <button type="button" className="oc-secondary" disabled={!allowed.length || content[key].length >= 15} onClick={() => change(key, [...draft[key], {call_id: allowed[0].id, ...Object.fromEntries(fields.map(field => [field, '']))}])}>Add {key === 'opening_script' ? 'script call' : 'counter'}</button>}
                </section>)}
            </fieldset>
            <section className="oc-plan-evidence"><h3>Evidence used for this draft</h3><p>Saved {plan.context.state.posteam} offense vs {plan.context.state.defteam}: down {plan.context.state.down}, {plan.context.state.ydstogo} yards to go. Personnel: {plan.context.preferences.personnel}; formation: {plan.context.preferences.formation}; anticipated coverage: {plan.context.preferences.anticipated_coverage} (coach input).</p>
                {evidence?.status === 'historical_frequencies' ? <><p>{evidence.source} · Seasons {evidence.seasons.join(', ')} · {evidence.sample_count} labeled dropbacks · Matched by {evidence.scope}.</p><ul>{evidence.distribution.map(item => <li key={item.coverage}>{item.coverage}: {(item.frequency * 100).toFixed(1)}% ({item.count} plays)</li>)}</ul><p>Coverage tags guide conditional alternatives; opening order uses situational coaching rules. Historical tendencies may differ from the opponent today.</p></> : <p>{evidence?.reason || 'Opponent coverage unavailable.'} This draft uses playbook and situation rules only.</p>}
                {Object.entries(plan.context.designs || {}).map(([id, design]) => <p key={id}>Coach-declared design: {calls.find(call => call.id === id)?.name || id} · Version {design.version} · {design.definition.formation} · {design.definition.personnel} personnel. Assignments, motion, and alignment require staff review; the template progression may need adjustment.</p>)}
                <p>Concept descriptions and counter links come from the starter playbook and need staff review. Free-text edits are coach notes, not verified opponent evidence.</p>
            </section>
        </>}
    </section>;
}
