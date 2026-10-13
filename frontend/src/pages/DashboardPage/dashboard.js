import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Icon, PlayField} from '../PreviewPage/preview';
import {dashboardRequest, mutation} from './api';
import ConceptSuggestions from './ConceptSuggestions';
import DataReview from './DataReview';
import FormationEditor from './FormationEditor';
import CoachesNotes from './CoachesNotes';
import '../PreviewPage/preview.css';
import './dashboard.css';

const storageKey = 'digitaloc.activeSession';
const ordinal = down => `${down}${['', 'st', 'nd', 'rd', 'th'][down] || ''}`;
const clock = seconds => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
const signed = (value, digits = 2) => `${value >= 0 ? '+' : ''}${Number(value).toFixed(digits)}`;
const field = state => state.yardline_100 > 50 ? `${state.posteam} ${100 - state.yardline_100}` : state.yardline_100 === 50 ? 'Midfield' : `${state.defteam} ${state.yardline_100}`;
const formState = state => ({...state, clock: clock(state.quarter_seconds_remaining)});
const logoFiles = require.context('../../logos', false, /\.png$/);
function TeamLogo({team}) {
    const file = `./${team === 'LA' ? 'LAR' : team}.png`;
    return logoFiles.keys().includes(file) ? <img src={logoFiles(file)} alt={team}/> : <span>{team}</span>;
}

