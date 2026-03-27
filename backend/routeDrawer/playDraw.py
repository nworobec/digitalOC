'''
Currently uses a dict as input  

input dictionary:
        "yardline_100": int,
        "down": int,
        "ydstogo": int,
        "pass_length": string,
        "pass_location": string,
        "air_yards": int,
        "run_location": string,
        "run_gap": string,
        "offense_formation": string,
        "offense_personnel": string,
        "route": string,
        "involved_player_position": string

Route Concepts:
    Go      → FLOAT:     outside=GO, inside=short OUT
    Flat    → FLANK:     inside=FLAT, outside=SLANT
    Cross   → Y CROSS:   inside=CROSS, outside=DIG
    Hitch   → SMASH:     outside=HITCH, inside=CORNER
                CURLS (>8 yds): outside=HITCH, inside=HITCH
    Screen  → (Screen):  outside=SCREEN, inside=blocks (no route)
    Out     → GHOST:     inside=OUT, outside=GO
    In      → DRIVE (>8 yds): inside=IN, outside=DRAG
              SLANT (<8 yds): inside=IN, outside=SLANT (both sides)
    Slant   → DOUBLE SLANTS: both=SLANT
    Corner  → SCISSORS:  outside=POST, inside=CORNER
    Post    → MILLS:     outside=POST, inside=IN
    Wheel   → POST-WHEEL: outside=POST, inside=WHEEL
'''

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np



# CONCEPT DEFINITIONS
# Maps a primary route → (concept_name, secondary_route, secondary_position_pref)
# secondary_position_pref: 'inside' or 'outside' (which player runs the companion)

ROUTE_CONCEPTS = {
    # companion_air: explicit depth for companion; None = derive below per-route
    'GO':     lambda ay: ('FLOAT',        'OUT',    'inside',  5),                            # short out underneath
    'FLAT':   lambda ay: ('FLANK',        'SLANT',  'inside',  6),                            # slant ~6 yds
    'CROSS':  lambda ay: ('Y CROSS',      'DIG',    'outside', max((ay or 8), 8)),           # dig at least as deep as cross
    'HITCH':  lambda ay: (
        'CURLS' if (ay or 0) > 8 else 'SMASH',
        'HITCH' if (ay or 0) > 8 else 'CORNER',
        'inside',
        (ay or 8) if (ay or 0) > 8 else max((ay or 5) + 4, 10),
    ),
    'SCREEN': lambda ay: (None,           None,     None,      None),                       # inside blocks
    'OUT':    lambda ay: ('GHOST',        'GO',     'outside', max((ay or 8) + 6, 14)),     # go route deeper than the out
    'IN':     lambda ay: (
        'DAGGER' if (ay or 0) > 8 else 'SLANT',
        'GO'     if (ay or 0) > 8 else 'SLANT',
        'inside',                                                                            # inside runs the go vertical
        max((ay or 9) + 4, 14) if (ay or 0) > 8 else 6,                                    # go is deeper than the in
    ),
    'SLANT':  lambda ay: ('DOUBLE SLANTS','SLANT',  'outside', 6),                          # match slant depth
    'CORNER': lambda ay: ('SCISSORS',     'POST',   'outside', (ay or 12)),                 # post same depth as corner
    'POST':   lambda ay: ('MILLS',        'IN',     'inside',  max((ay or 12), 8)),         # in slightly shorter than post
    'WHEEL':  lambda ay: ('POST-WHEEL',   'POST',   'outside', max((ay or 14) - 2, 12)),    # post just under wheel depth
}

# For SCISSORS and GHOST the "companion" is actually the OUTSIDE receiver
# while in others the companion is the INSIDE receiver.
# We handle companion positioning in get_companion_position().

