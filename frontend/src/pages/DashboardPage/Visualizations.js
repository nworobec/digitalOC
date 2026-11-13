import React, {useEffect, useState} from 'react';
import {dashboardRequest} from './api';
import './visualizations.css';

const teams = 'ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LA LAC LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS'.split(' ');
const labels = {completions: 'Completions', attempts: 'Pass attempts', completionPct: 'Completion rate', passingYards: 'Passing yards', passTD: 'Passing touchdowns', interceptions: 'Interceptions', sacks: 'Sacks', ypa: 'Yards per pass', rushAttempts: 'Rush attempts', rushingYards: 'Rushing yards', rushTD: 'Rushing touchdowns', ypc: 'Yards per rush', adot: 'Average depth of target', rating: 'Passer rating'};
const passKeys = ['completions', 'attempts', 'completionPct', 'passingYards', 'rating', 'passTD', 'interceptions', 'ypa', 'adot'];
const runKeys = ['rushAttempts', 'rushingYards', 'rushTD', 'ypc'];
const summaryKeys = ['passingYards', 'completions', 'attempts', 'passTD', 'completionPct', 'ypa', 'sacks', 'interceptions', ...runKeys];
const format = (value, key) => value == null ? '—' : `${value.toLocaleString(undefined, {maximumFractionDigits: 2})}${key === 'completionPct' ? '%' : ''}`;
const heat = (rank, size) => rank == null ? '#eef0eb' : `hsl(${120 * (1 - (rank - 1) / Math.max(1, size - 1))} 82% 79%)`;
const logos = require.context('../../logos', false, /\.png$/);

export default function Visualizations({initialTeam = 'TB'}) {
    const [team, setTeam] = useState(initialTeam);
    const [season, setSeason] = useState('2024');
    const [down, setDown] = useState('all');
    const [side, setSide] = useState('offense');
    const [mode, setMode] = useState('Summary');
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    const [retry, setRetry] = useState(0);
    useEffect(() => {
        const controller = new AbortController();
        setData(null); setError('');
        dashboardRequest(`/api/visualizations?${new URLSearchParams({team, season, down, side})}`, {signal: controller.signal})
            .then(value => {if (!controller.signal.aborted) setData(value);})
            .catch(failure => {if (!controller.signal.aborted) setError(failure.message);});
        return () => controller.abort();
    }, [team, season, down, side, retry]);
    const metricLabel = key => side === 'offense' ? (key === 'sacks' ? 'Sacks allowed' : labels[key]) :
        key === 'interceptions' ? 'Interceptions caught' : key === 'sacks' ? 'Sacks made' : `${labels[key]} allowed`;
    const tile = (group, key) => {
        const metric = group.metrics[key];
        return <div className="oc-viz-tile" key={key} style={{background: heat(metric.rank, data.leagueSize)}}>
            <span>{metricLabel(key)}</span><strong>{format(metric.value, key)}</strong><small>{metric.rank ? `#${metric.rank} of ${data.leagueSize}` : 'No ranked sample'}</small>
        </div>;
    };
    const logo = `./${team === 'LA' ? 'LAR' : team}.png`;
    return <section className="oc-panel oc-viz" aria-label="Team data visualizations">
        <div className="oc-viz-heading"><div><span className="oc-tiny-badge">TEAM SCOUTING</span><h2>Team performance atlas</h2><p>Explore play mix, passing zones, and rushing gaps.</p></div>{logos.keys().includes(logo) && <img src={logos(logo)} alt={`${team} logo`}/>}</div>
        <div className="oc-viz-controls">
            <label>Team<select value={team} onChange={e => setTeam(e.target.value)}>{teams.map(t => <option key={t}>{t}</option>)}</select></label>
            <label>Season<select value={season} onChange={e => setSeason(e.target.value)}>{[2024, 2023, 2022, 2021, 2020].map(y => <option key={y}>{y}</option>)}</select></label>
            <label>Unit<select value={side} onChange={e => setSide(e.target.value)}><option value="offense">Offense</option><option value="defense">Defense</option></select></label>
            <label>Down<select value={down} onChange={e => setDown(e.target.value)}><option value="all">All downs</option>{[1, 2, 3, 4].map(d => <option key={d} value={d}>Down {d}</option>)}</select></label>
        </div>
        <div className="oc-viz-modes" role="group" aria-label="Visualization type">{['Summary', 'Passing', 'Rushing'].map(m => <button key={m} aria-pressed={mode === m} onClick={() => setMode(m)}>{m}</button>)}</div>
        <p className="oc-viz-method">Local {season} regular season and postseason · Kneels, spikes, and two-point attempts excluded. Ranks compare the same down across teams; ties share a rank. Green = stronger rank, red = weaker rank.</p>
        {error ? <div role="alert" className="oc-error">{error} <button className="oc-secondary" onClick={() => setRetry(n => n + 1)}>Retry</button></div> : !data ? <p role="status">Loading team visualizations…</p> : <>
            {!data.summary.totalPlays ? <p className="oc-empty">No plays match these filters.</p> : <>
                <div className="oc-viz-overview"><div className="oc-viz-donut" role="img" aria-label={`${data.summary.runRate}% run, ${(100 - data.summary.runRate).toFixed(2)}% pass`} style={{background: `conic-gradient(#234b36 0 ${data.summary.runRate}%, #829bd5 ${data.summary.runRate}% 100%)`}}><div><strong>{data.summary.totalPlays.toLocaleString()}</strong><span>plays</span></div></div><div><h3>{team} {side}</h3><p><span className="oc-viz-dot"/>Run {data.summary.runRate}%</p><p><span className="oc-viz-dot pass"/>Pass {(100 - data.summary.runRate).toFixed(2)}%</p><small>Pass mix includes sacks; pass attempts exclude sacks.</small></div></div>
                {mode === 'Summary' ? <div className="oc-viz-table-wrap"><table className="oc-viz-table"><thead><tr><th>Category</th><th>Metric</th><th>Value</th><th>League rank</th></tr></thead><tbody>{summaryKeys.map(key => <tr key={key}><td>{runKeys.includes(key) ? 'Rushing' : 'Passing'}</td><th scope="row">{metricLabel(key)}</th><td>{format(data.summary.metrics[key].value, key)}</td><td style={{background: heat(data.summary.metrics[key].rank, data.leagueSize)}}>{data.summary.metrics[key].rank ? `#${data.summary.metrics[key].rank}` : '—'}</td></tr>)}</tbody></table></div> : <div className={`oc-viz-grid ${mode.toLowerCase()}`}>{(mode === 'Passing' ? data.zones : data.gaps).map(group => <article key={group.key}><h3>{group.label}</h3><div className="oc-viz-tiles">{(mode === 'Passing' ? passKeys : runKeys).map(key => tile(group, key))}</div></article>)}</div>}
            </>}
            <p className="oc-viz-method">Zones use recorded short/deep pass locations. Gap labels map end → D, tackle → C, guard → B, middle → A; uncharted locations are excluded from breakdowns. Zero-attempt rates are unavailable. Volume ranks reflect totals, without adjusting for games played.</p>
        </>}
    </section>;
}
