import React, {useState} from 'react';
import {dashboardRequest} from './api';

export default function DatasetReadiness() {
    const [report, setReport] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [trainThrough, setTrainThrough] = useState('');
    const [validationThrough, setValidationThrough] = useState('');
    const run = async download => {
        setBusy(true); setError('');
        try {
            const query = new URLSearchParams();
            if (trainThrough || validationThrough) {query.set('train_through', trainThrough); query.set('validation_through', validationThrough);}
            if (download) query.set('download', '1');
            const result = await dashboardRequest(`/api/data/dataset?${query}`);
            setReport(result);
            if (download) {
                const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'}));
                const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${result.dataset_id}.json`;
                document.body.appendChild(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
            }
        } catch (failure) {setError(failure.message);}
        finally {setBusy(false);}
    };
    const changeCutoff = setter => event => {setter(event.target.value); setReport(null);};
    return <section className="oc-panel oc-dataset-readiness" aria-label="Training dataset validation">
        <h2>Prepare the concept training dataset</h2>
        <p className="oc-inline-help">Validate reviewed records across all saved games. Separate games by date, quarantine duplicates, and inspect concept support before training. These actions do not train or replace a model.</p>
        <div className="oc-review-grid oc-situation-panel"><label>Train through (optional)<input disabled={busy} type="date" value={trainThrough} onChange={changeCutoff(setTrainThrough)}/></label><label>Validation through (optional)<input disabled={busy} type="date" value={validationThrough} onChange={changeCutoff(setValidationThrough)}/></label></div>
        <p className="oc-inline-help">Leave both dates blank for automatic 60/20/20 date groups. Otherwise supply both: training ends on the first date, validation on the second, and testing uses later games. A single game or date never crosses splits.</p>
        <div className="oc-button-row"><button className="oc-primary" disabled={busy} onClick={() => run(false)}>Validate training dataset</button><button className="oc-secondary" disabled={busy} onClick={() => run(true)}>Download dataset snapshot</button></div>
        {busy && <p role="status">Checking reviewed records…</p>}
        {error && <p className="oc-error" role="alert">{error}</p>}
        {report && <>
            <h3>{report.status === 'blocked' ? 'More data or review is needed' : 'Planning gates met for an experiment'}</h3>
            <p>{report.summary.included_plays} included · {report.summary.excluded_plays} excluded · {report.summary.unique_games} games · {report.summary.duplicate_source_groups} duplicate source groups</p>
            <p>Train: {report.summary.splits.train || 0} · Validation: {report.summary.splits.validation || 0} · Test: {report.summary.splits.test || 0} · Unassigned: {report.summary.splits.unassigned || 0}</p>
            <ul>{report.training_blockers.map(reason => <li key={reason}>{reason}</li>)}</ul>
            <p className="oc-inline-help">Planning minimums per concept: 100 training plays / 3 games, 20 validation plays / 2 games, 20 test plays / 2 games. At least two concepts must meet these checks. These minimums do not establish predictive quality.</p>
            {report.design_readiness && <section><h3>Execution-label readiness</h3><p>{report.design_readiness.verified_eligible_plays} verified eligible plays · {report.design_readiness.status.replace(/_/g, ' ')}</p><p className="oc-inline-help">{report.design_readiness.scope} Each concept/formation group uses the same per-split planning minimums shown above; at least two groups must meet them.</p><ul>{Object.entries(report.design_readiness.missing_labels).map(([reason, count]) => <li key={reason}>{reason}: {count}</li>)}</ul>
                {!report.design_readiness.support.length ? <p>No verified concept/formation groups yet. Review excluded records and complete execution labels.</p> : <div className="oc-audit-table"><table><thead><tr><th>Concept / formation</th><th>Train plays / games</th><th>Validation plays / games</th><th>Test plays / games</th></tr></thead><tbody>{report.design_readiness.support.map(item => <tr key={`${item.concept_id}:${item.formation}`}><td>{item.concept_id} / {item.formation}</td>{['train', 'validation', 'test'].map(split => <td key={split}>{item.rows[split]} / {item.games[split]}</td>)}</tr>)}</tbody></table></div>}
            </section>}
            <details><summary>Concept support by split</summary><div className="oc-audit-table"><table><thead><tr><th>Concept</th><th>Train plays / games</th><th>Validation plays / games</th><th>Test plays / games</th></tr></thead><tbody>{report.concept_support.map(item => <tr key={item.concept_id}><td>{item.concept_id}</td>{['train', 'validation', 'test'].map(split => <td key={split}>{item.rows[split]} / {item.games[split]}</td>)}</tr>)}</tbody></table></div></details>
            <details><summary>Excluded records · {report.exclusions.length}</summary>{report.exclusions.map(item => <p key={`${item.session_id}:${item.recorded_play_id}`}><strong>Session {item.session_id.slice(0, 8)} · play {item.recorded_play_id.slice(0, 8)}</strong><br/>{item.source_game_id || 'No source game'} / {item.source_play_id || 'No source play ID'}: {item.blockers.join('; ')}</p>)}</details>
            <p className="oc-inline-help">{report.dataset_id} · Train cutoff: {report.config.train_through || 'unassigned'} · Validation cutoff: {report.config.validation_through || 'unassigned'}</p>
            <details><summary>Feature and target boundaries</summary><p>Features: {report.config.features.join(', ')}. The concept is supplied separately as the action being evaluated. Target: verified yards gained.</p><ul>{report.limitations.map(item => <li key={item}>{item}</li>)}</ul></details>
        </>}
    </section>;
}
