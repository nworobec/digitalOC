import React, {useEffect, useState} from 'react';
import {dashboardRequest} from './api';

export default function HistoricalLabeling({onImport, busy}) {
    const [season, setSeason] = useState('2024');
    const [games, setGames] = useState([]);
    const [game, setGame] = useState('');
    const [action, setAction] = useState('all');
    const [page, setPage] = useState(0);
    const [result, setResult] = useState(null);
    const [selected, setSelected] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [loaded, setLoaded] = useState(false);
    const loadGames = async () => {
        setLoading(true); setError(''); setGame(''); setResult(null); setSelected([]);
        try {const data = await dashboardRequest(`/api/labeling/games?season=${season}`); setGames(data.games); setLoaded(true);}
        catch (failure) {setError(failure.message);}
        finally {setLoading(false);}
    };
    useEffect(() => {
        setResult(null); setSelected([]);
        if (!game) return undefined;
        const controller = new AbortController(); setLoading(true); setError('');
        dashboardRequest(`/api/labeling/plays?${new URLSearchParams({season, game_id: game, action, page})}`, {signal: controller.signal})
            .then(data => {if (!controller.signal.aborted) setResult(data);})
            .catch(failure => {if (failure.name !== 'AbortError') setError(failure.message);})
            .finally(() => {if (!controller.signal.aborted) setLoading(false);});
        return () => controller.abort();
    }, [game, action, page, season]);
    return <section className="oc-panel" aria-label="Historical play labeling">
        <h2>Build a real-play labeling queue</h2>
        <p className="oc-inline-help">Browse the local 2020–2024 data, then stage plays for film review. Routes and box-score descriptions cannot establish a complete concept. No concept labels or approvals are generated automatically.</p>
        <div className="oc-review-grid oc-situation-panel"><label>Source season<select disabled={loading || busy} value={season} onChange={event => {setSeason(event.target.value); setGames([]); setGame(''); setLoaded(false);}}>{['2024', '2023', '2022', '2021', '2020'].map(value => <option key={value}>{value}</option>)}</select></label><button className="oc-secondary" disabled={loading || busy} onClick={loadGames}>Browse source games</button></div>
        {loaded && <div className="oc-review-grid oc-situation-panel"><label>Source game<select disabled={loading || busy} value={game} onChange={event => {setGame(event.target.value); setPage(0);}}><option value="">Choose a game</option>{games.map(item => <option key={item.game_id} value={item.game_id}>{item.game_date} · {item.game_id} · {item.plays} candidates</option>)}</select></label><label>Source action<select disabled={loading || busy} value={action} onChange={event => {setAction(event.target.value); setPage(0);}}><option value="all">Run and pass</option><option value="run">Run intent</option><option value="pass">Pass intent</option></select></label></div>}
        {loading && <p role="status">Reading source plays…</p>}{error && <p className="oc-error" role="alert">{error}</p>}
        {result && <>
            <p>{result.total} candidates · page {page + 1}. Only penalty-free regulation plays with valid pre-snap fields are offered in this first queue.</p>
            <div className="oc-button-row"><button className="oc-secondary" disabled={busy} onClick={() => setSelected(result.plays.map(play => play.play_id))}>Select this page</button><button className="oc-secondary" disabled={busy || selected.length === 0} onClick={() => setSelected([])}>Clear selection</button><button className="oc-primary" disabled={busy || !selected.length} onClick={() => onImport(game, selected)}>Stage {selected.length} plays for review</button></div>
            {result.plays.map(play => <article className="oc-source-play" key={play.play_id}><label className="oc-review-checkbox"><input type="checkbox" disabled={busy} checked={selected.includes(play.play_id)} onChange={event => setSelected(previous => event.target.checked ? [...previous, play.play_id] : previous.filter(id => id !== play.play_id))}/><strong>Play {play.play_id} · {play.action.toUpperCase()} · {play.before.down} & {play.before.ydstogo} · {play.outcome.yards} yards</strong></label><p>{play.source.description}</p><p className="oc-inline-help">Raw source: route {play.source.raw_labels.route || 'unknown'} · formation {play.source.raw_labels.offense_formation || 'unknown'} · coverage {play.source.raw_labels.defense_coverage_type || 'unknown'}. Full concept: unlabeled.</p></article>)}
            <div className="oc-button-row"><button className="oc-secondary" disabled={busy || page === 0} onClick={() => setPage(page - 1)}>Previous source page</button><button className="oc-secondary" disabled={busy || (page + 1) * result.page_size >= result.total} onClick={() => setPage(page + 1)}>Next source page</button></div>
            <p className="oc-inline-help">Staging opens a separate review-only batch for this source game. Repeating an import preserves existing labels and does not duplicate plays. Changing pages clears the page selection.</p>
        </>}
    </section>;
}
