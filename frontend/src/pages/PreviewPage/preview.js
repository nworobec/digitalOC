import {playDiagrams} from './playDiagrams';
import {defaultPositions, playerLabels, clampPosition, anchoredRoute} from './formationPositions';
import React, {useId, useMemo, useState} from 'react';
import kcLogo from '../../logos/KC.png';
import bufLogo from '../../logos/BUF.png';
import './preview.css';

const initialSituation = {down: '2', distance: '6', coverage: 'Unknown', objective: 'Move the chains'};
const calls = [
    {id: 'mesh', name: 'Mesh sit', type: 'PASS', tag: '11 personnel · Gun trips', epa: 0.24, conversion: 58, risk: 'Moderate',
        summary: 'Crossing routes create a natural release against man. The sit route gives the quarterback an answer against zone.',
        read: 'Read the shallow cross, then the sit route. Keep the back available underneath.', audible: 'If the defense shows pressure, check to the quick outlet.', next: 'If the chains move', follow: 'Inside zone', color: '#c5f277'},
    {id: 'zone', name: 'Inside zone', type: 'RUN', tag: '11 personnel · Gun doubles', epa: 0.12, conversion: 43, risk: 'Lower',
        summary: 'A downhill option from a balanced look. Use the box count to decide whether to stay with the run or check out.',
        read: 'Press the front-side gap and read the first down lineman past the center.', audible: 'Against a loaded box, check to the quick passing option.', next: 'If the box tightens', follow: 'Play-action cross', color: '#f6b46d'},
    {id: 'flood', name: 'Flood concept', type: 'PASS', tag: '12 personnel · Gun bunch', epa: 0.18, conversion: 49, risk: 'Higher',
        summary: 'Three receiving levels stretch one side of the field. A deeper option when the defense protects the middle.',
        read: 'Read the deep route to the intermediate out, then take the flat.', audible: 'If pressure takes away the longer read, get the ball to the flat.', next: 'If the defense stays deep', follow: 'Split zone', color: '#a6ceda'},
];
const startingLog = [
    {id: 'seed-1', name: 'Duo', type: 'RUN', detail: '1st & 10 · KC 48', result: '+4 YDS', status: 'Sample result'},
    {id: 'seed-2', name: 'Stick', type: 'PASS', detail: '2nd & 6 · BUF 48', result: '+9 YDS', status: 'Sample result'},
    {id: 'seed-3', name: 'Inside zone', type: 'RUN', detail: '1st & 10 · BUF 39', result: '+4 YDS', status: 'Sample result'},
];

export function Icon({name, size = 20, ...props}) {
    const paths = {
        grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
        book: <><path d="M12 5v16M3 4h5a4 4 0 0 1 4 2 4 4 0 0 1 4-2h5v15h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3Z"/></>,
        clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
        arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
        chevron: <path d="m9 5 7 7-7 7"/>,
        sliders: <><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="16" cy="17" r="3"/></>,
        check: <path d="m5 12 4 4L19 6"/>,
        target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="m12 12 8-8"/></>,
    };
    return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.arrow}</svg>;
}