# BACKSIDE CONCEPTS
# Maps frontside concept -> (backside_concept_name, backside_primary_route, 
#                            backside_companion_route, backside_companion_pref, 
#                            backside_primary_air, backside_companion_air)
BACKSIDE_CONCEPTS = {
    'FLOAT':        ('Y CROSS',  'CROSS', 'DIG',    'outside', 10, 10),
    'FLANK':        ('FLOAT',    'GO',    'OUT',    'inside',  14, 5),
    'Y CROSS':      ('GHOST',    'OUT',   'GO',     'outside', 8,  14),
    'SMASH':        ('DAGGER',   'IN',    'GO',     'inside',  10, 14),
    'CURLS':        ('SCISSORS', 'CORNER','POST',   'outside', 12, 12),
    'GHOST':        ('MILLS',    'POST',  'IN',     'inside',  14, 10),
    'DAGGER':       ('SCISSORS', 'CORNER','POST',   'outside', 12, 12),
    'DOUBLE SLANTS':('FLANK',    'FLAT',  'SLANT',  'inside',  2,  6),
    'SCISSORS':     ('SLANT',    'SLANT', 'SLANT',  'outside', 6,  6),
    'MILLS':        ('SMASH',    'HITCH', 'CORNER', 'inside',  5,  10),
    'POST-WHEEL':   ('SMASH',    'HITCH', 'CORNER', 'inside',  5,  10),
    'SLANT':        ('FLANK',    'FLAT',  'SLANT',  'inside',  2,  6),
}


# FIELD DRAWING

