export function fieldPosition(side, yardline) {
    if (side === 'midfield') return 50;
    if (yardline === '' || yardline === null || yardline === undefined) {
        throw new Error('Enter a field position.');
    }
    const value = Number(yardline);
    if (!Number.isInteger(value) || value < 0 || value > 50 || !['own', 'opp'].includes(side)) {
        throw new Error('Enter a valid field position from 0 to 50.');
    }
    return side === 'own' ? 100 - value : value;
}

export function updatePlayHistory({ previous, current, history, playType, recordPlay, newDrive }) {
    if (!Number.isFinite(current.yardline_100)) throw new Error('Enter a valid field position.');
    const possessionChanged = previous.posteam !== current.posteam || previous.defteam !== current.defteam;
    if (newDrive || possessionChanged) return [];
    if (!recordPlay) return history;
    if (!Number.isFinite(previous.yardline_100)) throw new Error('The preceding field position is missing.');
    if (!['run', 'pass'].includes(playType)) throw new Error('Select the completed play type.');
    return [...history, {
        play_type: playType,
        yards_gained: previous.yardline_100 - current.yardline_100,
    }];
}