export function PlayField({play, positions: suppliedPositions, onMove, selectedPlayer, onSelectPlayer}) {
    const fieldId = useId().replace(/:/g, "");
    const positions = suppliedPositions || play.layout?.positions || defaultPositions;
    const [dragging, setDragging] = useState(null);
    const movePointer = event => {
        if (dragging === null || !onMove) return;
        const svg = event.currentTarget;
        const matrix = svg.getScreenCTM();
        if (!matrix) return;
        const point = svg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY;
        const local = point.matrixTransform(matrix.inverse());
        onMove(dragging, clampPosition(local.x, local.y));
    };
    return <svg className={`oc-field ${onMove ? 'oc-field-editable' : ''}`} viewBox="0 0 620 310" role={onMove ? 'group' : 'img'} aria-label={`Illustrative ${play.name} play diagram; offense moves toward the top of the field`}
        onPointerMove={movePointer} onPointerUp={() => setDragging(null)} onPointerCancel={() => setDragging(null)} onLostPointerCapture={() => setDragging(null)}>

        <defs>
            <pattern id={`${fieldId}-turf`} width="620" height="64" patternUnits="userSpaceOnUse"><rect width="620" height="32" fill="#ffffff" opacity=".025"/></pattern>
            <marker id={`${fieldId}-route-arrow`} markerWidth="8" markerHeight="8" refX="5" refY="3" orient="auto"><path d="M0 0 6 3 0 6" fill="none" stroke="#cbf48b" strokeWidth="1.4"/></marker>
            <marker id={`${fieldId}-orange-arrow`} markerWidth="8" markerHeight="8" refX="5" refY="3" orient="auto"><path d="M0 0 6 3 0 6" fill="none" stroke="#f4b67c" strokeWidth="1.4"/></marker>
        </defs>
        <rect width="620" height="310" rx="12" fill="#143e35"/><rect width="620" height="310" fill={`url(#${fieldId}-turf)`}/>
        {[42, 106, 170, 234, 298].map((y, i) => <g key={y} stroke="#eff6ef" strokeOpacity=".16"><path d={`M25 ${y}H595`}/><text x="32" y={y - 8} fill="#d7e3d8" stroke="none" opacity=".5" fontSize="13" fontFamily="monospace">{30 + i * 5}</text></g>)}
        {[74, 90, 122, 138, 154, 186, 218, 250, 266, 282].map(y => <path key={y} d={`M210 ${y}h7 M403 ${y}h7`} stroke="white" strokeOpacity=".22"/>)}
        <path d="M25 195H595" stroke="#abcfff" strokeDasharray="5 5" strokeOpacity=".55"/>
        <text x="28" y="188" fill="#abcfff" fontSize="9" letterSpacing="1.3">LINE OF SCRIMMAGE</text>
        {[[112, 151], [190, 148], [266, 172], [302, 169], [345, 170], [392, 174], [454, 145], [536, 148], [234, 94], [415, 87], [330, 132]].map(([x, y], i) => <path key={i} d={`m${x - 4} ${y - 4} 8 8m-8 0 8-8`} stroke="#b6c9c0" strokeWidth="2" opacity=".7"/>)}
        <g fill="none" stroke="#cbf48b" strokeWidth="2.5" strokeLinejoin="round" markerEnd={`url(#${fieldId}-route-arrow)`}>
            {(playDiagrams[play.diagram_key || play.id]?.routes || []).map((route, index) => <path key={index} d={anchoredRoute(route, positions)}/>)}
        </g>
        {playDiagrams[play.diagram_key || play.id] && <path d={anchoredRoute(playDiagrams[play.diagram_key || play.id].back, positions)} fill="none" stroke="#f4b67c" strokeWidth="3" markerEnd={`url(#${fieldId}-orange-arrow)`}/>}

        {positions.map(([x, y], i) => <g key={i} role={onMove ? 'button' : undefined} tabIndex={onMove ? 0 : undefined}
            aria-label={onMove ? `${playerLabels[i]}, x ${x}, y ${y}. Use arrow keys to move.` : undefined}
            aria-pressed={onMove ? selectedPlayer === i : undefined}
            onFocus={() => onSelectPlayer?.(i)}
            onPointerDown={event => {if (!onMove) return; event.preventDefault(); onSelectPlayer?.(i); setDragging(i); event.currentTarget.focus(); event.currentTarget.ownerSVGElement.setPointerCapture(event.pointerId);}}
            onKeyDown={event => {if (!onMove) return; const offsets = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}; const offset = offsets[event.key]; if (offset) {event.preventDefault(); const step = event.shiftKey ? 10 : 2; onMove(i, clampPosition(x + offset[0] * step, y + offset[1] * step));}}}>
            {onMove && <circle cx={x} cy={y} r="15" fill={selectedPlayer === i ? '#ffffff33' : 'transparent'} stroke={selectedPlayer === i ? '#f4b67c' : 'none'}/>}
            <circle cx={x} cy={y} r={i === 9 ? 11 : 8} fill={i === 9 ? '#cbf48b' : '#173e35'} stroke={i === 9 ? '#cbf48b' : '#f4f5df'} strokeWidth="2"/>{i === 9 && <text x={x} y={y + 3.5} textAnchor="middle" fill="#173e35" fontSize="9" fontWeight="800">QB</text>}</g>)}
    </svg>;
}

