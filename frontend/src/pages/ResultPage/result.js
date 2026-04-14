import React, {useEffect, useState} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import './result.css';
import {calculateGameSeconds, calculateHalfSeconds, calculateQtrSeconds} from '../SituationPage/situation';


const Result = () => {
    const location = useLocation();
    const navigate = useNavigate();
    const situationData = location.state;
    const [visualizationImage, setVisualizationImage] = useState(null);

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
        playHistory: situationData?.playHistory || [], 
        actualPlayType: 'run', // lets the user select what play actually ran
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

        // --- SEQUENCE LOGIC ---
        // Calculate yards gained by comparing the old yardline to the new yardline
        // (this logic assumes the team hasn't crossed midfield/changed possession for simplicity right now)
        const oldYdLine100 = situationData.ydLine100 || 50; 
        const yardsGained = oldYdLine100 - ydLine100; 

        // Add the completed play to our history array
        const updatedPlayHistory = [
            ...editableData.playHistory, 
            { play_type: editableData.actualPlayType, yards_gained: yardsGained }
        ];

        // Format for Flask
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

        let newExpYards = null;
        let newPlayVisualization = null;

        try {
            const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/suggestPlay`, { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    current_situation: currentSituation,
                    play_history: updatedPlayHistory
                })
            });

            const data = await response.json();
            newExpYards = data.expected_yards;
            newPlayVisualization = data.play_visualization;
            setVisualizationImage(`data:image/png;base64,${newPlayVisualization}`);

        } catch (error) {
            console.error("Error updating play visualization:", error);
        }

        // Update local state
        setEditableData(prev => ({
            ...prev,
            expYards: newExpYards,
            playVisualization: newPlayVisualization,
            playHistory: updatedPlayHistory
        }));
    };

    useEffect(() => {
        console.log("Received situation data:", situationData);

        // Set play visualization image when the page loads or when situationData changes
        if (situationData?.playVisualization) {
            setVisualizationImage(`data:image/png;base64,${situationData.playVisualization}`);
        }

    }, [situationData]);


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
                            <button className="update-button" onClick={submitUpdatedSituation}>
                                Update Situation
                            </button>
                        </div>
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
                            <span className="detail-label">Coverage:</span>
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
                        <div className="detail-item">
                            <span className="detail-label">Play Type:</span>
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
                        <h2>Play Visualization:</h2>
                        <img src={visualizationImage} alt="Play Visualization" className="visualization-image" />
                        <br />
                        <h2>Expected Yards: {editableData.expYards}</h2>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Result;
