import {fieldPosition, updatePlayHistory} from './playHistory';

const state = yardline => ({yardline_100: yardline, posteam: 'KC', defteam: 'BUF'});

test('consecutive plays use the immediately preceding position', () => {
    const first = updatePlayHistory({previous: state(55), current: state(48), history: [], playType: 'run', recordPlay: true});
    const second = updatePlayHistory({previous: state(48), current: state(45), history: first, playType: 'pass', recordPlay: true});
    expect(second.map(play => play.yards_gained)).toEqual([7, 3]);
});

test('refresh does not record a play and new drives reset history', () => {
    const history = [{play_type: 'run', yards_gained: 5}];
    const args = {previous: state(45), current: state(45), history, playType: 'run'};
    expect(updatePlayHistory({...args, recordPlay: false})).toBe(history);
    expect(updatePlayHistory({...args, newDrive: true, recordPlay: true})).toEqual([]);
    expect(updatePlayHistory({...args, current: {...state(55), posteam: 'BUF', defteam: 'KC'}, recordPlay: true})).toEqual([]);
});

test('field position supports midfield crossings, losses, and the goal line', () => {
    expect(fieldPosition('own', '45')).toBe(55);
    expect(fieldPosition('midfield', '')).toBe(50);
    expect(fieldPosition('opp', '0')).toBe(0);
    expect(() => fieldPosition('own', '')).toThrow();
    expect(updatePlayHistory({previous: state(45), current: state(48), history: [], playType: 'pass', recordPlay: true})[0].yards_gained).toBe(-3);
});