export default function Preview() {
    const [view, setView] = useState('Command center');
    const [draft, setDraft] = useState(initialSituation);
    const [situation, setSituation] = useState(initialSituation);
    const [selectedId, setSelectedId] = useState('mesh');
    const [filter, setFilter] = useState('ALL');
    const [savedCalls, setSavedCalls] = useState([]);
    const [notice, setNotice] = useState('');
    const play = calls.find(call => call.id === selectedId);
    const rankedCalls = useMemo(() => {
        // Curated demo scenarios, deliberately separate from model predictions.
        const candidates = calls.map(call => ({...call, epa: call.epa + (
            situation.coverage === 'Cover 3' && call.id === 'flood' ? 0.1 : 0
        )}));
        const preferred = situation.objective === 'Protect the ball' ? 'zone'
            : situation.objective === 'Create an explosive' ? 'flood' : null;
        return candidates.sort((a, b) => (Number(b.id === preferred) - Number(a.id === preferred)) || b.epa - a.epa);
    }, [situation]);
    const selectedMetrics = rankedCalls.find(call => call.id === selectedId);
    const defensiveLooks = situation.coverage === 'Cover 3'
        ? [['Cover 3', 62], ['Cover 1', 24], ['Other looks', 14]]
        : situation.coverage === 'Man look' ? [['Cover 1', 64], ['Cover 3', 22], ['Other looks', 14]]
        : [['Cover 1', 46], ['Cover 3', 34], ['Other looks', 20]];

    const applySituation = event => {
        event.preventDefault();
        setSituation({...draft});
        setNotice('Sample scenario updated. Estimates are illustrative, not live predictions.');
    };
    const saveCall = () => {
        setSavedCalls(previous => [...previous, {...play, id: `${play.id}-${Date.now()}`, detail: `${situation.down}${['', 'st', 'nd', 'rd', 'th'][Number(situation.down)]} & ${situation.distance} · BUF 35`, result: 'QUEUED', status: 'Planned call'}]);
        setNotice(`${play.name} added to your demo call sheet. No completed play was recorded.`);
    };

    return <div className="oc-preview">
        <aside className="oc-sidebar">
            <a className="oc-brand" href="/preview" aria-label="DigitalOC preview home"><span className="oc-brand-icon"><Icon name="target" size={25}/></span>digital<span>OC</span><span className="oc-brand-dot">.</span></a>
            <div className="oc-workspace"><span className="oc-avatar">KC</span><div><strong>Chiefs offense</strong><span>COORDINATOR WORKSPACE</span></div></div>
            <p className="oc-nav-label">YOUR SIDELINE</p>
            <nav aria-label="Preview navigation">{[['Command center', 'grid'], ['Playbook', 'book'], ['Drive log', 'clock']].map(([label, icon]) => <button key={label} className={view === label ? 'active' : ''} aria-current={view === label ? 'page' : undefined} onClick={() => {setView(label); setNotice('');}}><Icon name={icon}/>{label}{label === 'Drive log' && <span className="oc-nav-count">{startingLog.length + savedCalls.length}</span>}</button>)}</nav>
            <div className="oc-sidebar-bottom"><div className="oc-demo-label"><span/> DESIGN PREVIEW</div><p>A clearer picture.<br/>A better next call.</p><a href="/situation">Open current app <Icon name="arrow" size={15}/></a><div className="oc-profile"><span className="oc-avatar">OC</span><div><strong>Offensive coordinator</strong><span>Demo workspace</span></div></div></div>
        </aside>

        <main className="oc-main">
            <header className="oc-topbar"><div>WORKSPACE <span>/</span> <strong>{view}</strong></div><span className="oc-sample-badge"><span/> Sample game · UI preview</span></header>
            <section className="oc-page-heading"><div><p className="oc-eyebrow">EVERY DOWN. ONE STEP AHEAD.</p><h1>{view === 'Command center' ? 'Your next move starts here.' : view === 'Playbook' ? 'The right call, within reach.' : 'Every play tells a story.'}</h1><p>{view === 'Command center' ? 'Read the situation. Anticipate the response. Make the call.' : view === 'Playbook' ? 'Explore the sample concepts and build your call sheet.' : 'Review the sample drive and the calls you have queued.'}</p></div><div className="oc-game-week">WEEK 06<span>GAME PLAN / 001</span></div></section>

            <section className="oc-scoreboard" aria-label="Sample game situation">
                <div className="oc-matchup"><img src={kcLogo} alt="Kansas City Chiefs"/><div><span>KANSAS CITY <small>ON OFFENSE</small></span><strong>14</strong></div><span className="oc-score-divider">:</span><div><span>BUFFALO</span><strong>10</strong></div><img src={bufLogo} alt="Buffalo Bills"/></div>
                <div className="oc-score-stat"><span>QUARTER / CLOCK</span><strong>Q2 <i/> 05:00</strong></div>
                <div className="oc-score-stat"><span>DOWN & DISTANCE</span><strong>{situation.down}{['', 'st', 'nd', 'rd', 'th'][Number(situation.down)]} <em>& {situation.distance}</em></strong></div>
                <div className="oc-score-stat"><span>FIELD POSITION</span><strong>BUF <em>35</em></strong></div>
                <div className="oc-timeouts"><span>TIMEOUTS</span><div><i/><i/><i/></div><small>3 remaining</small></div>
            </section>

            <div className="oc-notice" role="status" aria-live="polite">{notice || 'Interactive mockup — all estimates, defensive probabilities, and game results are sample data.'}</div>

            {view === 'Command center' && <>
                <div className="oc-dashboard-grid">
                    <section className="oc-call-workspace">
                        <div className="oc-section-title"><div><span className="oc-step">01</span><h2>Find your advantage</h2></div><span>{situation.objective === "Move the chains" ? "RANKED BY SAMPLE EPA" : "RANKED FOR YOUR OBJECTIVE"}</span></div>
                        <div className="oc-play-cards">{rankedCalls.map((call, index) => <button key={call.id} className={`oc-play-card ${selectedId === call.id ? 'selected' : ''}`} onClick={() => setSelectedId(call.id)} aria-pressed={selectedId === call.id}>
                            <div className="oc-card-top"><span className={`oc-play-type ${call.type.toLowerCase()}`}>{call.type}</span><span>{index === 0 ? 'TOP OPTION' : `0${index + 1}`}</span></div>
                            <h3>{call.name}</h3><p>{call.tag}</p><div className="oc-card-metric"><strong>+{call.epa.toFixed(2)}</strong><span>EST. EPA</span><span className="oc-card-selector">{selectedId === call.id ? <Icon name="check" size={13}/> : <Icon name="arrow" size={13}/>}</span></div>
                        </button>)}</div>

                        <article className="oc-play-detail">
                            <div className="oc-detail-header"><div><p className="oc-eyebrow">THE CALL</p><h2>{play.name} <span>{play.type === 'PASS' ? 'Pass concept' : 'Run concept'}</span></h2></div><span className="oc-detail-number">{String(calls.findIndex(call => call.id === selectedId) + 1).padStart(2, '0')}</span></div>
                            <PlayField play={play}/>
                            <div className="oc-field-legend"><span><i className="offense"/> Offense</span><span><i className="defense">×</i> Defense</span><span><i className="route"/> Route / assignment</span><span>ILLUSTRATIVE ALIGNMENT ↑</span></div>
                            <div className="oc-explanation"><h3>Why this call fits</h3><p>{play.summary}</p></div>
                            <div className="oc-outcome-strip"><div><span>FIRST-DOWN CHANCE</span><strong>{selectedMetrics.conversion}<small>%</small></strong></div><div><span>EXPECTED POINTS ADDED</span><strong>+{selectedMetrics.epa.toFixed(2)}</strong></div><div><span>RELATIVE RISK</span><strong className="oc-risk">{play.risk}</strong></div></div>
                            <div className="oc-detail-footer"><span><Icon name="book" size={16}/> {play.tag}</span><button className="oc-primary" onClick={saveCall}>Add to call sheet <Icon name="arrow" size={16}/></button></div>
                        </article>
                    </section>

                    <aside className="oc-context-column">
                        <form className="oc-panel oc-situation-panel" onSubmit={applySituation}>
                            <div className="oc-panel-heading"><h2>Coach’s controls</h2><Icon name="sliders"/></div><p className="oc-panel-description">Set the situation. Shape your options.</p>
                            <div className="oc-input-pair"><label>Down<select value={draft.down} onChange={event => setDraft({...draft, down: event.target.value})}>{['1', '2', '3', '4'].map(down => <option key={down} value={down}>{down}{['', 'st', 'nd', 'rd', 'th'][Number(down)]} down</option>)}</select></label><label>Yards to go<input type="number" min="1" max="35" required value={draft.distance} onChange={event => setDraft({...draft, distance: event.target.value})}/></label></div>
                            <label>Defensive look<select value={draft.coverage} onChange={event => setDraft({...draft, coverage: event.target.value})}><option>Unknown</option><option>Man look</option><option>Cover 3</option></select></label>
                            <label>Play-calling objective<select value={draft.objective} onChange={event => setDraft({...draft, objective: event.target.value})}><option>Move the chains</option><option>Protect the ball</option><option>Create an explosive</option></select></label>
                            <button className="oc-primary oc-full" type="submit">Update sample scenario <Icon name="arrow" size={16}/></button><p className="oc-input-note">Adjust the controls to explore this demo.</p>
                        </form>

                        <section className="oc-panel oc-defense-panel"><div className="oc-panel-heading"><h2>Across the line</h2><span className="oc-tiny-badge">SAMPLE</span></div><p className="oc-panel-description">Possible defensive responses</p>
                            <div className="oc-opponent"><img src={bufLogo} alt=""/><div><strong>Buffalo defense</strong><span>Against this offensive look</span></div></div>
                            {defensiveLooks.map(([name, percent], index) => <div className="oc-probability" key={name}><div><span>{name}</span><strong>{percent}%</strong></div><div className="oc-bar-track"><div style={{width: `${percent}%`, opacity: 1 - index * 0.25}}/></div></div>)}
                            <div className="oc-defense-note"><Icon name="target" size={17}/><p>A look is a clue, not a certainty. Confirm the alignment before the snap.</p></div>
                        </section>
                    </aside>
                </div>

                <section className="oc-sequence"><div className="oc-section-title"><div><span className="oc-step">02</span><h2>Think one play ahead</h2></div><span>CONDITIONAL PLAN · SAMPLE</span></div><div className="oc-sequence-cards">
                    <article><span className="oc-branch-label"><i/> CALL NOW</span><h3>{play.name}</h3><p>{play.read}</p></article>
                    <article><span className="oc-branch-label">↳ IF PRESSURE SHOWS</span><h3>Have an answer ready</h3><p>{play.audible}</p></article>
                    <article><span className="oc-branch-label">↳ {play.next.toUpperCase()}</span><h3>{play.follow}</h3><p>Recheck down, distance, and the defensive look before committing to the next call.</p></article>
                </div></section>
            </>}

            {view === 'Playbook' && <section className="oc-panel oc-library"><div className="oc-section-title"><div><h2>Sample playbook</h2><span className="oc-tiny-badge">3 CONCEPTS</span></div><div className="oc-filter" aria-label="Filter plays">{['ALL', 'RUN', 'PASS'].map(value => <button key={value} className={filter === value ? 'active' : ''} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value}</button>)}</div></div><div className="oc-library-grid">{calls.filter(call => filter === 'ALL' || call.type === filter).map(call => <article key={call.id}><PlayField play={call}/><span className={`oc-play-type ${call.type.toLowerCase()}`}>{call.type}</span><h3>{call.name}</h3><p>{call.summary}</p><button className="oc-secondary" onClick={() => {setSelectedId(call.id); setView('Command center');}}>Explore this call <Icon name="arrow" size={15}/></button></article>)}</div></section>}

            {view === 'Drive log' && <section className="oc-panel oc-log"><div className="oc-section-title"><div><h2>Drive 04</h2><span className="oc-tiny-badge">DEMO HISTORY</span></div><span>{savedCalls.length} planned calls</span></div><p className="oc-panel-description">Completed sample plays and your planned calls. Queued calls are not game results.</p><div className="oc-log-table"><div className="oc-log-row oc-log-labels"><span>PLAY</span><span>CONTEXT</span><span>STATUS</span><span>RESULT</span></div>{[...startingLog, ...savedCalls].map((entry, index) => <div className="oc-log-row" key={entry.id}><div><span className="oc-log-index">{String(index + 1).padStart(2, '0')}</span><strong>{entry.name}</strong></div><span>{entry.detail}</span><span>{entry.status}</span><strong className={entry.result === 'QUEUED' ? 'oc-queued' : 'oc-gain'}>{entry.result}</strong></div>)}</div>{savedCalls.length > 0 && <button className="oc-secondary" onClick={() => {setSavedCalls([]); setNotice('Planned demo calls cleared.');}}>Clear planned calls</button>}</section>}
            <footer className="oc-footer"><span><strong>digitalOC.</strong> Built for the decisions between downs.</span><span>DESIGN PREVIEW / 01 <span>•</span> SAMPLE DATA</span></footer>
        </main>
    </div>;
}
