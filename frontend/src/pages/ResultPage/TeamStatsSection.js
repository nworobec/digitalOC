import React, {useEffect, useState} from 'react';
import './result.css';

export default function TeamStatsSection({offenseTeam, defenseTeam, className = ''}) {
    const [teamStats, setTeamStats] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const offense = (offenseTeam || '').trim().toUpperCase();
    const defense = (defenseTeam || '').trim().toUpperCase();

    useEffect(() => {
        if (!offense || !defense) {
            setTeamStats(null);
            setError('');
            setLoading(false);
            return undefined;
        }

        const controller = new AbortController();
        const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:5000';
        const params = new URLSearchParams({offense, defense});
        setTeamStats(null);
        setError('');
        setLoading(true);

        fetch(`${backendUrl}/teamStats?${params.toString()}`, {signal: controller.signal})
            .then(async response => {
                if (!response.ok) {
                    const errorBody = await response.json().catch(() => ({}));
                    throw new Error(errorBody.error || `Stats request failed (${response.status})`);
                }
                return response.json();
            })
            .then(data => {
                if (!controller.signal.aborted) setTeamStats(data);
            })
            .catch(failure => {
                if (!controller.signal.aborted) setError(failure.message);
            })
            .finally(() => {
                if (!controller.signal.aborted) setLoading(false);
            });

        return () => controller.abort();
    }, [offense, defense]);

    const renderTeamStatsPanel = (data, isDefense) => {
        const passing = data.passing;
        const rushing = data.rushing;
        const metrics = [
            {label: isDefense ? 'Pass Yards Allowed' : 'Passing Yards', value: passing.yards},
            {label: isDefense ? 'Pass Completions Allowed' : 'Pass Completions', value: passing.completions},
            {label: isDefense ? 'Pass Attempts Faced' : 'Pass Attempts', value: passing.attempts},
            {label: isDefense ? 'Completion Rate Allowed' : 'Completion Rate', value: `${passing.completionPct}%`},
            {label: isDefense ? 'Pass TDs Allowed' : 'Passing TDs', value: passing.touchdowns},
            {label: isDefense ? 'Interceptions' : 'Interceptions Thrown', value: passing.interceptions},
            {label: isDefense ? 'Sacks' : 'Sacks Allowed', value: passing.sacks},
            {label: isDefense ? 'Yards per Pass Allowed' : 'Yards per Pass', value: passing.yardsPerAttempt},
            {label: isDefense ? 'Rush Yards Allowed' : 'Rushing Yards', value: rushing.yards},
            {label: isDefense ? 'Rush Attempts Faced' : 'Rush Attempts', value: rushing.attempts},
            {label: isDefense ? 'Rush TDs Allowed' : 'Rushing TDs', value: rushing.touchdowns},
            {label: isDefense ? 'Yards per Carry Allowed' : 'Yards per Carry', value: rushing.yardsPerCarry},
        ];
        const maxLaneAttempts = Math.max(1, ...data.lanes.map(lane => lane.attempts));

        return (
            <section className={`team-stats-panel ${isDefense ? 'defense-stats' : 'offense-stats'}`}>
                <header className="team-stats-heading">
                    <div>
                        <span className="team-stats-kicker">{isDefense ? 'DEFENSE' : 'OFFENSE'} · 2024 SEASON</span>
                        <h3>{data.team} {isDefense ? 'Defense' : 'Offense'}</h3>
                    </div>
                    <span className="team-play-count">{data.totalPlays.toLocaleString()} plays</span>
                </header>

                <div className="team-play-mix" aria-label={`${data.runRate}% run plays and ${data.passRate}% pass plays`}>
                    <div className="play-mix-bar">
                        <span className="run-mix" style={{width: `${data.runRate}%`}} />
                        <span className="pass-mix" style={{width: `${data.passRate}%`}} />
                    </div>
                    <div className="play-mix-labels">
                        <span>Run <strong>{data.runRate}%</strong></span>
                        <span>Pass <strong>{data.passRate}%</strong></span>
                    </div>
                </div>

                <div className="team-stat-grid">
                    {metrics.map(metric => (
                        <div className="team-stat-card" key={metric.label}>
                            <span>{metric.label}</span>
                            <strong>{typeof metric.value === 'number' ? metric.value.toLocaleString() : metric.value}</strong>
                        </div>
                    ))}
                </div>

                <div className="team-breakdown">
                    <h4>{isDefense ? 'Rushing Defense by Gap' : 'Rushing by Gap'}</h4>
                    <div className="breakdown-grid rushing-breakdown">
                        {data.lanes.map(lane => (
                            <article className="breakdown-card" key={lane.key}>
                                <h5>{lane.label}</h5>
                                <div className="breakdown-bar">
                                    <span style={{width: `${(lane.attempts / maxLaneAttempts) * 100}%`}} />
                                </div>
                                <strong>{lane.attempts} {isDefense ? 'attempts faced' : 'attempts'}</strong>
                                <span>{lane.yards.toLocaleString()} yards · {lane.touchdowns} TD</span>
                                <span>{lane.yardsPerCarry} YPC{isDefense ? ' allowed' : ''}</span>
                            </article>
                        ))}
                    </div>
                </div>

                <div className="team-breakdown">
                    <h4>{isDefense ? 'Passing Defense by Field Zone' : 'Passing by Field Zone'}</h4>
                    <div className="breakdown-grid passing-breakdown">
                        {data.zones.map(zone => (
                            <article className="breakdown-card" key={zone.key}>
                                <h5>{zone.label}</h5>
                                <strong>{zone.completions}/{zone.attempts} completions</strong>
                                <span>{zone.completionPct}% · {zone.yards.toLocaleString()} yards</span>
                                <span>{zone.touchdowns} TD · {zone.interceptions} INT</span>
                                <span>{zone.yardsPerAttempt} YPA{isDefense ? ' allowed' : ''}</span>
                                <span>{zone.averageAirYards} average air yards</span>
                            </article>
                        ))}
                    </div>
                </div>
            </section>
        );
    };

    return (
        <section className={`team-stats-section ${className}`.trim()}>
            <div className="team-stats-section-heading">
                <div>
                    <span className="team-stats-kicker">PLAY-BY-PLAY BREAKDOWN</span>
                    <h2>Team Performance</h2>
                </div>
                <p>2024 regular season and postseason data</p>
            </div>
            {!offense || !defense ? (
                <p className="team-stats-message">Choose an offense and defense to view team performance.</p>
            ) : loading ? (
                <p className="team-stats-message" role="status">Loading team performance data…</p>
            ) : error ? (
                <p className="team-stats-message team-stats-error" role="alert">Unable to load team stats: {error}</p>
            ) : teamStats ? (
                <div className="team-stats-grid">
                    {renderTeamStatsPanel(teamStats.offense, false)}
                    {renderTeamStatsPanel(teamStats.defense, true)}
                </div>
            ) : null}
        </section>
    );
}
