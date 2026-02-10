import React, {useEffect, useState} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import './result.css';
import Sitaution, {calculateGameSeconds, calculateHalfSeconds, calculateQtrSeconds} from '../SituationPage/situation';


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
        defenseTimeouts: situationData?.defenseTimeouts || ''
    });

    const handleInputChange = (field, value) => {
        setEditableData(prev => ({
            ...prev,
            [field]: value
        }));
    };

    const submitUpdatedSituation = async () => {

        console.log("DEBUG, quarter, minutes, seconds:", editableData.quarter, editableData.minutes, editableData.seconds);
        console.log("Those values should be parsed as ints correctly in calculation functions.");

        // Recalculate necessary values
        const ydLine100 = (editableData.ownOppMidfield === "own" ? 100 - parseInt(editableData.ydLine50) : editableData.ownOppMidfield === "midfield" ? 50 : editableData.ownOppMidfield === "opp" ? parseInt(editableData.ydLine50) : undefined);
        const goalToGo = (ydLine100 === parseInt(editableData.ydsToGo) ? 1 : 0);
        const scoreDiff = parseInt(editableData.offensePoints) - parseInt(editableData.defensePoints);
        const quarterSeconds = await calculateQtrSeconds(editableData.minutes, editableData.seconds);
        const halfSeconds = await calculateHalfSeconds(editableData.quarter, editableData.minutes, editableData.seconds);
        const gameSeconds = await calculateGameSeconds(editableData.quarter, editableData.minutes, editableData.seconds);
        
        /*
            Situation array should follow this order:
            const situationArray = `${down}, ${ydsToGo}, ${ydLine100}, ${goalToGo}, 
                                    ${qtrSeconds}, ${halfSeconds}, ${gameSeconds}, ${scoreDiff}, 
                                    ${finalOffenseTimeouts}, ${finalDefenseTimeouts}, ${offenseTeam}, ${defenseTeam}`;
        */
        
        // Create updated situation array
        const updatedSituationArray = [
            editableData.down, editableData.ydsToGo, ydLine100, goalToGo, quarterSeconds, halfSeconds, 
            gameSeconds, scoreDiff, parseInt(editableData.offenseTimeouts), parseInt(editableData.defenseTimeouts), 
            editableData.offenseTeam, editableData.defenseTeam
        ].join(',');

        // First, send the updated situation to the backend to generate new visualization
        fetch(`https://glowing-giggle-6954gr9qpw9p34wwv-5000.app.github.dev//suggestPlay/${updatedSituationArray}`, { method: 'GET' })
            .then(response => {
                if (response.ok) {
                    // After the backend generates the new visualization, fetch it
                    return fetch(`https://glowing-giggle-6954gr9qpw9p34wwv-5000.app.github.dev/playVisualization?t=${Date.now()}`, { method: 'GET' });
                }   //      added timestamp to prevent caching of the image   
                throw new Error('Failed to generate play suggestion');
            })
            .then(response => response.blob())
            .then(imageBlob => {
            const imageObjectURL = URL.createObjectURL(imageBlob);
            setVisualizationImage(imageObjectURL);
            
            // update the display text by navigating with the new state
            navigate('/result', {
                state: {
                    ...editableData,
                    situationArray: updatedSituationArray
                }
            }, { replace: true });
        })
            .catch(error => {
                console.error("Error updating play visualization:", error);
                alert("Failed to update. Check backend terminal for errors.");
        });
};

        
    useEffect(() => {
        console.log("Received situation data:", situationData);

        // Fetch the play visualization image from the Flask backend
        fetch('https://glowing-giggle-6954gr9qpw9p34wwv-5000.app.github.dev//playVisualization', { method: 'GET' })
            .then(response => response.blob())
            .then(imageBlob => {
                // Create a local URL of the image blob and set it as the visualization image source
                const imageObjectURL = URL.createObjectURL(imageBlob);
                setVisualizationImage(imageObjectURL);
            })
            .catch(error => {
                console.error("Error fetching play visualization:", error);
            });

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
                        
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Result;