export default function Dashboard() {
    const [view, setView] = useState('Command center');
    const [meta, setMeta] = useState(null);
    const [catalog, setCalls] = useState([]);
    const [sessions, setSessions] = useState([]);
    const [session, setSession] = useState(null);
    const [draft, setDraft] = useState(null);
    const [preferences, setPreferences] = useState(null);
    const [evaluation, setEvaluation] = useState(null);
    const [evaluationError, setEvaluationError] = useState('');
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [busy, setBusy] = useState(false);
    const [editingLayout, setEditingLayout] = useState(false);
    const [editingPlan, setEditingPlan] = useState(false);
    const blocked = busy || editingLayout || editingPlan;
    const calls = catalog.map(call => ({...call, layout: session?.layouts?.[call.id], design: session?.designs?.[call.id]}));
    const [loading, setLoading] = useState(true);
    const [selectedId, setSelectedId] = useState(null);
    const [filter, setFilter] = useState('ALL');
    const [record, setRecord] = useState(null);
    const lock = useRef(false);

    const acceptSession = useCallback(value => {
        setSession(value);
        setDraft(formState(value.state));
        setPreferences(value.preferences);
        setRecord(null);
        try { localStorage.setItem(storageKey, value.id); } catch (_) { /* Session still persists on the server. */ }
    }, []);

    const refreshList = async () => setSessions((await dashboardRequest('/api/sessions')).sessions);

    useEffect(() => {
        const controller = new AbortController();
        const options = {signal: controller.signal};
        (async () => {
            try {
                const [metadata, catalog, saved] = await Promise.all([
                    dashboardRequest('/api/meta', options), dashboardRequest('/api/playbook', options), dashboardRequest('/api/sessions', options),
                ]);
                if (controller.signal.aborted) return;
                setMeta(metadata); setCalls(catalog.plays); setSessions(saved.sessions);
                let remembered;
                try { remembered = localStorage.getItem(storageKey); } catch (_) { remembered = null; }
                const active = saved.sessions.find(item => item.id === remembered) || saved.sessions[0];
                if (active) {
                    const loaded = await dashboardRequest(`/api/sessions/${active.id}`, options);
                    if (!controller.signal.aborted) acceptSession(loaded);
                } else { setDraft(formState(metadata.defaults)); setPreferences(metadata.preference_defaults); }
            } catch (failure) {
                if (failure.name !== 'AbortError') setError(failure.message);
            } finally { if (!controller.signal.aborted) setLoading(false); }
        })();
        return () => controller.abort();
    }, [acceptSession]);

    useEffect(() => {
        if (!session) return undefined;
        const controller = new AbortController();
        setEvaluation(null); setEvaluationError('');
        dashboardRequest(`/api/sessions/${session.id}/evaluation`, {signal: controller.signal})
            .then(result => {if (!controller.signal.aborted) setEvaluation(result);})
            .catch(failure => {if (failure.name !== 'AbortError') setEvaluationError(failure.message);});
        return () => controller.abort();
    }, [session]);

    const task = async (work, message) => {
        if (lock.current) return;
        lock.current = true; setBusy(true); setError(''); setNotice('');
        try {
            const saved = await work();
            acceptSession(saved);
            setNotice(message);
            await refreshList();
            return saved;
        } catch (failure) {
            setError(failure.message);
            if (failure.status === 409 && session) {
                try { acceptSession(await dashboardRequest(`/api/sessions/${session.id}`)); }
                catch (_) { /* Keep the original conflict message. */ }
            }
        } finally { lock.current = false; setBusy(false); }
    };

    const saveSituation = event => {
        event.preventDefault();
        const command = event.nativeEvent.submitter?.value;
        const {clock: time, ...state} = draft;
        if (!/^\d{1,2}:[0-5]\d$/.test(time)) {setError('Use MM:SS for the quarter clock.'); return;}
        state.quarter_seconds_remaining = Number(time.split(':')[0]) * 60 + Number(time.split(':')[1]);
        const creating = !session || command === 'create';
        const path = creating ? '/api/sessions' : `/api/sessions/${session.id}${command === 'drive' ? '/drive' : ''}`;
        task(() => dashboardRequest(path, {method: creating || command === 'drive' ? 'POST' : 'PATCH',
            body: creating ? {state, preferences} : {...mutation(session), state, preferences}}),
        creating ? 'Game session created.' : command === 'drive' ? 'New drive started. Previous plays remain in the log.' : 'Situation saved. Estimates refreshed.');
    };

    const queueCall = call => task(() => dashboardRequest(`/api/sessions/${session.id}/queue`, {
        method: 'POST', body: {...mutation(session), call_id: call.id, ...(presentation ? {presentation} : {})},
    }), `${call.name} added to the call sheet. It has not been recorded as a completed play.`);

    const startRecord = (call, queued) => {
        setError('');
        setRecord({call_id: call.id, queue_id: queued?.id, kind: 'gain', yards: 0,
            elapsed_seconds: Math.min(20, session.state.quarter_seconds_remaining), observed_coverage: 'UNKNOWN'});
    };

    const submitResult = event => {
        event.preventDefault();
        const {call_id, queue_id, ...outcome} = record;
        task(() => dashboardRequest(`/api/sessions/${session.id}/plays`, {
            method: 'POST', body: {...mutation(session), call_id, ...(queue_id ? {queue_id} : {}), outcome, ...(presentation ? {presentation} : {})},
        }), 'Play recorded. The game state and next-down comparison have been updated.');
    };

    const state = session?.state || draft;
    const currentEvaluation = evaluation?.revision === session?.revision ? evaluation : null;
    const fit = currentEvaluation?.situational_fit;
    const play = calls.find(call => call.id === selectedId) || calls.find(call => call.id === fit?.suggestions[0]?.call_id);
    const selectedFit = fit?.suggestions.find(item => item.call_id === play?.id);
    const selectedExclusion = fit?.excluded.find(item => item.call_id === play?.id);
    const presentation = fit ? {revision: session.revision, candidate_ids: fit.suggestions.map(item => item.call_id)} : null;
    const comparison = currentEvaluation?.comparison;
    const defense = currentEvaluation?.defense;
    const active = session?.status === 'active';
    const allowed = call => !!call && !!fit?.eligible_call_ids.includes(call.id);
    const change = (key, value) => setDraft(previous => ({...previous, [key]: value}));

    const controls = draft && preferences && <form className="oc-panel oc-situation-panel oc-live-controls" onSubmit={saveSituation}>
        <div className="oc-panel-heading"><h2>{session ? 'Coach’s controls' : 'Set up your game'}</h2><Icon name="sliders"/></div>
        <p className="oc-panel-description">{session ? 'Edits change the situation, not the completed-play history.' : 'Enter the current state to create a saved session.'}</p>
        <fieldset disabled={blocked}>
            <div className="oc-control-groups">
            <section className="oc-control-group" aria-labelledby="oc-matchup-heading"><h3 id="oc-matchup-heading">Matchup & clock</h3>
            <div className="oc-input-pair">{[['posteam', 'Offense'], ['defteam', 'Defense']].map(([key, label]) => <label key={key}>{label}<select value={draft[key]} onChange={event => change(key, event.target.value)}>{meta.teams.map(team => <option key={team}>{team}</option>)}</select></label>)}</div>
            <div className="oc-input-pair">{[['offense_score', 'Offense score'], ['defense_score', 'Defense score']].map(([key, label]) => <label key={key}>{label}<input required type="number" min="0" max="100" value={draft[key]} onChange={event => change(key, event.target.value === '' ? '' : Number(event.target.value))}/></label>)}</div>
            <div className="oc-input-pair"><label>Quarter<select value={draft.qtr} onChange={event => change('qtr', Number(event.target.value))}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>Quarter {value}</option>)}</select></label><label>Quarter clock<input required aria-label="Quarter clock" value={draft.clock} pattern="[0-9]{1,2}:[0-5][0-9]" placeholder="MM:SS" onChange={event => change('clock', event.target.value)}/></label></div>
                        <div className="oc-input-pair">{[['posteam_timeouts_remaining', 'Offense timeouts'], ['defteam_timeouts_remaining', 'Defense timeouts']].map(([key, label]) => <label key={key}>{label}<select value={draft[key]} onChange={event => change(key, Number(event.target.value))}>{[0, 1, 2, 3].map(value => <option key={value}>{value}</option>)}</select></label>)}</div>
            </section>
            <section className="oc-control-group" aria-labelledby="oc-field-heading"><h3 id="oc-field-heading">Field & defensive look</h3>
            <div className="oc-input-pair"><label>Down<select value={draft.down} onChange={event => change('down', Number(event.target.value))}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>{ordinal(value)} down</option>)}</select></label><label>Yards to go<input required type="number" min="1" max="99" value={draft.ydstogo} onChange={event => change('ydstogo', event.target.value === '' ? '' : Number(event.target.value))}/></label></div>
            <label>Yards to opponent’s goal line<input required type="number" min="1" max="99" value={draft.yardline_100} onChange={event => change('yardline_100', event.target.value === '' ? '' : Number(event.target.value))}/></label>

            <label>Observed defensive look<select value={draft.coverage} onChange={event => change('coverage', event.target.value)}>{meta.coverages.map(value => <option key={value} value={value}>{value === 'UNKNOWN' ? 'Unknown' : value.replace(/_/g, ' ')}</option>)}</select></label>
            <p className="oc-inline-help">Saved as a coaching observation. The current outcome model does not use coverage.</p>
            <label>Allowed actions<select value={draft.action_filter} onChange={event => change('action_filter', event.target.value)}><option value="all">Run and pass</option><option value="run">Run only</option><option value="pass">Pass only</option></select></label>
            </section>
            <section className="oc-control-group" aria-labelledby="oc-fit-heading"><h3 id="oc-fit-heading">Playbook & approach</h3>
            <p className="oc-inline-help">These inputs guide coaching rules only. Save to refresh the shortlist; run/pass EPA still uses game state and teams.</p>
            {[['personnel', 'On-field personnel', meta.personnel], ['formation', 'Formation', meta.formations], ['objective', 'Coaching objective', meta.coaching_objectives]].map(([key, label, choices]) => <label key={key}>{label}<select value={preferences[key]} onChange={event => setPreferences({...preferences, [key]: event.target.value})}>{Object.entries(choices).map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label>)}
            <label>Anticipated coverage for next snap<select value={preferences.anticipated_coverage} onChange={event => setPreferences({...preferences, anticipated_coverage: event.target.value})}>{meta.coverages.map(value => <option key={value} value={value}>{value.replace(/_/g, ' ')}</option>)}</select></label>
            <p className="oc-inline-help">Your pre-snap hypothesis, separate from observed coverage. Resets to Unknown after a recorded play.</p>
            <details className="oc-installed"><summary>Available playbook · {preferences.installed_call_ids.length} calls</summary><p className="oc-inline-help">Uncheck concepts your offense has not installed.</p>{calls.map(call => <label key={call.id}><input type="checkbox" checked={preferences.installed_call_ids.includes(call.id)} onChange={event => setPreferences({...preferences, installed_call_ids: event.target.checked ? [...preferences.installed_call_ids, call.id] : preferences.installed_call_ids.filter(id => id !== call.id)})}/>{call.name}</label>)}</details>
            <label>Ranking objective<select value="epa" onChange={() => {}}><option value="epa">Expected points added</option><option disabled>Conversion probability — unavailable</option><option disabled>Turnover risk — unavailable</option></select></label>
            </section>
            </div>
            <div className="oc-control-actions">
            <button className="oc-primary oc-full" type="submit" disabled={!!session && !active}>{session ? 'Save situation & evaluate' : 'Create game session'}<Icon name="arrow" size={15}/></button>
            {session && session.mode !== 'historical_review' && <button className="oc-secondary oc-full" type="submit" value="drive">Start new drive with these inputs</button>}
            {session && <button className="oc-text-button oc-full" type="submit" value="create">Create a separate game session</button>}
            </div>
        </fieldset>
    </form>;

    return <div className="oc-preview oc-connected">
        <aside className="oc-sidebar">
            <a className="oc-brand" href="/" aria-label="DigitalOC dashboard"><span className="oc-brand-icon"><Icon name="target" size={25}/></span>digital<span>OC</span><span className="oc-brand-dot">.</span></a>
            <div className="oc-workspace"><span className="oc-avatar">{state?.posteam || 'OC'}</span><div><strong>{state ? `${state.posteam} offense` : 'Coordinator workspace'}</strong><span>SAVED GAME SESSIONS</span></div></div>
            <p className="oc-nav-label">YOUR SIDELINE</p>
            <nav aria-label="Dashboard navigation">{[['Command center', 'grid'], ['Playbook', 'book'], ['Coaches Notes', 'book'], ['Drive log', 'clock'], ['Data & review', 'sliders']].map(([label, icon]) => <button key={label} disabled={blocked} className={view === label ? 'active' : ''} aria-current={view === label ? 'page' : undefined} onClick={() => setView(label)}><Icon name={icon}/>{label}{label === 'Drive log' && session && <span className="oc-nav-count">{session.plays.length}</span>}</button>)}</nav>
            <div className="oc-sidebar-bottom"><div className="oc-demo-label"><span/> {meta ? 'CONNECTED WORKSPACE' : 'CONNECTING'}</div><p>A clearer picture.<br/>A better next call.</p><a href="/preview">View design preview <Icon name="arrow" size={15}/></a><a href="/situation">Legacy play suggester <Icon name="arrow" size={15}/></a><div className="oc-profile"><span className="oc-avatar">OC</span><div><strong>Offensive coordinator</strong><span>Manual game tracking</span></div></div></div>
        </aside>
        <main className="oc-main">
            <header className="oc-topbar"><div>WORKSPACE <span>/</span><strong>{view}</strong></div><span className="oc-sample-badge"><span/>{meta ? 'Connected · experimental estimates' : 'Connecting to game service'}</span></header>
            <section className="oc-page-heading"><div><p className="oc-eyebrow">EVERY DOWN. ONE STEP AHEAD.</p><h1>{view === 'Command center' ? 'Your next move starts here.' : view === 'Playbook' ? 'Your calls, ready to go.' : view === 'Coaches Notes' ? 'Build your plan for the next snap.' : view === 'Data & review' ? 'Build data you can trust.' : 'Every play tells a story.'}</h1><p>Track the game. Compare run and pass. Keep the next decision in view.</p></div>{session && <div className="oc-game-week">DRIVE {String(session.drive).padStart(2, '0')}<span>{session.status.replace(/_/g, ' ').toUpperCase()}</span></div>}</section>
            {error && <div className="oc-error" role="alert">{error}<button type="button" onClick={() => window.location.reload()}>Reload saved state</button></div>}
            {loading && <div className="oc-panel" role="status">Loading your workspace…</div>}
            {meta && <>
                {sessions.length > 0 && <label className="oc-session-picker">Saved game<select aria-label="Saved game" disabled={blocked} value={session?.id || ''} onChange={event => task(() => dashboardRequest(`/api/sessions/${event.target.value}`), 'Saved game loaded.')}><option value="" disabled>Select a game</option>{sessions.map(item => <option key={item.id} value={item.id}>{item.state.posteam} vs {item.state.defteam} · {new Date(item.updated_at).toLocaleString()}</option>)}</select></label>}
                {session && <section className="oc-scoreboard" aria-label="Saved game situation"><div className="oc-matchup"><TeamLogo team={state.posteam}/><div><span>{state.posteam}<small>TRACKED OFFENSE</small></span><strong>{state.offense_score}</strong></div><span className="oc-score-divider">:</span><div><span>{state.defteam}</span><strong>{state.defense_score}</strong></div><TeamLogo team={state.defteam}/></div><div className="oc-score-stat"><span>QUARTER / CLOCK</span><strong>Q{state.qtr}<i/>{clock(state.quarter_seconds_remaining)}</strong></div><div className="oc-score-stat"><span>DOWN & DISTANCE</span><strong>{ordinal(state.down)} <em>& {state.ydstogo}</em></strong></div><div className="oc-score-stat"><span>FIELD POSITION</span><strong>{field(state)}</strong></div><div className="oc-timeouts"><span>TIMEOUTS</span><div>{Array.from({length: state.posteam_timeouts_remaining}, (_, i) => <i key={i}/>)}</div><small>{state.posteam_timeouts_remaining} remaining</small></div></section>}
                <div className="oc-notice" role="status">{notice || (session ? 'Saved locally on the backend. Estimates compare broad run/pass actions, not individual concepts.' : 'No game has been created yet. Start with your actual situation below.')}</div>
                {session?.mode === 'historical_review' && <div className="oc-status-panel">Historical labeling batch. Use Data &amp; review to verify these source plays. This is not a live game session.</div>}
                {session && !active && session.mode !== 'historical_review' && <div className="oc-status-panel">{session.status === 'finished' ? 'Regulation has ended. Overtime is not modeled.' : 'This drive or half has ended.'} Set scores, clock, field position, and possession in Coach’s controls, then start a new drive. Extra points, penalties, and returns require manual correction.</div>}
                {view === 'Command center' && <section className="oc-coordinator-hub" aria-label="Game controls and opponent overview">{controls}{session && <section className="oc-panel oc-defense-panel"><div className="oc-panel-heading"><h2>Across the line</h2><span className="oc-tiny-badge">HISTORICAL</span></div><p className="oc-panel-description">{state.defteam} coverage on labeled dropbacks</p><div className="oc-observation">Your current observation: <strong>{state.coverage.replace(/_/g, ' ')}</strong></div>{defense?.status === 'historical_frequencies' ? <><div className="oc-coverage-grid">{defense.distribution.map(item => <div className="oc-probability" key={item.coverage}><div><span>{item.coverage.replace(/_/g, ' ')}</span><strong>{(item.frequency * 100).toFixed(1)}%</strong></div><div className="oc-bar-track"><div style={{width: `${item.frequency * 100}%`}}/></div></div>)}</div><p className="oc-inline-help">{defense.sample_count.toLocaleString()} labeled plays · {defense.seasons.join(', ')}. Matched by {defense.scope}.</p><p className="oc-inline-help">{defense.description} Source: {defense.source}.</p></> : <p className="oc-inline-help">{defense?.reason || 'Historical coverage will appear after evaluation.'}</p>}<div className="oc-defense-note"><Icon name="target" size={17}/><p>A calibrated forecast of the next defensive response is not available.</p></div></section>}</section>}
                {view === 'Command center' && <div className="oc-dashboard-grid"><section className="oc-call-workspace">
                    {!session ? <div className="oc-panel oc-empty"><Icon name="target" size={36}/><h2>Start with the situation.</h2><p>Create a game session to get real run/pass estimates and begin your drive log. Nothing here is a simulated game result.</p></div> : <>
                        <div className="oc-section-title"><div><span className="oc-step">01</span><h2>Run or pass?</h2></div><span>EXPERIMENTAL · EPA RANKING</span></div>
                        {evaluationError ? <div className="oc-error" role="alert">{evaluationError}<button onClick={() => setSession({...session})}>Retry evaluation</button></div> : !currentEvaluation ? <div className="oc-panel" role="status">Evaluating the saved situation…</div> : comparison ? <>
                            <div className="oc-action-cards">{comparison.options.map(option => <article className="oc-play-card" key={option.action}><div className="oc-card-top"><span className={`oc-play-type ${option.action}`}>{option.action.toUpperCase()}</span><span>ESTIMATED RANK {option.estimated_rank}</span></div><h3>{option.action === 'pass' ? 'Pass intent' : 'Designed run'}</h3><div className="oc-card-metric"><strong>{signed(option.expected_epa)}</strong><span>EXPECTED EPA</span></div><div className="oc-action-metrics"><span><strong>{option.expected_yards.toFixed(1)}</strong> expected yards</span><span><strong>{(option.historical_call_probability * 100).toFixed(0)}%</strong> call tendency</span></div><p>{option.training_examples_in_down_distance_bucket.toLocaleString()} training plays in this down/distance band</p>{option.support_status === 'sparse' && <p className="oc-sparse">Sparse support. Treat this estimate cautiously.</p>}</article>)}</div>
                            <p className="oc-inline-help">Run/pass EPA does not account for this play design. Call tendency is how often a call is expected, not its chance of success. Estimated ordering is provisional. Fourth-down comparisons omit kicking options.</p>
                        </> : <div className="oc-panel">{currentEvaluation.status === 'model_unavailable' ? 'Outcome model unavailable. Game tracking and the playbook still work.' : 'Start the next drive to evaluate another call.'}</div>}
                        <div className="oc-section-title oc-concept-heading"><div><h2>Choose a playbook call</h2></div><span>SITUATIONAL FIT · COACHING RULES</span></div>
                        <ConceptSuggestions fit={fit} calls={calls} selectedId={play?.id} disabled={blocked} onSelect={setSelectedId}/>
                        {play && <article className="oc-play-detail"><div className="oc-detail-header"><div><p className="oc-eyebrow">THE CALL · COACH SELECTED</p><h2>{play.name}<span>{play.type === 'PASS' ? 'Pass concept' : 'Run concept'}</span></h2></div></div><FormationEditor key={`${session.id}:${play.id}:${session.revision}`} play={play} meta={meta} preferences={session.preferences} busy={busy} onEditing={setEditingLayout} onSave={(positions, design) => task(() => dashboardRequest(`/api/sessions/${session.id}/layouts/${play.id}`, {method: 'PUT', body: {...mutation(session), positions, ...(design ? {design} : {})}}), design ? 'Design saved. Confirmed formation and personnel applied; coaching recommendations refreshed. Run/pass EPA does not use the design.' : 'Visual alignment saved. Coaching rules and model inputs are unchanged.')}/><div className="oc-field-legend"><span><i className="offense"/>Offense</span><span><i className="defense">×</i>Illustrative defense</span><span>SCHEMATIC TEMPLATE</span></div><div className="oc-explanation"><h3>Coaching notes</h3><button type="button" className="oc-primary oc-plan-launch" disabled={blocked} onClick={() => setView('Coaches Notes')}><span>Open game-plan assistant</span><Icon name="arrow" size={18}/></button><p>{play.summary}</p><p>{play.read}</p>
                            {selectedFit && <p><strong>Current fit:</strong> {selectedFit.reasons.join(' ')}</p>}
                            {fit && !selectedFit && <p className="oc-fit-caution">Your selected call is preserved. {selectedExclusion ? selectedExclusion.reasons.join(' ') : 'It remains eligible but is outside the current three-call shortlist.'}</p>}
                            <p><strong>Related concepts to review:</strong> {play.counters?.map(id => calls.find(call => call.id === id)?.name).filter(Boolean).join(', ')}. Coaching links only; no optimized sequence is predicted.</p></div><div className="oc-unavailable">Concept-specific EPA, first-down probability, and turnover risk are not available. The run/pass estimates above must not be interpreted as this call’s performance.</div><div className="oc-detail-footer"><span>{play.tag}</span><div className="oc-button-row"><button className="oc-secondary" disabled={blocked || !active || !fit} onClick={() => startRecord(play)}>Record actual result</button><button className="oc-primary" disabled={blocked || !active || !allowed(play)} onClick={() => queueCall(play)}>Add to call sheet <Icon name="arrow" size={15}/></button></div></div></article>}
                        {session.queue.length > 0 && <section className="oc-panel oc-queue"><h2>Planned calls</h2>{session.queue.map(entry => <div key={entry.id} className="oc-queue-row"><div><strong>{entry.name}</strong><span>Queued · not a completed play</span>{fit && !allowed(calls.find(call => call.id === entry.call_id)) && <span className="oc-fit-caution">Outside the current constraints; kept for your review.</span>}</div><div className="oc-button-row"><button className="oc-secondary" disabled={blocked || !active || !fit} onClick={() => startRecord(calls.find(call => call.id === entry.call_id), entry)}>Record result</button><button className="oc-text-button" disabled={blocked} onClick={() => task(() => dashboardRequest(`/api/sessions/${session.id}/queue/${entry.id}`, {method: 'DELETE', body: mutation(session)}), 'Planned call removed.')}>Remove</button></div></div>)}</section>}
                    </>}
                </section></div>}

                {view === 'Command center' && session && currentEvaluation?.branches.length > 0 && <section className="oc-sequence"><div className="oc-section-title"><div><span className="oc-step">02</span><h2>Explore the next down</h2></div><span>WHAT-IF COMPARISON · NO BRANCH PROBABILITIES</span></div><div className="oc-sequence-cards oc-two-branches">{currentEvaluation.branches.map(branch => <article key={branch.label}><span className="oc-branch-label">{branch.label}</span><h3>{branch.status === 'active' ? `${ordinal(branch.state.down)} & ${branch.state.ydstogo} · ${field(branch.state)}` : 'Drive ends'}</h3>{branch.comparison ? branch.comparison.options.map(option => <p key={option.action}><strong>{option.action.toUpperCase()}</strong> · {signed(option.expected_epa)} expected EPA · {option.expected_yards.toFixed(1)} expected yards</p>) : <p>Set the next possession after the actual result.</p>}<p>{branch.assumption}. This does not identify a setup play or an optimal sequence.</p></article>)}</div></section>}

                {view === 'Playbook' && <section className="oc-panel oc-library"><div className="oc-section-title"><div><h2>Starter playbook</h2><span className="oc-tiny-badge">COACHING TEMPLATES</span></div><div className="oc-filter">{['ALL', 'RUN', 'PASS'].map(value => <button key={value} aria-pressed={filter === value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{value}</button>)}</div></div><p className="oc-inline-help">Stored in the backend catalog with stable call IDs. Confirm each template against your installed playbook.</p><div className="oc-library-grid">{calls.filter(call => filter === 'ALL' || call.type === filter).map(call => <article key={call.id}><PlayField play={call}/><span className={`oc-play-type ${call.type.toLowerCase()}`}>{call.type}</span><h3>{call.name}</h3><p>{call.summary}</p><button className="oc-secondary" onClick={() => {setSelectedId(call.id); setView('Command center');}}>Explore call <Icon name="arrow" size={15}/></button></article>)}</div></section>}

                {view === 'Coaches Notes' && <CoachesNotes key={session?.id || 'none'} session={session} calls={calls} busy={busy} onEditing={setEditingPlan}
                    onGenerate={() => task(() => dashboardRequest(`/api/sessions/${session.id}/plan/generate`, {method: 'POST', body: mutation(session)}), 'Game-plan draft saved. Review and edit it in Coaches Notes.')}
                    onSave={(context_id, content) => task(() => dashboardRequest(`/api/sessions/${session.id}/plan`, {method: 'PUT', body: {...mutation(session), context_id, content}}), 'Coaching plan saved.')}/>}

                {view === 'Data & review' && <DataReview session={session} calls={calls} meta={meta} busy={busy} onImport={(game_id, play_ids) => task(() => dashboardRequest('/api/labeling/import', {method: 'POST', body: {game_id, play_ids}}), 'Historical plays staged. Open each record below and verify its concept against film or charting evidence.')} onSave={(playId, review) => task(() => dashboardRequest(`/api/sessions/${session.id}/plays/${playId}/review`, {method: 'POST', body: {...mutation(session), review}}), 'Review saved. Original play and game state preserved.')}/>}

                {view === 'Drive log' && <section className="oc-panel oc-log"><div className="oc-section-title"><div><h2>Completed plays</h2><span className="oc-tiny-badge">SAVED GAME HISTORY</span></div>{session?.can_undo && <button className="oc-secondary" disabled={blocked} onClick={() => task(() => dashboardRequest(`/api/sessions/${session.id}/undo`, {method: 'POST', body: mutation(session)}), 'Latest play undone. Previous state restored.')}>Undo latest play</button>}</div><p className="oc-panel-description">Only results you record appear here. To correct the latest play, undo it before another change; penalties and other adjustments can be entered in Coach’s controls.</p>{!session?.plays.length ? <div className="oc-empty"><h3>No completed plays yet.</h3><p>Queue a call or record an actual result from the command center.</p></div> : <div className="oc-log-table"><div className="oc-log-row oc-log-labels"><span>PLAY / DRIVE</span><span>BEFORE</span><span>RESULT</span><span>AFTER</span></div>{session.plays.map(entry => <div className="oc-log-row" key={entry.id}><div><strong>{entry.name}</strong><span> · Drive {entry.drive}</span>{entry.decision_context && <details className="oc-log-context"><summary>Decision context</summary><p>{entry.decision_context.preferences.personnel} personnel · {entry.decision_context.preferences.formation.replace(/_/g, ' ')} · {entry.decision_context.preferences.objective}</p><p>Anticipated: {entry.decision_context.preferences.anticipated_coverage} · Observed: {entry.outcome.observed_coverage || 'UNKNOWN'}</p><p>Shortlist: {entry.decision_context.suggestions.map(item => item.name).join(', ') || 'None'}</p><p>{entry.decision_context.rule_version} · {entry.decision_context.display_source}</p></details>}</div><span>{ordinal(entry.before.down)} & {entry.before.ydstogo} · {field(entry.before)}</span><span>{entry.outcome.kind} · {signed(entry.outcome.yards, 0)} yd</span><span>{entry.after ? `${field(entry.after)} · ${clock(entry.after.quarter_seconds_remaining)}` : 'Post-play state not imported'}</span></div>)}</div>}</section>}

                {record && <div className="oc-modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="oc-result-title" className="oc-panel oc-result-dialog"><h2 id="oc-result-title">Record {calls.find(call => call.id === record.call_id)?.name}</h2><p className="oc-panel-description">This saves a completed play and advances the game state.</p><form className="oc-situation-panel" onSubmit={submitResult}><fieldset disabled={blocked}><label>Outcome<select autoFocus value={record.kind} onChange={event => setRecord({...record, kind: event.target.value, yards: event.target.value === 'incomplete' ? 0 : record.yards})}>{['gain', 'incomplete', 'sack', 'turnover', 'touchdown', 'safety'].map(value => <option key={value}>{value}</option>)}</select></label><div className="oc-input-pair"><label>Yards gained<input required type="number" min="-99" max="99" value={record.yards} onChange={event => setRecord({...record, yards: event.target.value === '' ? '' : Number(event.target.value)})}/></label><label>Seconds elapsed<input required type="number" min="0" max={state.quarter_seconds_remaining} value={record.elapsed_seconds} onChange={event => setRecord({...record, elapsed_seconds: event.target.value === '' ? '' : Number(event.target.value)})}/></label></div><label>Actual coverage observed<select value={record.observed_coverage} onChange={event => setRecord({...record, observed_coverage: event.target.value})}>{meta.coverages.map(value => <option key={value}>{value}</option>)}</select></label><p className="oc-inline-help">For sacks, record a pass call. For touchdowns, enter yards to the goal line. Returns, extra points, and penalties need manual state correction.</p>{error && <p role="alert" className="oc-error">{error}</p>}<div className="oc-button-row"><button type="button" className="oc-secondary" onClick={() => {setRecord(null); setError('');}}>Cancel</button><button className="oc-primary" type="submit">Save completed play</button></div></fieldset></form></section></div>}
                <footer className="oc-footer"><span><strong>digitalOC.</strong> Saved game state. Coach-led decisions.</span><span>{comparison?.model_id || meta.model_id || 'MODEL UNAVAILABLE'}</span></footer>
            </>}
        </main>
    </div>;
}
