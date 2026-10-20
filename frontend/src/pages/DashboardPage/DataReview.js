import React, {useEffect, useState} from 'react';
import {dashboardRequest, downloadPlayLog} from './api';
import './dataReview.css';
import DatasetReadiness from './DatasetReadiness';
import HistoricalLabeling from './HistoricalLabeling';
import ExecutionReview, {emptyExecution} from './ExecutionReview';

export function initialReview(row) {
    const original = row.original;
    const source = original.historical_source;
    const defaults = {execution: emptyExecution(), status: 'draft', reviewer: '', source_type: source ? 'real_game' : 'unknown', source_reference: '', game_id: source?.game_id || '', game_date: source?.game_date || '', source_play_id: source?.play_id || '',
        actual_call_id: 'unknown', actual_personnel: 'unknown', actual_formation: 'unknown', observed_coverage: 'UNKNOWN',
        actual_kind: original.outcome.kind, actual_yards: original.outcome.yards, penalty_status: source?.penalty_flag === 0 ? 'none' : 'unknown', outcome_verified: false, before_state_verified: false, notes: ''};
    return Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, row.latest_review?.[key] ?? value]));
}

export default function DataReview({session, calls, meta, busy, onSave, onImport}) {
    const [audit, setAudit] = useState(null);
    const [auditing, setAuditing] = useState(false);
    const [error, setError] = useState('');
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(false);
    const [selected, setSelected] = useState('');
    const [review, setReview] = useState(null);
    const [exporting, setExporting] = useState(false);
    const row = rows.find(item => item.play_id === selected);
    useEffect(() => {
        const controller = new AbortController();
        setRows([]); setError(''); setAudit(null);
        if (!session) return () => controller.abort();
        setLoading(true);
        dashboardRequest(`/api/sessions/${session.id}/review`, {signal: controller.signal})
            .then(result => {if (!controller.signal.aborted) {setRows(result.records); setSelected(value => result.records.some(item => item.play_id === value) ? value : result.records[0]?.play_id || '');}})
            .catch(failure => {if (failure.name !== 'AbortError') setError(failure.message);})
            .finally(() => {if (!controller.signal.aborted) setLoading(false);});
        return () => controller.abort();
    }, [session]);
    useEffect(() => {setReview(row ? initialReview(row) : null);}, [row]);
    const change = (key, value) => setReview(previous => ({...previous, [key]: value}));
    const runAudit = async () => {
        setAuditing(true); setError('');
        try {setAudit(await dashboardRequest('/api/data/audit'));}
        catch (failure) {setError(failure.message);}
        finally {setAuditing(false);}
    };
    const download = async format => {
        setExporting(true); setError('');
        try {await downloadPlayLog(session.id, format);}
        catch (failure) {setError(failure.message);}
        finally {setExporting(false);}
    };
    return <section className="oc-data-review">
        <HistoricalLabeling onImport={onImport} busy={busy}/>
        <section className="oc-panel">
            <div className="oc-section-title"><h2>Data readiness</h2><button className="oc-secondary" disabled={auditing} onClick={runAudit}>{auditing ? 'Scanning local data…' : 'Run data audit'}</button></div>
            <p className="oc-inline-help">Audit raw source files and recorded plays. Populated labels are not proof of accuracy; route labels are not full play concepts.</p>
            {error && <p className="oc-error" role="alert">{error}</p>}
            {auditing && <p role="status">The first scan can take a moment. Subsequent scans reuse unchanged file results.</p>}
            {audit && <>
                <p className="oc-inline-help">Historical audit: {audit.historical.status} · {new Date(audit.historical.generated_at).toLocaleString()}</p>
                <div className="oc-audit-metrics">
                    <p><strong>{audit.historical.summary.pbp_rows.toLocaleString()}</strong> raw play-by-play rows</p>
                    <p><strong>{audit.historical.summary.recognized_concept_label_cells.toLocaleString()}</strong> populated recognized concept-label cells</p>
                    <p><strong>{audit.historical.join.matched_unique_keys.toLocaleString()}</strong> matched PBP / participation keys</p>
                    <p><strong>{audit.recorded.recorded_plays}</strong> recorded plays across saved sessions</p>
                    <p><strong>{audit.recorded.yardage_candidates}</strong> reviewed yardage candidates</p>
                    <p><strong>{audit.recorded.epa_candidates}</strong> recorded plays with verified EPA</p>
                </div>
                <p className="oc-inline-help">Duplicate extra rows: PBP {audit.historical.keys.pbp.duplicate_extra_rows}, participation {audit.historical.keys.participation.duplicate_extra_rows}. PBP keys without participation: {audit.historical.join.pbp_without_participation}.</p>
                {audit.historical.missing_expected_files.length > 0 && <p className="oc-status-panel">Missing expected sources: {audit.historical.missing_expected_files.join(', ')}</p>}
                {audit.historical.errors.map(item => <p key={item.file} className="oc-error">{item.file}: {item.error}</p>)}
                <details><summary>Field completeness and source details</summary><div className="oc-audit-table"><table><thead><tr><th>Source</th><th>Rows</th><th>Populated label fields</th></tr></thead><tbody>{audit.historical.files.filter(file => file.scope !== 'inventory_only').map(file => <tr key={file.file}><td>{file.file}</td><td>{file.rows?.toLocaleString()}</td><td>{file.available_label_columns.map(key => <div key={key}>{key}: {file.populated?.[key] ?? 0} / {file.rows ?? 0}</div>)}{file.available_label_columns.length === 0 && 'No recognized label columns'}{file.missing_key_rows > 0 && <div>Missing/invalid keys: {file.missing_key_rows}</div>}</td></tr>)}</tbody></table></div></details>
                <details><summary>Audit scope and limitations</summary><ul>{audit.historical.limitations.map(item => <li key={item}>{item}</li>)}</ul></details>
            </>}
        </section>
        <DatasetReadiness key={`${session?.id || 'none'}:${session?.revision || 0}`}/>
        <section className="oc-panel">
            <div className="oc-section-title"><h2>Review recorded plays</h2>{session && <div className="oc-button-row"><button className="oc-secondary" disabled={exporting || busy} onClick={() => download('json')}>Export JSON</button><button className="oc-secondary" disabled={exporting || busy} onClick={() => download('csv')}>Export CSV</button></div>}</div>
            <p className="oc-inline-help">Exports include all completed plays in the selected session, original inputs, review history, and target-specific blockers. No record is automatically approved or used for training. Use the same source game/play IDs across sessions so duplicate plays can be detected.</p>
            {!session ? <p>Create or select a session first.</p> : loading ? <p role="status">Loading review queue…</p> : rows.length === 0 ? <p>No completed plays to review. Record an actual result in the command center.</p> : <>
                <label className="oc-review-selector">Recorded play<select disabled={busy} value={selected} onChange={event => setSelected(event.target.value)}>{rows.map((item, index) => <option key={item.play_id} value={item.play_id}>{index + 1}. {item.original.name} · Drive {item.original.drive} · {item.latest_review?.status || 'unreviewed'}</option>)}</select></label>
                {row && review && <>
                    {row.original.historical_source && <div className="oc-status-panel"><strong>Historical source evidence · concept not yet verified</strong><p>{row.original.historical_source.description}</p><p>{row.original.historical_source.pbp_file} · {row.original.historical_source.game_id} / {row.original.historical_source.play_id}</p><p>Raw route: {row.original.historical_source.raw_labels.route || 'unknown'} · Formation: {row.original.historical_source.raw_labels.offense_formation || 'unknown'} · Personnel: {row.original.historical_source.raw_labels.offense_personnel || 'unknown'} · Coverage: {row.original.historical_source.raw_labels.defense_coverage_type || 'unknown'}</p><p>Supply film/charting evidence for the full concept. Route labels are not mapped automatically. Post-play state and elapsed time were not imported.</p></div>}
                    <div className="oc-status-panel">Original: {row.original.name} · {row.original.outcome.kind} · {row.original.outcome.yards} yards. Planned personnel: {row.original.decision_context?.preferences.personnel || 'not recorded'}; formation: {row.original.decision_context?.preferences.formation || 'not recorded'}.</div>
                    <details><summary>Original pre-snap game state</summary><pre className="oc-review-state">{JSON.stringify(row.original.before, null, 2)}</pre></details>
                    <p className="oc-inline-help">Confirm actual execution from your evidence. Planned settings are not automatically copied into verified labels. Corrections annotate this record; they do not replay the game or repair later states. Saving a review disables Undo for the latest play.</p>
                    <form className="oc-situation-panel" onSubmit={event => {event.preventDefault(); onSave(row.play_id, review);}}>
                        <fieldset disabled={busy}><div className="oc-review-grid">
                            <label>Review status<select value={review.status} onChange={event => change('status', event.target.value)}><option value="draft">Draft</option><option value="approved">Approved</option><option value="excluded">Excluded</option></select></label>
                            <label>Reviewer (self-reported)<input required maxLength="300" value={review.reviewer} onChange={event => change('reviewer', event.target.value)}/></label>
                            <label>Source type<select value={review.source_type} onChange={event => change('source_type', event.target.value)}>{['unknown', 'real_game', 'practice', 'test'].map(value => <option key={value} value={value}>{value.replace(/_/g, ' ')}</option>)}</select></label>
                            <label>Evidence reference<input maxLength="300" placeholder="Film timestamp or source play reference" value={review.source_reference} onChange={event => change('source_reference', event.target.value)}/></label>
                            <label>Source game ID<input maxLength="300" value={review.game_id} onChange={event => change('game_id', event.target.value)}/></label>
                            <label>Source play ID<input maxLength="300" placeholder="Stable play ID within the source game" value={review.source_play_id} onChange={event => change('source_play_id', event.target.value)}/></label>
                            <label>Game date<input type="date" value={review.game_date} onChange={event => change('game_date', event.target.value)}/></label>
                            <label>Actual concept<select value={review.actual_call_id} onChange={event => change('actual_call_id', event.target.value)}><option value="unknown">Unknown / outside catalog</option>{calls.map(call => <option key={call.id} value={call.id}>{call.name}</option>)}</select></label>
                            {[['actual_personnel', 'Actual personnel', meta.personnel], ['actual_formation', 'Actual formation', meta.formations]].map(([key, label, choices]) => <label key={key}>{label}<select value={review[key]} onChange={event => change(key, event.target.value)}><option value="unknown">Unknown / outside catalog</option>{Object.entries(choices).filter(([value]) => value !== 'any').map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label>)}
                            <label>Observed coverage<select value={review.observed_coverage} onChange={event => change('observed_coverage', event.target.value)}>{meta.coverages.map(value => <option key={value}>{value}</option>)}</select></label>
                            <label>Reviewed outcome<select value={review.actual_kind} onChange={event => change('actual_kind', event.target.value)}>{['gain', 'incomplete', 'sack', 'turnover', 'touchdown', 'safety'].map(value => <option key={value}>{value}</option>)}</select></label>
                            <label>Reviewed yards<input required type="number" min="-99" max="99" value={review.actual_yards} onChange={event => change('actual_yards', event.target.value === '' ? '' : Number(event.target.value))}/></label>
                            <label>Penalty status<select value={review.penalty_status} onChange={event => change('penalty_status', event.target.value)}>{['unknown', 'none', 'declined', 'accepted', 'offsetting'].map(value => <option key={value}>{value}</option>)}</select></label>
                        </div>
                        <ExecutionReview play={row.original} value={review.execution} onChange={value => change('execution', value)}/>
                        <label className="oc-review-checkbox"><input type="checkbox" checked={review.before_state_verified} onChange={event => change('before_state_verified', event.target.checked)}/>I checked the original pre-snap game state against the evidence</label>
                        <label className="oc-review-checkbox"><input type="checkbox" checked={review.outcome_verified} onChange={event => change('outcome_verified', event.target.checked)}/>I checked the outcome against the evidence</label>
                        <label>Review notes / correction or exclusion reason<textarea maxLength="2000" rows="3" value={review.notes} onChange={event => change('notes', event.target.value)}/></label>
                        <p className="oc-inline-help">Approval requires verified pre-snap state, identified execution, known penalty status, verified outcome, and game/source details. An approved practice/test record is still excluded from real-game training candidates.</p>
                        <button className="oc-primary" type="submit">Save review</button></fieldset>
                    </form>
                    <h3>Current saved readiness</h3><p>Yardage candidate: {row.readiness.yardage_candidate ? 'Yes' : 'No'} · Defensive-label candidate: {row.readiness.defensive_label_candidate ? 'Yes' : 'No'}</p>
                    <p>Verified design candidate: {row.readiness.design_candidate ? 'Yes' : 'No'}</p><ul>{(row.readiness.design_blockers || []).map(reason => <li key={reason}>{reason}</li>)}</ul>
                    <ul>{[...new Set([...row.readiness.yardage_blockers, ...row.readiness.defensive_label_blockers, ...row.readiness.epa_blockers])].map(reason => <li key={reason}>{reason}</li>)}</ul>
                    <details><summary>Review history · {row.original.reviews?.length || 0}</summary>{row.original.reviews?.map(item => <article key={item.review_number}><strong>#{item.review_number} · {item.status} · {item.reviewer}</strong><p>{item.reviewed_at} · {item.actual_call_id} · {item.actual_kind} · {item.actual_yards} yards</p><p>{item.notes || 'No notes'}</p></article>)}</details>
                </>}
            </>}
        </section>
    </section>;
}
