export const defaultPositions = [[76, 202], [160, 202], [250, 202], [280, 202], [310, 202], [340, 202], [370, 202], [462, 202], [544, 202], [310, 244], [366, 266]];
export const playerLabels = ['Left wide player', 'Left slot player', 'Left tackle', 'Left guard', 'Center', 'Right guard', 'Right tackle', 'Right slot player', 'Right wide player', 'Quarterback', 'Running back'];
export const clampPosition = (x, y) => [Math.round(Math.min(600, Math.max(20, x))), Math.round(Math.min(290, Math.max(202, y)))];
// Preserve the route's landmarks; only its starting point follows its player.
export function anchoredRoute(path, positions) {
    const start = path.match(/^M(\d+)\s+(\d+)/);
    if (!start) return path;
    const index = defaultPositions.findIndex(([x, y]) => x === Number(start[1]) && y === Number(start[2]));
    return index < 0 ? path : path.replace(/^M\d+\s+\d+/, `M${positions[index][0]} ${positions[index][1]}`);
}
