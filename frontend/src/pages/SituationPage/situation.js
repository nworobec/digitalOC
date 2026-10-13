import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import TeamDropdownMenu from '../../components/team_dropdown';
import './situation.css';

// Import team logos
import ARILogo from '../../logos/ARI.png';
import ATLLogo from '../../logos/ATL.png';
import BALLogo from '../../logos/BAL.png';
import BUFLogo from '../../logos/BUF.png';
import CARLogo from '../../logos/CAR.png';
import CHILogo from '../../logos/CHI.png';
import CINLogo from '../../logos/CIN.png';
import CLELogo from '../../logos/CLE.png';
import DALLogo from '../../logos/DAL.png';
import DENLogo from '../../logos/DEN.png';
import DETLogo from '../../logos/DET.png';
import GBLogo from '../../logos/GB.png';
import HOULogo from '../../logos/HOU.png';
import INDLogo from '../../logos/IND.png';
import JAXLogo from '../../logos/JAX.png';
import KCLogo from '../../logos/KC.png';
import LACLogo from '../../logos/LAC.png';
import LARLogo from '../../logos/LAR.png';
import LVLogo from '../../logos/LV.png';
import MIALogo from '../../logos/MIA.png';
import MINLogo from '../../logos/MIN.png';
import NELogo from '../../logos/NE.png';
import NOLogo from '../../logos/NO.png';
import NYGLogo from '../../logos/NYG.png';
import NYJLogo from '../../logos/NYJ.png';
import PHILogo from '../../logos/PHI.png';
import PITLogo from '../../logos/PIT.png';
import SEALogo from '../../logos/SEA.png';
import SFLogo from '../../logos/SF.png';
import TBLogo from '../../logos/TB.png';
import TENLogo from '../../logos/TEN.png';
import WASLogo from '../../logos/WAS.png';

// Below are functions to calculate seconds remaining in quarter, half, and game
export async function calculateQtrSeconds(minutes, seconds) {
    seconds = parseInt(seconds);
    minutes = parseInt(minutes);

    return seconds + (minutes * 60); 
}

export async function calculateHalfSeconds(qtr, minutes, seconds) {
    seconds = parseInt(seconds);
    minutes = parseInt(minutes);

    if (qtr === '1' || qtr === '3') seconds += 900; 
    return seconds + (minutes * 60); 
}

export async function calculateGameSeconds(qtr, minutes, seconds) {
    seconds = parseInt(seconds);
    minutes = parseInt(minutes);

    if (qtr === '3') seconds += 900; 
    else if (qtr === '2') seconds += 1800; 
    else if (qtr === '1') seconds += 2700; 
    return seconds + (minutes * 60); 
}

