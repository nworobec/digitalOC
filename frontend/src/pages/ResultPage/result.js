import React, {useEffect, useState, useRef} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import './result.css';
import {fieldPosition, updatePlayHistory} from './playHistory';
import {calculateGameSeconds, calculateHalfSeconds, calculateQtrSeconds, fetchSuggestedPlay, normalizeSuggestedPlays} from '../SituationPage/situation';


const Result = () => {
    const location = useLocation();
    const navigate = useNavigate();
    const situationData = location.state;
    const [visualizationImage, setVisualizationImage] = useState(null);
    const [selectedPlayIndex, setSelectedPlayIndex] = useState(0);

    const [isUpdating, setIsUpdating] = useState(false);
    const [newDrive, setNewDrive] = useState(false);
    const updateInFlight = useRef(false);
    const previousSituation = useRef({
        yardline_100: situationData?.ydLine100 ?? (situationData ? fieldPosition(situationData.ownOppMidfield, situationData.ydLine50) : null),
        posteam: situationData?.offenseTeam,
        defteam: situationData?.defenseTeam,
    });

    // Editable state for situation details
    const [editableData, setEditableData] = useState({
        offenseTeam: situationData?.offenseTeam || '',
        defenseTeam: situationData?.defenseTeam || '',
        offensePoints: situationData?.offensePoints || '',
        defensePoints: situationData?.defensePoints || '',
        ownOppMidfield: situationData?.ownOppMidfield || '',
        ydLine50: situationData?.ydLine50 || '',
        down: situationData?.down || '',
        ydsToGo: situationData?.ydsToGo || '',
        quarter: situationData?.quarter || '',
        minutes: situationData?.minutes || '',
        seconds: situationData?.seconds || '',
        offenseTimeouts: situationData?.offenseTimeouts || '',
        defenseTimeouts: situationData?.defenseTimeouts || '',
        expYards: situationData?.expYards || '',
        suggestedPlayType: situationData?.suggestedPlayType || '',
        suggestedPlays: situationData?.suggestedPlays || [],
        playHistory: situationData?.playHistory || [], 
        actualPlayType: 'run', 
        defenseCoverage: situationData?.defenseCoverage || 'UNKNOWN'
    });

    const handleInputChange = (field, value) => {
        setEditableData(prev => ({
            ...prev,
            [field]: value
        }));
    };

    const submitUpdatedSituation = async () => {
        // Calculate necessary values
        const ydLine100 = (editableData.ownOppMidfield === "own" ? 100 - parseInt(editableData.ydLine50) : editableData.ownOppMidfield === "midfield" ? 50 : editableData.ownOppMidfield === "opp" ? parseInt(editableData.ydLine50) : undefined);
        const goalToGo = (ydLine100 === parseInt(editableData.ydsToGo) ? 1 : 0);
        const scoreDiff = parseInt(editableData.offensePoints) - parseInt(editableData.defensePoints);
        const quarterSeconds = await calculateQtrSeconds(editableData.minutes, editableData.seconds);
        const halfSeconds = await calculateHalfSeconds(editableData.quarter, editableData.minutes, editableData.seconds);
        const gameSeconds = await calculateGameSeconds(editableData.quarter, editableData.minutes, editableData.seconds);

        // Sequence Logic
        const oldYdLine100 = situationData.ydLine100 || 50; 
        const yardsGained = oldYdLine100 - ydLine100; 

        const updatedPlayHistory = [
            ...editableData.playHistory, 
            { play_type: editableData.actualPlayType, yards_gained: yardsGained }
        ];

        const currentSituation = {
            down: parseInt(editableData.down),
            ydstogo: parseInt(editableData.ydsToGo),
            yardline_100: ydLine100,
            goal_to_go: goalToGo,
            quarter_seconds_remaining: quarterSeconds,
            half_seconds_remaining: halfSeconds,
            game_seconds_remaining: gameSeconds,
            score_differential: scoreDiff,
            posteam_timeouts_remaining: parseInt(editableData.offenseTimeouts),
            defteam_timeouts_remaining: parseInt(editableData.defenseTimeouts),
            posteam: editableData.offenseTeam,
            defteam: editableData.defenseTeam,
            defense_coverage_type: editableData.defenseCoverage
        };

        let newScoutingReport = null;
        let newPlayVisualization = null;

    const submitUpdatedSituation = async (recordPlay = false) => {
        if (updateInFlight.current) return;
        updateInFlight.current = true;
        setIsUpdating(true);
        try {
            const ydLine100 = fieldPosition(editableData.ownOppMidfield, editableData.ydLine50);
            const currentSituation = {
                down: parseInt(editableData.down),
                ydstogo: parseInt(editableData.ydsToGo),
                yardline_100: ydLine100,
                goal_to_go: ydLine100 === parseInt(editableData.ydsToGo) ? 1 : 0,
                quarter_seconds_remaining: await calculateQtrSeconds(editableData.minutes, editableData.seconds),
                half_seconds_remaining: await calculateHalfSeconds(editableData.quarter, editableData.minutes, editableData.seconds),
                game_seconds_remaining: await calculateGameSeconds(editableData.quarter, editableData.minutes, editableData.seconds),
                score_differential: parseInt(editableData.offensePoints) - parseInt(editableData.defensePoints),
                posteam_timeouts_remaining: parseInt(editableData.offenseTimeouts),
                defteam_timeouts_remaining: parseInt(editableData.defenseTimeouts),
                posteam: editableData.offenseTeam,
                defteam: editableData.defenseTeam,
                defense_coverage_type: editableData.defenseCoverage,
            };
            const updatedPlayHistory = updatePlayHistory({
                previous: previousSituation.current,
                current: currentSituation,
                history: editableData.playHistory,
                playType: editableData.actualPlayType,
                recordPlay,
                newDrive,
            });
            const data = await fetchSuggestedPlay({
                current_situation: currentSituation,
                play_history: updatedPlayHistory,
            });
            const newSuggestedPlays = normalizeSuggestedPlays(data);
            if (!newSuggestedPlays.length) throw new Error('The backend returned no suggested plays.');

            const data = await response.json();
            newScoutingReport = data.scouting_report;
            newPlayVisualization = data.play_visualization;
            
            setVisualizationImage(`data:image/png;base64,${newPlayVisualization}`);
            setScoutingReport(newScoutingReport);

            // Commit the next baseline only after a successful response; retries cannot add phantom plays.
            previousSituation.current = currentSituation;
            setNewDrive(false);
            setSelectedPlayIndex(0);
            setVisualizationImage(newSuggestedPlays[0].play_visualization
                ? `data:image/png;base64,${newSuggestedPlays[0].play_visualization}` : null);
            setEditableData(prev => ({
                ...prev,
                suggestedPlayType: data.play_type,
                suggestedPlays: newSuggestedPlays,
                expYards: newSuggestedPlays[0].expected_yards ?? '',
                playVisualization: newSuggestedPlays[0].play_visualization ?? null,
                playHistory: updatedPlayHistory,
            }));
        } catch (error) {
            console.error('Error updating situation:', error);
            alert(`Could not update the situation: ${error.message}`);
        } finally {
            updateInFlight.current = false;
            setIsUpdating(false);
        }

        setEditableData(prev => ({
            ...prev,
            playVisualization: newPlayVisualization,
            playHistory: updatedPlayHistory
        }));
    };

    useEffect(() => {
        console.log("Received situation data:", situationData);
        if (situationData?.playVisualization) {

        // Set play visualization image when the page loads or when situationData changes
        if (situationData?.suggestedPlays?.[0]?.play_visualization) {
            setVisualizationImage(`data:image/png;base64,${situationData.suggestedPlays[0].play_visualization}`);
        } else if (situationData?.playVisualization) {
            setVisualizationImage(`data:image/png;base64,${situationData.playVisualization}`);
        }
    }, [situationData]);

    const formatLabel = (value) => {
        return value
            .replace(/_/g, ' ')
            .replace(/\b\w/g, char => char.toUpperCase());
    };

    const selectedPlay = editableData.suggestedPlays[selectedPlayIndex];

    const selectPlay = (play, index) => {
        setSelectedPlayIndex(index);
        setVisualizationImage(
            play.play_visualization
                ? `data:image/png;base64,${play.play_visualization}`
                : null
        );
    };

    const renderPlayData = (playData = {}) => {
        return Object.entries(playData)
            .filter(([, value]) => value !== null && value !== undefined && value !== '')
            .map(([key, value]) => (
                <div className="play-data-row" key={key}>
                    <span>{formatLabel(key)}:</span>
                    <strong>{value}</strong>
                </div>
            ));
    };


    if (!situationData) {
        return (
            <div className="result-container">
                <h1>No situation data available</h1>
                <button onClick={() => navigate('/situation')}>Go to Situation Page</button>
            </div>
        );
    }

    return (
        <div className="result-container">
            <button className="back-button" onClick={() => navigate('/situation')}>
                ← Back to Situation
            </button>
            
            <h1 className="result-title">SITUATION RESULT</h1>
            
            <div className="result-content">
                <div className="left-column">
                    <div className="left-section">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                            <h2 style={{ margin: 0 }}>Situation Details:</h2>
                            <div>
                                <button className="update-button" disabled={isUpdating} onClick={() => submitUpdatedSituation(false)}>
                                    Refresh Suggestions
                                </button>
                                <button className="update-button" disabled={isUpdating} onClick={() => submitUpdatedSituation(true)}>
                                    Record Play & Update
                                </button>
                            </div>
                        </div>
                        <label>
                            <input type="checkbox" checked={newDrive} onChange={event => setNewDrive(event.target.checked)} />
                            Start a new drive (clear play history)
                        </label>
                        <p>Recorded plays this drive: {editableData.playHistory.length}</p>
                        <div className="details-list">
                        <div className="detail-item">
                            <span className="detail-label">Offense:</span>
                            <input 
                                type="text" 
                                className="detail-input" 
                                value={editableData.offenseTeam}
                                onChange={(e) => handleInputChange('offenseTeam', e.target.value)}
                                maxLength={3}
                            />
                        </div>
                        <div className="detail-item">
                            <span className="detail-label">Defense:</span>
                            <input 
                                type="text" 
                                className="detail-input" 
                                value={editableData.defenseTeam}
                                onChange={(e) => handleInputChange('defenseTeam', e.target.value)}
                                maxLength={3}
                            />
                        </div>
                        <div className="detail-item">
                            <span className="detail-label">Defensive Coverage:</span>
                            <select 
                                className="detail-input" 
                                value={editableData.defenseCoverage}
                                onChange={(e) => handleInputChange('defenseCoverage', e.target.value)}
                                style={{ width: '160px', fontSize: '16px' }}
                            >
                                <option value="UNKNOWN">Unknown</option>
                                <option value="COVER_0">Cover 0</option>
                                <option value="COVER_1">Cover 1</option>
                                <option value="COVER_2">Cover 2</option>
                                <option value="COVER_3">Cover 3</option>
                                <option value="COVER_4">Cover 4</option>
                                <option value="COVER_6">Cover 6</option>
                                <option value="2_MAN">2-Man</option>
                            </select>
                        </div>
                        <div className="detail-item">
                            <span className="detail-label">Score:</span>
                            <div style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
                                <input 
                                    type="number" 
                                    className="detail-input score-input" 
                                    value={editableData.offensePoints}
                                    onChange={(e) => handleInputChange('offensePoints', e.target.value)}
                                    style={{ width: '60px' }}
                                />
                                <span className="detail-value">-</span>
                                <input 
                                    type="number" 
                                    className="detail-input score-input" 
                                    value={editableData.defensePoints}
                                    onChange={(e) => handleInputChange('defensePoints', e.target.value)}
                                    style={{ width: '60px' }}
                                />
                            </div>
                        </div>
                        <div className="detail-item">
                            <span className="detail-label">Field Position:</span>
                            <div style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
                                <select 
                                    className="detail-input" 
                                    value={editableData.ownOppMidfield}
                                    onChange={(e) => handleInputChange('ownOppMidfield', e.target.value)}
                                    style={{ width: '100px' }}
                                >
                                    <option value="own">OWN</option>
                                    <option value="opp">OPP</option>
                                    <option value="midfield">MIDFIELD</option>
                                </select>
                                {editableData.ownOppMidfield !== 'midfield' && (
                                    <input 
                                        type="number" 
                                        className="detail-input" 
                                        value={editableData.ydLine50}
                                        onChange={(e) => handleInputChange('ydLine50', e.target.value)}
                                        style={{ width: '60px' }}
                                        min="1"
                                        max="49"
                                    />
                                )}
                            </div>
                        </div>
                        <div className="detail-item" style={{ border: '2px dashed #ff69ff' }}>
                            <span className="detail-label">Completed Play Type:</span>
                            <div style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
                                <select 
                                    className="detail-input" 
                                    value={editableData.actualPlayType}
                                    onChange={(e) => handleInputChange('actualPlayType', e.target.value)}
                                    style={{ width: '120px' }}
                                >
                                    <option value="run">RUN</option>
                                    <option value="pass">PASS</option>
                                </select>
                            </div>
                        </div>
                        <div className="detail-item">
                            <span className="detail-label">Down & Distance:</span>
                            <div style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
                                <input 
                                    type="number" 
                                    className="detail-input" 
                                    value={editableData.down}
                                    onChange={(e) => handleInputChange('down', e.target.value)}
                                    style={{ width: '60px' }}
                                    min="1"
                                    max="4"
                                />
                                <span className="detail-value">&</span>
                                <input 
                                    type="number" 
                                    className="detail-input" 
                                    value={editableData.ydsToGo}
                                    onChange={(e) => handleInputChange('ydsToGo', e.target.value)}
                                    style={{ width: '60px' }}
                                />
                            </div>
                        </div>
                        <div className="detail-item">
                            <span className="detail-label">Time:</span>
                            <div style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
                                <span className="detail-value">Q</span>
                                <input 
                                    type="text" 
                                    className="detail-input" 
                                    value={editableData.quarter}
                                    onChange={(e) => handleInputChange('quarter', e.target.value)}
                                    style={{ width: '50px' }}
                                />
                                <span className="detail-value">-</span>
                                <input 
                                    type="number" 
                                    className="detail-input" 
                                    value={editableData.minutes}
                                    onChange={(e) => handleInputChange('minutes', e.target.value)}
                                    style={{ width: '50px' }}
                                    min="0"
                                    max="15"
                                />
                                <span className="detail-value">:</span>
                                <input 
                                    type="number" 
                                    className="detail-input" 
                                    value={editableData.seconds}
                                    onChange={(e) => handleInputChange('seconds', e.target.value)}
                                    style={{ width: '50px' }}
                                    min="0"
                                    max="59"
                                />
                            </div>
                        </div>
                        <div className="detail-item">
                            <span className="detail-label">Timeouts:</span>
                            <div style={{ display: 'flex', gap: '5px', alignItems: 'center' }}>
                                <span className="detail-value">OFF:</span>
                                <input 
                                    type="number" 
                                    className="detail-input" 
                                    value={editableData.offenseTimeouts}
                                    onChange={(e) => handleInputChange('offenseTimeouts', e.target.value)}
                                    style={{ width: '50px' }}
                                    min="0"
                                    max="3"
                                />
                                <span className="detail-value">DEF:</span>
                                <input 
                                    type="number" 
                                    className="detail-input" 
                                    value={editableData.defenseTimeouts}
                                    onChange={(e) => handleInputChange('defenseTimeouts', e.target.value)}
                                    style={{ width: '50px' }}
                                    min="0"
                                    max="3"
                                />
                            </div>
                        </div>
                    </div>
                    </div>

                    <div className="left-section">
                        <h2>Raw Situation Array:</h2>
                        <pre className="situation-output">{situationData.situationArray}</pre>
                    </div>
                </div>

                <div className="right-column">
                    <div className="visualization-container">
                        <h2>Top Play Visualization:</h2>
                        <img src={visualizationImage} alt="Play Visualization" className="visualization-image" />
                        <br />
                        
                        {/* NEW SCOUTING DASHBOARD */}
                        {scoutingReport && (
                            <div className="scouting-dashboard" style={{ marginTop: '20px', textAlign: 'left', background: '#000000', padding: '15px', borderRadius: '8px' }}>
                                <h2>Opponent Tendencies</h2>
                                
                                <div style={{ display: 'flex', justifyContent: 'space-around', marginBottom: '15px' }}>
                                    <div style={{ padding: '10px', background: scoutingReport.pbp_tendency.primary_tendency === 'PASS' ? '#d4edda' : 'transparent', borderRadius: '5px' }}>
                                        <strong>Pass Probability:</strong> {(scoutingReport.pbp_tendency.pass_probability * 100).toFixed(1)}%
                                    </div>
                                    <div style={{ padding: '10px', background: scoutingReport.pbp_tendency.primary_tendency === 'RUN' ? '#d4edda' : 'transparent', borderRadius: '5px' }}>
                                        <strong>Run Probability:</strong> {(scoutingReport.pbp_tendency.run_probability * 100).toFixed(1)}%
                                    </div>
                                </div>

                                {scoutingReport.pbp_tendency.primary_tendency === 'PASS' && scoutingReport.pass_tendencies && (
                                    <div className="pass-tendencies">
                                        <h3>Top Pass Routes</h3>
                                        <ul>
                                            {scoutingReport.pass_tendencies.route.map((r, i) => (
                                                <li key={i}>{r.label.toUpperCase()} - {(r.probability * 100).toFixed(1)}%</li>
                                            ))}
                                        </ul>
                                        <h3>Top Target Areas</h3>
                                        <ul>
                                            {scoutingReport.pass_tendencies.pass_target_area.map((t, i) => (
                                                <li key={i}>{t.label.replace('_', ' ').toUpperCase()} - {(t.probability * 100).toFixed(1)}%</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {scoutingReport.pbp_tendency.primary_tendency === 'RUN' && scoutingReport.run_tendencies && (
                                    <div className="run-tendencies">
                                        <h3>Top Run Lanes</h3>
                                        <ul>
                                            {scoutingReport.run_tendencies.run_tendencies.map((r, i) => (
                                                <li key={i}>{r.run_lane.replace('_', ' ').toUpperCase()} - {(r.probability * 100).toFixed(1)}%</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        )}
                        <h2>Suggested Plays:</h2>
                        <div className="play-options">
                            {editableData.suggestedPlays.length > 0 ? (
                                editableData.suggestedPlays.map((play, index) => (
                                    <button
                                        type="button"
                                        key={`${play.play_type}-${play.rank}`}
                                        className={`play-option ${selectedPlayIndex === index ? 'active' : ''}`}
                                        onClick={() => selectPlay(play, index)}
                                    >
                                        <span>#{play.rank} {play.play_type?.toUpperCase()}</span>
                                        <strong>{play.expected_yards}</strong>
                                    </button>
                                ))
                            ) : (
                                <p className="no-plays-message">No play suggestions returned yet.</p>
                            )}
                        </div>

                        {selectedPlay && (
                            <div className="selected-play-details">
                                <h2>Play #{selectedPlay.rank}</h2>
                                {renderPlayData(selectedPlay.play_data)}
                            </div>
                        )}

                        <h2>Play Visualization:</h2>
                        {visualizationImage ? (
                            <img src={visualizationImage} alt="Play Visualization" className="visualization-image" />
                        ) : (
                            <p className="no-plays-message">No visualization available for this play.</p>
                        )}
                        <br />
                        <h2>Expected Points Added: {editableData.expYards}</h2>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Result;