def draw_field(ax, ydstogo, yardline_100):
    ax.set_facecolor('#3A9D23')
    
    max_y_visible = 45
    ax.set_xlim(-25, 25)
    ax.set_ylim(-10, max_y_visible)

    # Endzone
    if pd.notna(yardline_100) and yardline_100 < max_y_visible:
        ax.axhspan(yardline_100, max_y_visible, color='#004080', alpha=0.5)
        ax.text(-24, yardline_100 + 1, 'ENDZONE', color='white', fontsize=12, fontweight='bold')

    # Line of scrimmage
    ax.axhline(0, color='white', linestyle='--', linewidth=2, label='Line of Scrimmage')

    # First down line
    if pd.notna(ydstogo) and ydstogo < max_y_visible:
        ax.axhline(ydstogo, color='yellow', linestyle='-', linewidth=3, label=f'1st Down ({int(ydstogo)} yds)')

    # Yard lines
    if pd.isna(yardline_100):
        for y in range(5, max_y_visible, 5):
            if pd.notna(ydstogo) and y == ydstogo:
                continue
            ax.axhline(y, color='white', linestyle='-', alpha=0.5)
            ax.text(-24, y + 0.5, str(y), color='white', fontsize=10)
    else:
        ball_on_yardline = 100 - yardline_100
        first_marker_downfield = (ball_on_yardline // 5) * 5 + 5
        yds_to_first_marker = first_marker_downfield - ball_on_yardline
        for y_relative in range(int(yds_to_first_marker), max_y_visible, 5):
            absolute_yardline = first_marker_downfield + (y_relative - yds_to_first_marker)
            label = 100 - absolute_yardline if absolute_yardline > 50 else absolute_yardline
            if (pd.notna(yardline_100) and y_relative == yardline_100) or \
               (pd.notna(ydstogo) and y_relative == ydstogo):
                continue
            ax.axhline(y_relative, color='white', linestyle='-', alpha=0.5)
            ax.text(-24, y_relative + 0.5, str(int(label)), color='white', fontsize=10)

    # Hash marks
    for y in np.arange(1, max_y_visible, 1):
        ax.plot([-9, -8], [y, y], color='white', alpha=0.5)
        ax.plot([8, 9],   [y, y], color='white', alpha=0.5)

    # O-line
    ol_x = [-4, -2, 0, 2, 4]
    ax.plot(ol_x, [0]*5, 'o', color='white', markersize=10, label='Offensive Line')

    ax.set_xticks([])
    ax.set_yticks([])


# PLAYER POSITIONING

# Routes that break outward — typically run from the slot (inside alignment)
SLOT_ROUTES = {'OUT', 'FLAT', 'CORNER', 'WHEEL', 'SCREEN', 'CROSS', 'SLANT'}

# Routes that break inward — typically run from outside (wide alignment)
WIDE_ROUTES = {'POST', 'DIG', 'DRAG', 'GO', 'FADE',
               'HITCH', 'CURL', 'IN', 'UNKNOWN'}


def get_start_position(position, pass_location, formation, route=None):
    if position == 'RB' and 'EMPTY' in str(formation).upper():
        position = 'WR'

    if pd.isna(pass_location) or pass_location == 'middle':
        location_side = 'right'
    else:
        location_side = pass_location

    if 'SHOTGUN' in str(formation).upper():
        backfield_y = -5
    elif 'SINGLEBACK' in str(formation).upper() or 'I_FORM' in str(formation).upper():
        backfield_y = -5
    elif 'PISTOL' in str(formation).upper():
        backfield_y = -7.5
    else:
        backfield_y = -5

    if position == 'RB':
        if 'I_FORM' in str(formation).upper() or 'SINGLEBACK' in str(formation).upper() or 'PISTOL' in str(formation).upper():
            return (0, backfield_y)
        if 'SHOTGUN' in str(formation).upper():
            return (2, backfield_y) if location_side == 'left' else (-2, backfield_y)
        return (-2, backfield_y) if location_side == 'left' else (2, backfield_y)

    elif position == 'TE':
        return (-5, -0.5) if location_side == 'left' else (5, -0.5)

    elif position == 'WR':
        # Fixed positions: outside=±18, inside=±8
        # The concept logic determines which receiver runs which route
        route_key = str(route).upper() if route else 'UNKNOWN'
        if route_key in SLOT_ROUTES:
            return (-12, -0.5) if location_side == 'left' else (12, -0.5)
        else:
            return (-18, -0.5) if location_side == 'left' else (18, -0.5)

    else:
        return (0, 0)


def get_companion_start_position(primary_pos, pass_location, companion_pref, formation, companion_route=None):
    """
    Given the primary receiver's position (x, y) and side, determine
    the companion receiver's starting position.
    companion_pref: 'inside' = slot alignment (±8), 'outside' = wide alignment (±18)
    The companion's position is determined purely by companion_pref — the primary's
    get_start_position() already handles route-based alignment for the targeted receiver.
    """
    if pd.isna(pass_location) or pass_location == 'middle':
        location_side = 'right'
    else:
        location_side = pass_location

    primary_x, _ = primary_pos
    sign = -1 if location_side == 'left' else 1

    if companion_pref == 'inside':
        comp_x = sign * 12   # inside/slot
    else:
        comp_x = sign * 18   # outside/wide

    # Final safety: avoid stacking on top of primary
    if abs(comp_x - primary_x) < 5:
        comp_x = comp_x + (5 if comp_x > 0 else -5)

    return (comp_x, -0.5)


# ROUTE PATHS

def get_route_path(route_name, start_pos, position, location, air_yards):
    if pd.isna(route_name):
        route_name = "UNKNOWN"
    route_key = str(route_name).upper()

    start_x, start_y = start_pos
    is_left_side = start_x < 0

    if pd.isna(air_yards):
        if route_key == 'SCREEN':
            air_yards = -2
        else:
            air_yards = 5
    y = air_yards

    if route_key == 'SCREEN' and position == 'RB':
        if location == 'left':
            relative_path = [(0, 1), (-5, y)]
        else:
            relative_path = [(0, 1), (5, y)]
    else:
        ROUTE_DEFINITIONS = {
            'GO':     lambda y: [(0, y*0.5), (0, y)],
            'FADE':   lambda y: [(1, y*0.5), (3, y)],
            'OUT':    lambda y: [(0, y*0.8), (0, y), (10, y)],
            'IN':     lambda y: [(0, y*0.75), (0, y*0.75), (-10, y*0.75)],
            'HITCH':  lambda y: [(0, y), (0, y-2)],
            'CURL':   lambda y: [(0, y), (0, y+2), (0, y), (-2, y)],
            'SLANT':  lambda _: [(0, 3), (-3, 6)],
            'FLAT':   lambda _: [(3, 1), (5, 1)],
            'SCREEN': lambda _: [(-3, 0), (-5, -2)],
            'WHEEL':  lambda _: [(3, 1), (8, 3), (12, 8), (12, 12), (12, 16)],
            'CROSS':  lambda y: [(-2, y*0.2), (-6, y*0.5), (-11, y*0.8), (-15, y)],
            # New routes for concepts
            'CORNER': lambda y: [(0, y*0.6), (0, y*0.85), (4, y)],
            'POST':   lambda y: [(0, y*0.5), (0, y*0.75), (-4, y)],
            'DIG':    lambda y: [(0, y*0.6), (0, y), (-6, y)],
            'DRAG':   lambda _: [(0, 2), (-4, 4)],
        }

        route_func = ROUTE_DEFINITIONS.get(route_key, lambda y: [(0, y*0.5), (1, y)])
        relative_path = route_func(y)

    if is_left_side and not (route_key == 'SCREEN' and position == 'RB'):
        mirror_routes = ['OUT', 'FLAT', 'IN', 'SLANT', 'FADE', 'CURL', 'SCREEN', 'CROSS',
                         'CORNER', 'POST', 'DIG', 'DRAG', 'WHEEL']
        if route_key in mirror_routes:
            relative_path = [(-x, y) for x, y in relative_path]

    absolute_path = [
        (start_x + rel_x, start_y + rel_y)
        for rel_x, rel_y in relative_path
    ]
    return absolute_path


def get_run_path(run_location, run_gap, start_pos):
    target_x = 0
    if run_location == 'middle':
        target_x = 0
    elif run_location == 'left':
        if run_gap == 'guard':   target_x = -1
        elif run_gap == 'tackle': target_x = -3
        elif run_gap == 'end':   target_x = -5
        else:                    target_x = -3
    elif run_location == 'right':
        if run_gap == 'guard':   target_x = 1
        elif run_gap == 'tackle': target_x = 3
        elif run_gap == 'end':   target_x = 5
        else:                    target_x = 3

    return [(target_x, 0.5), (target_x, 5)]


# PERSONNEL PARSING & ALIGNMENT

def parse_personnel(personnel_str):
    counts = {'RB': 0, 'TE': 0, 'WR': 0}
    if pd.isna(personnel_str):
        return counts
    personnel_str = str(personnel_str).replace('"', '')
    for part in personnel_str.split(','):
        part = part.strip()
        pieces = part.split(' ')
        if len(pieces) == 2:
            try:
                count = int(pieces[0])
                pos   = pieces[1].strip()
                if pos in counts:
                    counts[pos] = count
            except ValueError:
                continue
    return counts


def get_default_alignments(personnel_counts, formation, play_type='pass', location=None, occupied_slots=None, concept_side=None):
    """
    Same as before but now accepts a list of occupied_slots to exclude.
    """
    if occupied_slots is None:
        occupied_slots = []

    alignments = []
    formation_str = str(formation).upper()

    if 'SHOTGUN' in formation_str:         backfield_y = -5
    elif 'SINGLEBACK' in formation_str or 'I_FORM' in formation_str: backfield_y = -5
    elif 'PISTOL' in formation_str:        backfield_y = -7.5
    else:                                  backfield_y = -5

    WR_SLOTS = [
        (-18, -0.5), (18, -0.5),
        (-11, -1),   (11, -1),
        (7,  -0.5),  (-7, -0.5),
    ]
    TE_SLOT_RIGHT = (5.5, -1)
    TE_SLOT_LEFT  = (-5.5, -1)

    is_run = play_type == 'run'
    run_side = str(location).lower() if location else ''
    if is_run and run_side == 'left':
        TE_SLOTS = [TE_SLOT_LEFT, TE_SLOT_RIGHT]
    elif is_run and run_side == 'right':
        TE_SLOTS = [TE_SLOT_RIGHT, TE_SLOT_LEFT]
    else:
        TE_SLOTS = [TE_SLOT_RIGHT, TE_SLOT_LEFT]

    OFFSET_RB_SLOTS  = [(2, -5), (-2, -5)]
    I_FORM_RB_SLOTS  = [(0, -3), (0, -5)]
    PISTOL_RB_SLOTS  = [(0, backfield_y), (-4, -4) if run_side == 'left' else (4, -4)]

    available_wr_slots = WR_SLOTS.copy()
    available_te_slots = TE_SLOTS.copy()

    if 'I_FORM' in formation_str:       available_rb_slots = I_FORM_RB_SLOTS.copy()
    elif 'PISTOL' in formation_str:     available_rb_slots = PISTOL_RB_SLOTS.copy()
    elif 'SINGLEBACK' in formation_str: available_rb_slots = [(0, backfield_y)]
    else:                               available_rb_slots = OFFSET_RB_SLOTS.copy()

    # Remove ALL occupied slots
    for slot in occupied_slots:
        for slot_list in [available_wr_slots, available_te_slots, available_rb_slots]:
            if slot in slot_list:
                slot_list.remove(slot)

    # If concept_side is specified, remove all WR/TE slots on that side to force
    # remaining receivers to the opposite side (max 2 receivers per side rule)
    if concept_side is not None:
        sign = -1 if concept_side == 'left' else 1
        available_wr_slots = [s for s in available_wr_slots if (s[0] * sign) < 0]
        available_te_slots = [s for s in available_te_slots if (s[0] * sign) < 0]

    is_empty = 'EMPTY' in formation_str

    for _ in range(personnel_counts.get('TE', 0)):
        if available_te_slots:
            slot = available_te_slots.pop(0)
            alignments.append(('TE', slot))
            if slot in available_wr_slots:
                available_wr_slots.remove(slot)

    for i in range(personnel_counts.get('WR', 0)):
        slot = available_wr_slots.pop(0) if available_wr_slots else (20 + i*2, -0.5)
        alignments.append(('WR', slot))
        if slot in available_te_slots:
            available_te_slots.remove(slot)

    for i in range(personnel_counts.get('RB', 0)):
        if is_empty:
            if available_wr_slots:
                alignments.append(('RB', available_wr_slots.pop(0)))
            elif available_te_slots:
                alignments.append(('RB', available_te_slots.pop(0)))
        else:
            if available_rb_slots:
                alignments.append(('RB', available_rb_slots.pop(0)))
            else:
                side = 2 if i % 2 == 0 else -2
                alignments.append(('RB', (side, -4)))

    return alignments


# ---------------------------------------------------------------------------
# PLOT HELPER
# ---------------------------------------------------------------------------

def _draw_route(ax, start_pos, path, color, lw=3):
    """Draw route arrow on ax from start_pos through path points."""
    if not path:
        return
    start_x, start_y = start_pos
    full_x = [start_x] + [x for x, _ in path]
    full_y = [start_y] + [y for _, y in path]
    ax.plot(full_x, full_y, '-', color=color, linewidth=lw)
    ax.arrow(
        full_x[-2], full_y[-2],
        full_x[-1] - full_x[-2],
        full_y[-1] - full_y[-2],
        head_width=1, head_length=1,
        fc=color, ec=color, length_includes_head=True
    )


# MAIN VISUALIZATION

def visualize_play(play_data, save_path='play_visualization.png'):
    """
    Accepts a dictionary 'play_data' containing all necessary play variables.
    Pass plays now draw the full route concept (companion route alongside primary).
    """
    formation   = play_data.get('offense_formation')
    personnel   = play_data.get('offense_personnel')
    position    = play_data.get('involved_player_position')

    def get_num(key):
        val = play_data.get(key)
        return val if pd.notna(val) else None

    down        = get_num('down')
    ydstogo     = get_num('ydstogo')
    yardline_100 = get_num('yardline_100')

    down_str     = f"{int(down) if down else '?'} & {int(ydstogo) if ydstogo else '?'}"
    yardline_str = f"{int(yardline_100) if yardline_100 else '?'} yds to EZ"

    play_type       = ''
    plot_label      = ''
    path_info_str   = ''
    concept_name    = ''
    path            = []
    companion_path       = []
    companion_start      = None
    
    # Backside concept variables
    backside_primary_start = None
    backside_primary_path = []
    backside_companion_start = None
    backside_companion_path = []
    backside_concept_name = None
    backside_companion_is_te = False
    backside_primary_is_te = False

    route   = play_data.get('route')
    run_gap = play_data.get('run_gap')

    # ---- PASS PLAY ----
    if pd.notna(route):
        play_type  = 'pass'
        route      = play_data.get('route')
        location   = play_data.get('pass_location')
        air_yards  = get_num('air_yards')
        plot_label = f'Targeted Receiver ({position})'

        start_pos = get_start_position(position, location, formation, route=route)
        path      = get_route_path(route, start_pos, position, location, air_yards)

        # --- Concept Logic ---
        route_key = str(route).upper()
        concept_fn = ROUTE_CONCEPTS.get(route_key)
        companion_is_te = False 
        
        # Track available TEs so we can assign them to inside alignments
        pc_check_temp = parse_personnel(personnel)
        te_available = pc_check_temp.get('TE', 0) - (1 if position == 'TE' else 0)

        if concept_fn is not None:
            concept_name, companion_route, companion_pref, companion_air = concept_fn(air_yards)

            if companion_route is not None and companion_pref is not None:
                companion_start = get_companion_start_position(
                    start_pos, location, companion_pref, formation,
                    companion_route=companion_route
                )
                comp_air = companion_air if companion_air is not None else (air_yards or 5)
                
                # Check if we should use an available TE for the frontside companion
                if te_available > 0 and companion_pref == 'inside':
                    companion_is_te = True
                    te_available -= 1 # Consume the TE
                    sign = -1 if companion_start[0] < 0 else 1
                    companion_start = (sign * 5, -1) # Force TE alignment
                
                companion_path = get_route_path(
                    companion_route,
                    companion_start,
                    'WR',
                    location,
                    comp_air
                )

        if concept_name:
            path_info_str = "Route: {} ({} yds) | Concept: {}".format(route_key, air_yards, concept_name)
        else:
            path_info_str = "Route: {} ({} yds)".format(route_key, air_yards)
        
        # --- Backside Concept Logic ---
        if concept_name and concept_name in BACKSIDE_CONCEPTS:
            backside_info = BACKSIDE_CONCEPTS[concept_name]
            (backside_concept_name, backside_primary_route, backside_companion_route,
             backside_companion_pref, backside_primary_air, backside_companion_air) = backside_info
            
            frontside = 'left' if start_pos[0] < 0 else 'right'
            backside = 'right' if frontside == 'left' else 'left'
            
            backside_primary_start = get_start_position(
                'WR', backside, formation, route=backside_primary_route
            )
            backside_primary_path = get_route_path(
                backside_primary_route, backside_primary_start, 'WR',
                backside, backside_primary_air
            )
            
            backside_companion_start = get_companion_start_position(
                backside_primary_start, backside, backside_companion_pref,
                formation, companion_route=backside_companion_route
            )
            
            # Check if an available TE should play the backside inside receiver
            if te_available > 0:
                if backside_companion_pref == 'outside':
                    # If companion is outside, the primary MUST be the inside receiver
                    backside_primary_is_te = True
                    te_available -= 1
                    sign = -1 if backside_primary_start[0] < 0 else 1
                    backside_primary_start = (sign * 5, -1) # Force TE alignment
                    
                elif backside_companion_pref == 'inside':
                    backside_companion_is_te = True
                    te_available -= 1
                    sign = -1 if backside_companion_start[0] < 0 else 1
                    backside_companion_start = (sign * 5, -1) # Force TE alignment
            
            backside_companion_path = get_route_path(
                backside_companion_route, backside_companion_start, 'WR',
                backside, backside_companion_air
            )

    #      RUN PLAY 
    elif pd.notna(run_gap):
        play_type     = 'run'
        location      = play_data.get('run_location')
        run_gap_val   = play_data.get('run_gap')
        plot_label    = f'Rusher ({position})'
        path_info_str = f"Run: {str(location).capitalize()} ({str(run_gap_val).capitalize()})"

        start_pos = get_start_position(position, location, formation)
        path      = get_run_path(location, run_gap_val, start_pos)

    #      FALLBACK 
    else:
        start_pos  = (0, -1)
        location   = None
        plot_label = 'Unknown Play'

    print(f"  > Situation: {down_str} | {yardline_str}")
    print(f"  > Formation: {formation}")
    print(f"  > Personnel: {personnel}")
    print(f"  > Play Type: {play_type}")
    if concept_name:
        print(f"  > Concept:   {concept_name}")

    # BUILD FIGURE
    fig, ax = plt.subplots(figsize=(7, 7))
    fig.patch.set_facecolor('#1A1A2E')

    draw_field(ax, ydstogo, yardline_100)

    # QB
    formation_str = str(formation).upper()
    if 'SHOTGUN' in formation_str:
        qb_pos, qb_label = (0, -5),  'QB (Shotgun)'
    elif 'SINGLEBACK' in formation_str or 'I_FORM' in formation_str:
        qb_pos, qb_label = (0, -1),  'QB (Under Center)'
    elif 'PISTOL' in formation_str:
        qb_pos, qb_label = (0, -4),  'QB (Pistol)'
    else:
        qb_pos, qb_label = (0, -1),  'QB (Reference)'

    ax.plot(qb_pos[0], qb_pos[1], 'o', color='yellow', markersize=12, label=qb_label)

    personnel_counts = parse_personnel(personnel)
    current_skill_count = sum(personnel_counts.values())
    if current_skill_count < 5:
        personnel_counts['WR'] = personnel_counts.get('WR', 0) + (5 - current_skill_count)

    def consume_player(pref_pos):
        if personnel_counts.get(pref_pos, 0) > 0:
            personnel_counts[pref_pos] -= 1
        else:
            for fallback_pos in ['WR', 'TE', 'RB']:
                if personnel_counts.get(fallback_pos, 0) > 0:
                    personnel_counts[fallback_pos] -= 1
                    break

    # Subtract frontside and backside receivers from background count based on updated flags
    if position:
        consume_player(position)
        
    if companion_start is not None:
        consume_player('TE' if companion_is_te else 'WR')
        
    if backside_primary_start is not None:
        consume_player('TE' if backside_primary_is_te else 'WR')
        
    if backside_companion_start is not None:
        consume_player('TE' if backside_companion_is_te else 'WR')

    occupied_slots = [start_pos]
    if companion_start is not None:
        occupied_slots.append(companion_start)
    if backside_primary_start is not None:
        occupied_slots.append(backside_primary_start)
    if backside_companion_start is not None:
        occupied_slots.append(backside_companion_start)

    concept_side = None
    if play_type == 'pass' and companion_start is not None:
        concept_side = 'left' if start_pos[0] < 0 else 'right'

    default_players = get_default_alignments(
        personnel_counts, formation, play_type, location,
        occupied_slots=occupied_slots,
        concept_side=concept_side
    )

    # Draw other (background) receivers
    has_ghost_label = False
    for pos, (x, y) in default_players:
        if not has_ghost_label:
            ax.plot(x, y, 'o', color='white', markersize=10, alpha=0.7, label='Other Players')
            has_ghost_label = True
        else:
            ax.plot(x, y, 'o', color='white', markersize=10, alpha=0.7)

    # Draw primary receiver / rusher (RED)
    sx, sy = start_pos
    ax.plot(sx, sy, 'o', color='red', markersize=12, label=plot_label)
    _draw_route(ax, start_pos, path, color='red', lw=3)

    # Draw companion receiver(s) (LIGHT BLUE)
    if companion_start is not None and companion_path:
        cx, cy = companion_start
        pos_type = 'TE' if companion_is_te else 'WR'
        companion_label = 'Companion {} ({})'.format(pos_type, concept_name)
        ax.plot(cx, cy, 'o', color="#72CEFF", markersize=12, label=companion_label)
        _draw_route(ax, companion_start, companion_path, color='#72CEFF', lw=3)
    elif companion_start is not None:
        cx, cy = companion_start
        ax.plot(cx, cy, 'o', color='#72CEFF', markersize=12,
                label='Blocker / No Route')

    if backside_primary_start is not None:
        bx, by = backside_primary_start
        pos_type = 'TE' if backside_primary_is_te else 'WR'
        ax.plot(bx, by, 'o', color='#72CEFF', markersize=12,
                label='Backside Primary {} ({})'.format(pos_type, backside_concept_name))
        _draw_route(ax, backside_primary_start, backside_primary_path, color='#72CEFF', lw=3)
    
    if backside_companion_start is not None:
        bcx, bcy = backside_companion_start
        pos_type = 'TE' if backside_companion_is_te else 'WR'
        ax.plot(bcx, bcy, 'o', color="#72CEFF", markersize=12,
                label='Backside {} ({})'.format(pos_type, backside_concept_name))
        _draw_route(ax, backside_companion_start, backside_companion_path, color='#72CEFF', lw=3)

    title_text = (
        f"{down_str} | {yardline_str}\n"
        f"Position: {position} | {path_info_str}\n"
        f"Formation: {formation} | Personnel: {personnel}"
    )
    ax.set_title(title_text, fontsize=11, color='white', pad=10)
    fig.patch.set_facecolor('#1A1A2E')

    handles, labels = ax.get_legend_handles_labels()
    unique = {}
    for h, l in zip(handles, labels):
        if l not in unique:
            unique[l] = h
    ax.legend(unique.values(), unique.keys(), loc='upper right',
              facecolor='#2A2A3E', edgecolor='white', labelcolor='white', fontsize=9)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close()


# TEST CASES

if __name__ == "__main__":
    # --- Test all 11 concepts ---
    # Given route -> Concept -> Complimentary concept

    test_plays = [
        # 1. GO → FLOAT -> Y CROSS
        {
            "yardline_100": 25, "down": 1, "ydstogo": 10,
            "pass_length": "deep", "pass_location": "right", "air_yards": 15,
            "run_location": None, "run_gap": None,
            "offense_formation": "SHOTGUN", "offense_personnel": "1 RB, 1 TE, 3 WR",
            "route": "GO", "involved_player_position": "WR"
        },
        # 2. FLAT → FLANK -> FLOAT
        {
            "yardline_100": 35, "down": 2, "ydstogo": 7,
            "pass_length": "short", "pass_location": "left", "air_yards": 2,
            "run_location": None, "run_gap": None,
            "offense_formation": "SHOTGUN", "offense_personnel": "1 RB, 2 TE, 2 WR",
            "route": "FLAT", "involved_player_position": "TE"
        },
        # 3. CROSS → Y CROSS -> GHOST
        {
            "yardline_100": 40, "down": 3, "ydstogo": 8,
            "pass_length": "medium", "pass_location": "right", "air_yards": 10,
            "run_location": None, "run_gap": None,
            "offense_formation": "SHOTGUN", "offense_personnel": "1 RB, 1 TE, 3 WR",
            "route": "CROSS", "involved_player_position": "TE"
        },
        
    ]

    for i, play in enumerate(test_plays):
        out = f'concept_{i+1}_{play["route"].lower()}.png'
        print(f"\n=== Play {i+1}: {play['route']} ===")
        visualize_play(play, save_path=out)
        print(f"  > Saved: {out}")
        