export async function fetchSuggestedPlay(payload) {
    let lastError = null;
    const REACT_APP_BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:5000';

    try {
        const response = await fetch(`${REACT_APP_BACKEND_URL}/suggestPlay`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const requestId = response.headers.get('X-Request-ID');
        console.info('suggestPlay completed', { requestId, status: response.status });
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Request ${requestId || 'unknown'} returned ${response.status}: ${errorText}`);
        }

        return await response.json();
    } catch (error) {
        lastError = error;
        console.warn(`Could not reach backend at ${REACT_APP_BACKEND_URL}:`, error);
    }

    throw new Error(`Could not reach the backend at ${REACT_APP_BACKEND_URL}. Last error: ${lastError?.message || 'unknown error'}`);
}

export const normalizeSuggestedPlays = (data) => {
    if (Array.isArray(data)) {
        return data;
    }

    const plays = data?.plays || data?.play_outputs || data?.outputs || data?.suggestions || data?.suggested_plays;
    if (Array.isArray(plays)) {
        return plays;
    }

    if (data?.expected_yards || data?.play_visualization || data?.play_data) {
        return [{
            rank: 1,
            play_type: data.play_type,
            expected_yards: data.expected_yards,
            play_visualization: data.play_visualization,
            play_data: data.play_data || {}
        }];
    }

    return [];
};

const Situation = () => {
    const navigate = useNavigate();
    const secondsInputRef = useRef(null);
    // Team attributes
    const [offenseTeam, setOffenseTeam] = useState("");
    const [defenseTeam, setDefenseTeam] = useState("");
    
    // Team selector modal state
    const [showTeamSelector, setShowTeamSelector] = useState(false);
    const [teamSearchQuery, setTeamSearchQuery] = useState('');
    const [selectorType, setSelectorType] = useState(''); // 'offense' or 'defense'

    // Down and distance attributes
    const [down, setDown] = useState("");
    const [ydsToGo, setYdsToGo] = useState();
    const [ownOppMidfield, setOwnOppMidfield] = useState(""); // Defines whether the offense is in their own or opponent's territory or midfield
    const [ydLine50, setYdLine50] = useState(); // Yard line relative to own/opp territory (ignored if midfield selected)

    // Score attributes
    const [offensePoints, setOffensePoints] = useState(); 
    const [defensePoints, setDefensePoints] = useState();

    // Time attributes
    /* If OT is selected for quarter, the qtr/half/game seconds will be calculated as if it was the 4th quarter */
    const [quarter, setQuarter] = useState(""); 
    const [minutes, setMinutes] = useState(); 
    const [seconds, setSeconds] = useState(); 

    // Timeout attributes
    const [offenseTimeouts, setOffenseTimeouts] = useState("0"); 
    const [defenseTimeouts, setDefenseTimeouts] = useState("0");
    const [defenseCoverage, setDefenseCoverage] = useState("UNKNOWN");

    // Cycling tips state
    const [currentTipIndex, setCurrentTipIndex] = useState(0);
    
    // Team data with logos
    const teams = [
        { abbr: 'ARI', logo: ARILogo },
        { abbr: 'ATL', logo: ATLLogo },
        { abbr: 'BAL', logo: BALLogo },
        { abbr: 'BUF', logo: BUFLogo },
        { abbr: 'CAR', logo: CARLogo },
        { abbr: 'CHI', logo: CHILogo },
        { abbr: 'CIN', logo: CINLogo },
        { abbr: 'CLE', logo: CLELogo },
        { abbr: 'DAL', logo: DALLogo },
        { abbr: 'DEN', logo: DENLogo },
        { abbr: 'DET', logo: DETLogo },
        { abbr: 'GB', logo: GBLogo },
        { abbr: 'HOU', logo: HOULogo },
        { abbr: 'IND', logo: INDLogo },
        { abbr: 'JAX', logo: JAXLogo },
        { abbr: 'KC', logo: KCLogo },
        { abbr: 'LAC', logo: LACLogo },
        { abbr: 'LAR', logo: LARLogo },
        { abbr: 'LV', logo: LVLogo },
        { abbr: 'MIA', logo: MIALogo },
        { abbr: 'MIN', logo: MINLogo },
        { abbr: 'NE', logo: NELogo },
        { abbr: 'NO', logo: NOLogo },
        { abbr: 'NYG', logo: NYGLogo },
        { abbr: 'NYJ', logo: NYJLogo },
        { abbr: 'PHI', logo: PHILogo },
        { abbr: 'PIT', logo: PITLogo },
        { abbr: 'SEA', logo: SEALogo },
        { abbr: 'SF', logo: SFLogo },
        { abbr: 'TB', logo: TBLogo },
        { abbr: 'TEN', logo: TENLogo },
        { abbr: 'WAS', logo: WASLogo },
    ];
    
    // Team colors data
    const teamColors = {
        'ARI': { primary: '#97233f', secondary: '#000000' },
        'ATL': { primary: '#a71930', secondary: '#000000' },
        'BAL': { primary: '#241773', secondary: '#9e7c0c' },
        'BUF': { primary: '#00338d', secondary: '#c60c30' },
        'CAR': { primary: '#0085ca', secondary: '#000000' },
        'CHI': { primary: '#0b162a', secondary: '#c83803' },
        'CIN': { primary: '#fb4f14', secondary: '#000000' },
        'CLE': { primary: '#ff3c00', secondary: '#311d00' },
        'DAL': { primary: '#002244', secondary: '#b0b7bc' },
        'DEN': { primary: '#002244', secondary: '#fb4f14' },
        'DET': { primary: '#0076b6', secondary: '#b0b7bc' },
        'GB': { primary: '#203731', secondary: '#ffb612' },
        'HOU': { primary: '#03202f', secondary: '#a71930' },
        'IND': { primary: '#002c5f', secondary: '#fffff8' },
        'JAX': { primary: '#000000', secondary: '#006778' },
        'KC': { primary: '#e31837', secondary: '#ffb612' },
        'LAC': { primary: '#0080c6', secondary: '#ffc20e' },
        'LAR': { primary: '#032287ff', secondary: '#fdfd00ff' },
        'LV': { primary: '#000000', secondary: '#a5acaf' },
        'MIA': { primary: '#008e97', secondary: '#fc4c02' },
        'MIN': { primary: '#4f2683', secondary: '#ffc62f' },
        'NE': { primary: '#002244', secondary: '#c60c30' },
        'NO': { primary: '#d3bc8d', secondary: '#000000' },
        'NYG': { primary: '#0b2265', secondary: '#a71930' },
        'NYJ': { primary: '#003f2d', secondary: '#fffff8' },
        'PHI': { primary: '#18675b', secondary: '#a5acaf' },
        'PIT': { primary: '#000000', secondary: '#ffb612' },
        'SEA': { primary: '#002244', secondary: '#69be28' },
        'SF': { primary: '#d50a0a', secondary: '#b3995d' },
        'TB': { primary: '#d50a0a', secondary: '#34302b' },
        'TEN': { primary: '#002244', secondary: '#4b92db' },
        'WAS': { primary: '#5a1414', secondary: '#ffbc12' }
    };
    // Function to handle clicking on the visual field
    const handleFieldClick = (e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const percentage = Math.round((clickX / rect.width) * 100);
        
        if (percentage === 50) {
            setOwnOppMidfield('midfield');
            setYdLine50('50');
        } else if (percentage < 50) {
            setOwnOppMidfield('own');
            // Ensure it doesn't go below 1
            setYdLine50(Math.max(1, percentage).toString());
        } else {
            setOwnOppMidfield('opp');
            // Convert from 51-99 range back to 49-1 range
            setYdLine50(Math.max(1, 100 - percentage).toString());
        }
    };
    // Get team logo by abbreviation
    const getTeamLogo = (abbr) => {
        const team = teams.find(t => t.abbr === abbr);
        return team ? team.logo : null;
    };
    
    // Get team gradient background
    const getTeamGradient = (abbr) => {
        const colors = teamColors[abbr];
        if (colors) {
            // Convert hex to rgba with 0.85 opacity and favor primary color
            const hexToRgba = (hex, opacity) => {
                const r = parseInt(hex.slice(1, 3), 16);
                const g = parseInt(hex.slice(3, 5), 16);
                const b = parseInt(hex.slice(5, 7), 16);
                return `rgba(${r}, ${g}, ${b}, ${opacity})`;
            };
            return `linear-gradient(135deg, ${hexToRgba(colors.primary, 0.5)} 38%, ${hexToRgba(colors.secondary, 0.44)} 100%)`;
        }
        return 'rgba(20, 30, 60, 0.8)'; // Default background
    };
    
    // Get 50/50 split gradient for teams card
    const getTeamsCardGradient = () => {
        if (offenseTeam && defenseTeam) {
            const offenseColor = teamColors[offenseTeam]?.primary;
            const defenseColor = teamColors[defenseTeam]?.primary;
            if (offenseColor && defenseColor) {
                const hexToRgba = (hex, opacity) => {
                    const r = parseInt(hex.slice(1, 3), 16);
                    const g = parseInt(hex.slice(3, 5), 16);
                    const b = parseInt(hex.slice(5, 7), 16);
                    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
                };
                return `linear-gradient(90deg, ${hexToRgba(offenseColor, 0.5)}, ${hexToRgba(defenseColor, 0.5)})`;
            }
        }
        return 'rgba(40, 30, 70, 0.9)'; // Default background
    };

    // Tips array
    const tips = [
        "Tip: use up/down arrows and tab for a smoother experience!",
        "Tip: make sure to update the timeouts located under the score!"
    ];

    // Cycle tips every 5 seconds
    useEffect(() => {
        const interval = setInterval(() => {
            setCurrentTipIndex((prevIndex) => (prevIndex + 1) % tips.length);
        }, 5000);

        return () => clearInterval(interval);
    }, [tips.length]);
    
    // Open team selector
    const openTeamSelector = (type) => {
        setSelectorType(type);
        setTeamSearchQuery(''); // Clear out any old searches
        setShowTeamSelector(true);
    };
    
    // Select team from modal
    const selectTeam = (abbr) => {
        if (selectorType === 'offense') {
            setOffenseTeam(abbr);
        } else if (selectorType === 'defense') {
            setDefenseTeam(abbr);
        }
        setShowTeamSelector(false);
        setTeamSearchQuery(''); // Clear the search when done
    };
    
    // Calculate ball marker position (0-100%) based on field position
    const calculateBallPosition = () => {
        if (ownOppMidfield === 'midfield') {
            return 50; // Center of field
        } else if (ownOppMidfield === 'own' && ydLine50) {
            // Own territory: own 1 = 1%, own 49 = 49%
            return parseInt(ydLine50);
        } else if (ownOppMidfield === 'opp' && ydLine50) {
            // Opponent territory: opp 49 = 51%, opp 1 = 99%
            return 100 - parseInt(ydLine50);
        }
        return 50; // Default to center
    };

    async function submitSituation() {
        // Default timeouts to 0 if not selected
        const finalOffenseTimeouts = offenseTimeouts || '0';
        const finalDefenseTimeouts = defenseTimeouts || '0';
        
        // Ensure no required fields are left blank
        if (!offenseTeam || !defenseTeam || !down || !ydsToGo || !ownOppMidfield || (ownOppMidfield !== 'midfield' && !ydLine50) || offensePoints === '' ||
         offensePoints === undefined || defensePoints === '' || defensePoints === undefined || !quarter || minutes === '' || minutes === undefined || seconds === '' || seconds === undefined) {
            alert("Please fill out all required fields before submitting the situation.");
            return;
        }

        if (offenseTeam === defenseTeam) {
            alert("Please select different teams for the offense and defense."); 
            return; 
        }

        // Log the situation to the console
        console.log("Sitaution submitted, here is the following situation: "); 
        console.log(`Teams (offense vs. defense) are ${offenseTeam} vs. ${defenseTeam}`); 
        console.log(`${down}${down === '1' ? 'st' : down === '2' ? 'nd' : down === '3' ? 'rd' : 'th'} & ${ydsToGo} from ${ownOppMidfield} ${ownOppMidfield !== 'midfield' ? ydLine50 : ''}`);
        console.log(`Score (offense - defense) is ${offensePoints} - ${defensePoints}`);
        console.log(`Timestamp: ${quarter}${quarter === '1' ? 'st' : quarter === '2' ? 'nd' : quarter === '3' ? 'rd' : quarter === '4' ? 'th' : ''} at ${minutes}:${seconds}`);
        console.log(`Timeouts remaining: Offense ${finalOffenseTimeouts}, Defense ${finalDefenseTimeouts}`);
        console.log(`Defensive coverage: ${defenseCoverage}`);
        
        // Calculate necessary values for the situation array as needed by the backend model
        const ydLine100 = (ownOppMidfield === "own" ? 100 - parseInt(ydLine50) : ownOppMidfield === "midfield" ? 50 : ownOppMidfield === "opp" ? parseInt(ydLine50) : undefined);
        const goalToGo = (ydLine100 === parseInt(ydsToGo) ? 1 : 0);
        const scoreDiff = parseInt(offensePoints) - parseInt(defensePoints);
        const qtrSeconds = await calculateQtrSeconds(minutes, seconds);
        const halfSeconds = await calculateHalfSeconds(quarter, minutes, seconds);
        const gameSeconds = await calculateGameSeconds(quarter, minutes, seconds);

        // Create the JSON object expected by the backend model
        const currentSituation = {
            down: parseInt(down),
            ydstogo: parseInt(ydsToGo),
            yardline_100: ydLine100,
            goal_to_go: goalToGo,
            quarter_seconds_remaining: qtrSeconds,
            half_seconds_remaining: halfSeconds,
            game_seconds_remaining: gameSeconds,
            score_differential: scoreDiff,
            posteam_timeouts_remaining: parseInt(finalOffenseTimeouts),
            defteam_timeouts_remaining: parseInt(finalDefenseTimeouts),
            posteam: offenseTeam,
            defteam: defenseTeam,
            defense_coverage_type: defenseCoverage
        };

        let suggestedPlays = [];
        let suggestedPlayType = null;

        try {
            const data = await fetchSuggestedPlay({
                current_situation: currentSituation,
                play_history: [] // Starts empty for the very first play of the scenario
            });

            console.log("Backend response:", data);
            suggestedPlays = normalizeSuggestedPlays(data);
            suggestedPlayType = data.play_type || null;
            console.log("Suggested Plays:", suggestedPlays);
            
        } catch (error) {
            console.error("Error calling Flask endpoint:", error);
            alert(`Could not get play suggestions from the backend.\n\n${error.message}`);
            return;
        }

        if (suggestedPlays.length === 0) {
            alert("The backend responded, but it did not include any suggested plays. Check the browser console for the full backend response.");
            return;
        }

        const situationArray = `${down}, ${ydsToGo}, ${ydLine100}, ${goalToGo}, ${qtrSeconds}, ${halfSeconds}, ${gameSeconds}, ${scoreDiff}, ${finalOffenseTimeouts}, ${finalDefenseTimeouts}, ${offenseTeam}, ${defenseTeam}`;
        
        // Navigate to result page with situation data and show the play visualization
        navigate('/result', { 
            state: { 
                situationArray,
                offenseTeam,
                defenseTeam,
                down,
                ydsToGo,
                ownOppMidfield,
                ydLine50,
                offensePoints,
                defensePoints,
                quarter,
                minutes,
                seconds,
                offenseTimeouts: finalOffenseTimeouts,
                defenseTimeouts: finalDefenseTimeouts,
                defenseCoverage,
                ydLine100: ydLine100,
                suggestedPlayType,
                suggestedPlays,
                expYards: suggestedPlays[0]?.expected_yards || '',
                playVisualization: suggestedPlays[0]?.play_visualization || null
            } 
        });

        return; 
    }   

    return (
        <div className="situation-container">
            {/* Cards Container */}
            <div className="cards-container">
                {/* OFFENSE Card */}
                <div className="card" style={{ background: offenseTeam ? getTeamGradient(offenseTeam) : 'rgba(20, 30, 60, 0.8)' }}>
                    <h2 className="card-title">OFFENSE</h2>
                    
                    {/* Hidden team selector */}
                    <div style={{ position: 'absolute', opacity: 0, pointerEvents: 'none' }}>
                        <TeamDropdownMenu 
                            onChange={(value) => setOffenseTeam(value)}
                        />
                    </div>
                    
                    {/* Team Logo Display */}
                    <div className="team-logo-container" onClick={() => openTeamSelector('offense')} style={{ cursor: 'pointer' }}>
                        {offenseTeam ? (
                            <img 
                                src={getTeamLogo(offenseTeam)}
                                alt={offenseTeam}
                                className="team-logo"
                            />
                        ) : (
                            <div style={{ fontSize: '24px', color: 'rgba(255,255,255,0.5)' }}>Select Team</div>
                        )}
                    </div>
                    
                    {/* Points Display */}
                    <div className="points-display">
                        <input
                            type="number"
                            className="situation-input"
                            min="0"
                            max="99"
                            value={offensePoints || ''}
                            onChange={(e) => {
                                const value = parseInt(e.target.value);
                                if ((value >= 0 && value <= 99) || e.target.value === '') {
                                    setOffensePoints(e.target.value);
                                }
                            }}
                            placeholder="10"
                            style={{ fontSize: '72px', width: '120px', color: '#fffff8' }}
                        />
                    </div>
                    
                    {/* Timeout Buttons */}
                    <div className="timeout-indicators">
                        <div 
                            className={`timeout-dot ${parseInt(offenseTimeouts) >= 1 ? '' : 'inactive'}`}
                            onClick={() => setOffenseTimeouts(parseInt(offenseTimeouts) === 1 ? '0' : '1')}
                            style={{ cursor: 'pointer' }}
                        ></div>
                        <div 
                            className={`timeout-dot ${parseInt(offenseTimeouts) >= 2 ? '' : 'inactive'}`}
                            onClick={() => setOffenseTimeouts(parseInt(offenseTimeouts) === 2 ? '1' : '2')}
                            style={{ cursor: 'pointer' }}
                        ></div>
                        <div 
                            className={`timeout-dot ${parseInt(offenseTimeouts) >= 3 ? '' : 'inactive'}`}
                            onClick={() => setOffenseTimeouts(parseInt(offenseTimeouts) === 3 ? '2' : '3')}
                            style={{ cursor: 'pointer' }}
                        ></div>
                    </div>
                </div>

                {/* TEAMS Card */}
                <div className="teams-card" style={{ background: getTeamsCardGradient() }}>
                    <h2 className="card-title">GAME STATE</h2>
                    
                    {/* Down & Yards to Go */}
                    <div className="situation-row">
                        <span className="situation-label" style={{ fontSize: '25px', margin: '0 10px' }}>DOWN</span>
                            <div className="quick-btn-group">
                                {['1', '2', '3', '4'].map((d) => (
                                    <button
                                        key={d}
                                        type="button"
                                        /* Added down-btn right next to quick-btn! */
                                        className={`quick-btn down-btn ${down === d ? 'active' : ''}`}
                                        onClick={() => setDown(d)}
                                    >
                                        {d}
                                    </button>
                                ))}
                        </div>
                                                
                        <span className="situation-label" style={{ fontSize: '35px', margin: '0 20px' }}>&</span>
                        
                        <span className="situation-label"  style={{ fontSize: '25px', margin: '0 10px' }}>YDS TO GO</span>
                        <input
                            type="number"
                            className="situation-input"
                            min="1"
                            max="99"
                            value={ydsToGo || ''}
                            onChange={(e) => {
                                const value = parseInt(e.target.value);
                                if ((value >= 1 && value <= 99) || e.target.value === '') {
                                    setYdsToGo(e.target.value);
                                }
                            }}
                            placeholder="10"
                        />
                    </div>
                    {/* Defensive Coverage Dropdown */}
                    <div className="situation-row" style={{ marginTop: '15px', marginBottom: '15px' }}>
                        <span className="situation-label" style={{ fontSize: '18px' }}>COVERAGE TYPE</span>
                        <select 
                            className="situation-input" 
                            value={defenseCoverage}
                            onChange={(e) => setDefenseCoverage(e.target.value)}
                            style={{ width: '160px', fontSize: '16px' }}
                        >
                            <option value="UNKNOWN">Unknown</option>
                            <option value="COVER_0">Cover 0 (Man)</option>
                            <option value="COVER_1">Cover 1 (Man)</option>
                            <option value="COVER_2">Cover 2 (Zone)</option>
                            <option value="COVER_3">Cover 3 (Zone)</option>
                            <option value="COVER_4">Cover 4 (Quarters)</option>
                            <option value="COVER_6">Cover 6</option>
                            <option value="2_MAN">2-Man</option>
                        </select>
                    </div>
                    {/* Quarter & Time */}
                    <div className="situation-row">
                        <span className="situation-label" style={{ fontSize: '25px', margin: '0 10px' }}>QTR</span>
                        
                        {/* Quick-select buttons for Quarter */}
                        <div className="quick-btn-group">
                            {['1', '2', '3', '4', 'OT'].map((q) => (
                                <button
                                    key={q}
                                    type="button"
                                    className={`quick-btn qtr-btn ${quarter === q ? 'active' : ''}`}
                                    onClick={() => setQuarter(q)}
                                >
                                    {q}
                                </button>
                            ))}
                        </div>
                        
                        <div className="time-display" style={{ marginLeft: 'auto' }}>
                            <input
                                type="number"
                                className="situation-input"
                                min="0"
                                max="15"
                                value={minutes || ''}
                                onChange={(e) => {
                                    const value = parseInt(e.target.value);
                                    if ((value >= 0 && value <= 15) || e.target.value === '') {
                                        setMinutes(e.target.value);
                                        
                                        // Auto-advance to seconds if 2 digits are typed or if they type 15
                                        if (e.target.value.length >= 2 || value === 15) {
                                            if (value === 15) setSeconds(0);
                                            if (secondsInputRef.current) secondsInputRef.current.focus();
                                        }
                                    }
                                }}
                                placeholder="12"
                                style={{ width: '70px' }}
                            />
                            <span style={{ fontSize: '48px' }}>:</span>
                            <input
                                type="number"
                                ref={secondsInputRef} /* Attached the ref here for auto-focusing */
                                className="situation-input"
                                min="0"
                                max="59"
                                value={seconds === '' || seconds === undefined ? '' : seconds}
                                onChange={(e) => {
                                    // ... your existing seconds logic remains exactly the same
                                    const value = parseInt(e.target.value);
                                    if (parseInt(minutes) === 15) {
                                        setSeconds(0);
                                        return;
                                    }
                                    if ((value >= 0 && value <= 59) || e.target.value === '') {
                                        setSeconds(e.target.value);
                                    }
                                }}
                                placeholder="15"
                                style={{ width: '70px' }}
                            />
                        </div>
                    </div>
                </div>
                
                {/* DEFENSE Card */}
                <div className="card" style={{ background: defenseTeam ? getTeamGradient(defenseTeam) : 'rgba(20, 30, 60, 0.8)' }}>
                    <h2 className="card-title">DEFENSE</h2>
                    
                    {/* Hidden team selector */}
                    <div style={{ position: 'absolute', opacity: 0, pointerEvents: 'none' }}>
                        <TeamDropdownMenu 
                            onChange={(value) => setDefenseTeam(value)}
                        />
                    </div>
                    
                    {/* Team Logo Display */}
                    <div className="team-logo-container" onClick={() => openTeamSelector('defense')} style={{ cursor: 'pointer' }}>
                        {defenseTeam ? (
                            <img 
                                src={getTeamLogo(defenseTeam)}
                                alt={defenseTeam}
                                className="team-logo"
                            />
                        ) : (
                            <div style={{ fontSize: '24px', color: 'rgba(255,255,255,0.5)' }}>Select Team</div>
                        )}
                    </div>
                    
                    {/* Points Display */}
                    <div className="points-display">
                        <input
                            type="number"
                            className="situation-input"
                            min="0"
                            max="99"
                            value={defensePoints || ''}
                            onChange={(e) => {
                                const value = parseInt(e.target.value);
                                if ((value >= 0 && value <= 99) || e.target.value === '') {
                                    setDefensePoints(e.target.value);
                                }
                            }}
                            placeholder="10"
                            style={{ fontSize: '72px', width: '120px', color: '#fcf8f9' }}
                        />
                    </div>
                    
                    {/* Timeout Buttons */}
                    <div className="timeout-indicators">
                        <div 
                            className={`timeout-dot ${parseInt(defenseTimeouts) >= 1 ? '' : 'inactive'}`}
                            onClick={() => setDefenseTimeouts(parseInt(defenseTimeouts) === 1 ? '0' : '1')}
                            style={{ cursor: 'pointer' }}
                        ></div>
                        <div 
                            className={`timeout-dot ${parseInt(defenseTimeouts) >= 2 ? '' : 'inactive'}`}
                            onClick={() => setDefenseTimeouts(parseInt(defenseTimeouts) === 2 ? '1' : '2')}
                            style={{ cursor: 'pointer' }}
                        ></div>
                        <div 
                            className={`timeout-dot ${parseInt(defenseTimeouts) >= 3 ? '' : 'inactive'}`}
                            onClick={() => setDefenseTimeouts(parseInt(defenseTimeouts) === 3 ? '2' : '3')}
                            style={{ cursor: 'pointer' }}
                        ></div>
                    </div>
                </div>
            </div>

            {/* Field Container */}
            <div className="field-container">
                <h2 className="card-title" style={{ marginBottom: '10px' }}>FIELD POSITION</h2>
                <div 
                    className="field" 
                    onClick={handleFieldClick}
                    style={{
                        cursor: 'pointer', /* Shows the clickable hand icon */
                        background: `linear-gradient(90deg, 
                            ${offenseTeam ? teamColors[offenseTeam]?.primary + '40' : 'rgba(90, 143, 58, 0.3)'} 0%, 
                            ${offenseTeam ? teamColors[offenseTeam]?.primary + '40' : 'rgba(90, 143, 58, 0.3)'} 10%, 
                            #5a8f3a 10%, 
                            #4a7f2a 90%, 
                            ${defenseTeam ? teamColors[defenseTeam]?.primary + '40' : 'rgba(74, 127, 42, 0.3)'} 90%, 
                            ${defenseTeam ? teamColors[defenseTeam]?.primary + '40' : 'rgba(74, 127, 42, 0.3)'} 100%)`
                    }}>
                    <div className="field-lines">
                        <span>0</span>
                        <span>10</span>
                        <span>20</span>
                        <span>30</span>
                        <span>40</span>
                        <span>50</span>
                        <span>40</span>
                        <span>30</span>
                        <span>20</span>
                        <span>10</span>
                        <span>0</span>
                    </div>
                    <div className="field-marker">
                        <div 
                            className="ball-marker"
                            style={{ 
                                left: `${calculateBallPosition()}%`, 
                                transform: 'translateX(-50%)',
                                position: 'absolute'
                            }}
                        ></div>
                    </div>
                </div>
                <div className="yard-line-display">
                    {/* Territory selector */}
                    <div className="quick-btn-group">
                        <button 
                            type="button" 
                            className={`quick-btn terr-btn ${ownOppMidfield === 'own' ? 'active' : ''}`} 
                            onClick={() => setOwnOppMidfield('own')}
                        >
                            OWN
                        </button>
                        
                        <button 
                            type="button" 
                            className={`quick-btn terr-btn ${ownOppMidfield === 'midfield' ? 'active' : ''}`} 
                            onClick={() => { 
                                setOwnOppMidfield('midfield'); 
                                setYdLine50('50'); 
                            }}
                        >
                            MID
                        </button>
                        
                        <button 
                            type="button" 
                            className={`quick-btn terr-btn ${ownOppMidfield === 'opp' ? 'active' : ''}`} 
                            onClick={() => setOwnOppMidfield('opp')}
                        >
                            OPP
                        </button>
                    </div>
                    
                    {/* Yard line input */}
                    <input
                        type="number"
                        className="situation-input"
                        min="1"
                        max="50"
                        value={ydLine50 || ''}
                        onChange={(e) => {
                            const value = parseInt(e.target.value);
                            if (value === 50) {
                                setOwnOppMidfield('midfield');
                                setYdLine50('50');
                            } else if ((value >= 1 && value <= 49) || e.target.value === '') {
                                setYdLine50(e.target.value);
                            }
                        }}
                        placeholder="20"
                        style={{ width: '100px' }}
                        disabled={ownOppMidfield === 'midfield'}
                    />
                </div>
            </div>

            {/* Submit Button */}
            <button className="submit-button" onClick={submitSituation}>
                Submit Situation
            </button>

            {/* Tip Message */}
            <div style={{
                position: 'fixed',
                bottom: '15px',
                right: '15px',
                color: 'rgba(255, 255, 255, 0.6)',
                fontSize: '12px',
                fontStyle: 'italic',
                textAlign: 'right',
                padding: '8px 12px',
                background: 'rgba(20, 30, 60, 0.7)',
                borderRadius: '8px',
                border: '1px solid rgba(255, 255, 255, 0.3)'
            }}>
                {tips[currentTipIndex]}
            </div>

            {/* Team Selector Modal */}
            {showTeamSelector && (
                <div className="team-selector-overlay" onClick={() => setShowTeamSelector(false)}>
                    <div className="team-selector-modal" onClick={(e) => e.stopPropagation()}>
                        <h2 className="team-selector-title">SELECT TEAM</h2>
                        
                        {/* The Search Input */}
                        <input 
                            type="text" 
                            className="team-search-input"
                            placeholder="Type team abbreviation (e.g., BUF)..."
                            value={teamSearchQuery}
                            onChange={(e) => setTeamSearchQuery(e.target.value)}
                            autoFocus /* Automatically puts the cursor here so they can start typing instantly */
                        />

                        <div className="team-grid">
                            {/*Filter teams before mapping them */}
                            {teams
                                .filter(team => team.abbr.toLowerCase().includes(teamSearchQuery.toLowerCase()))
                                .map((team) => (
                                <div 
                                    key={team.abbr}
                                    className="team-option"
                                    onClick={() => selectTeam(team.abbr)}
                                >
                                    <img src={team.logo} alt={team.abbr} className="team-option-logo" />
                                    <span className="team-option-abbr">{team.abbr}</span>
                                </div>
                            ))}
            </div>
            <button type="button" className="close-modal-btn" onClick={() => setShowTeamSelector(false)}>✕</button>
        </div>
    </div>
)}
        </div>
    );
}

export default Situation;
