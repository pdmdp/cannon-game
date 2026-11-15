"""The hand-crafted campaign: 10 levels, each introducing one mechanic.

Levels are pure data (easy to read, tweak and serialize):
- "target": where the Rust Swarm beacon sits (any height vs the cannon,
  as the assignment requires; some sit low, some float high).
- "budget": shots allowed on Normal difficulty; Easy is unlimited and
  Hard shrinks it (see shot_budget()). The round's shot count is thus
  declared at the beginning of each round, per the assignment.
- "obstacles": specs as tuples -> instantiated by build_level().

Design intent per level (the campaign teaching order):
 1 aiming    2 dig through rock      3 bombshell drilling
 4 perpetio (arc over)               5 laser + mirror periscope
6 mirror through a narrow window    7 wormhole
8 gravitonio attract                9 elastonio bank shot
10 several later mechanics combined across three rounds.
"""

from game.obstacles import Elastonio, Gravitonio, Mirror, Perpetio, Rock, Wormhole

# Color grading is decorative only.  Layouts, collisions and scoring stay
# deterministic so solutions and Hall of Fame results remain comparable.
PALETTES = {
    "outpost_cyan": {"tint": (0.10, 0.50, 0.72, 0.10), "accent": (0.35, 0.90, 1.00)},
    "rubble_amber": {"tint": (0.62, 0.32, 0.08, 0.12), "accent": (1.00, 0.68, 0.28)},
    "blast_orange": {"tint": (0.72, 0.20, 0.05, 0.11), "accent": (1.00, 0.38, 0.16)},
    "steel_blue": {"tint": (0.12, 0.28, 0.52, 0.12), "accent": (0.58, 0.78, 1.00)},
    "mirror_white_red": {"tint": (0.36, 0.42, 0.55, 0.10), "accent": (1.00, 0.34, 0.34)},
    "canyon_cyan": {"tint": (0.05, 0.52, 0.60, 0.10), "accent": (0.34, 1.00, 0.94)},
    "wormhole_violet": {"tint": (0.40, 0.12, 0.65, 0.13), "accent": (0.78, 0.44, 1.00)},
    "gravity_blue": {"tint": (0.05, 0.25, 0.72, 0.13), "accent": (0.38, 0.66, 1.00)},
    "elastonio_magenta": {"tint": (0.62, 0.08, 0.46, 0.12), "accent": (1.00, 0.42, 0.86)},
    "foreman_hazard": {"tint": (0.68, 0.12, 0.03, 0.14), "accent": (1.00, 0.56, 0.16)},
}

LEVELS = [
    {
        "name": "TRAINING RANGE",
        "flavor": "Beacon one is exposed in open space.",
        "sector": "PV-1 OUTER RANGE",
        "objective": "Destroy the exposed route beacon.",
        "par": 1,
        "palette": "outpost_cyan",
        "decor": "outpost",
        "budget": 3,
        "target": (1000, 300),
        "obstacles": [],
    },
    {
        "name": "THE RUBBLE LINE",
        "flavor": "The route beacon is protected by loose asteroid rubble.",
        "sector": "MERIDIAN APPROACH",
        "objective": "Break through or arc over the rubble.",
        "par": 1,
        "palette": "rubble_amber",
        "decor": "debris",
        "budget": 5,
        "target": (950, 120),
        "obstacles": [
            ("rock", 560, 0, 4, 22),
        ],
    },
    {
        "name": "DIG DEEP",
        "flavor": "A full-height rock wall seals the route.",
        "sector": "MERIDIAN REFINERY ROAD",
        "objective": "Drill a breach, then destroy the beacon.",
        "par": 2,
        "palette": "blast_orange",
        "decor": "blast_marks",
        "budget": 6,
        "target": (790, 130),
        "obstacles": [
            # Full-height thickness: no ballistic arc can bypass it. A
            # bombshell drills a traversable breach for the following shot.
            # Extend beyond the visible top because high arcs may leave the
            # screen and fall back in; the only route is a drilled breach.
            ("rock", 500, 0, 5, 100),
        ],
    },
    {
        "name": "THE PERPETIO SHIELD",
        "flavor": "Indestructible perpetio plate blocks a direct shot.",
        "sector": "MERIDIAN POWER GRID",
        "objective": "Arc a massive shell over the shield.",
        "par": 1,
        "palette": "steel_blue",
        "decor": "steel_grid",
        "budget": 4,
        "target": (1000, 130),
        "obstacles": [
            ("perpetio", 620, 0, 4, 18),
        ],
    },
    {
        "name": "LIGHT BENDS",
        "flavor": "The Mirror Warden protects the fifth route beacon.",
        "sector": "MERIDIAN EVACUATION LANE",
        "objective": "Reflect laser fire around the Warden's shield.",
        "par": 2,
        "palette": "mirror_white_red",
        "decor": "mirror_array",
        "budget": 4,
        "target": (900, 490),
        "obstacles": [
            ("perpetio", 560, 0, 4, 30),
            ("mirror", 380, 110, 420, 150),
            ("mirror", 380, 470, 420, 510),
        ],
        # The Mirror Warden adds a second layout after the base round. Each
        # round ends when a projectile hits its target.
        "boss": {
            "name": "MIRROR WARDEN",
            "sprite": "sprite_warden",
            "phases": [
                {   # phase 2: the arrays redeploy lower, armor shrinks
                    "target": (900, 250),
                    "obstacles": [
                        ("perpetio", 560, 0, 4, 17),
                        ("mirror", 380, 110, 420, 150),
                        ("mirror", 380, 230, 420, 270),
                    ],
                },
            ],
        },
    },
    {
        "name": "MIRROR CANYON",
        "flavor": "A narrow opening crosses the armored canyon.",
        "sector": "HALDE WATER PLANT",
        "objective": "Thread a shot through the open window.",
        "par": 1,
        "palette": "canyon_cyan",
        "decor": "canyon",
        "budget": 4,
        "target": (1000, 130),
        "obstacles": [
            ("perpetio", 760, 0, 4, 22),
            ("perpetio", 700, 380, 10, 3),
            ("mirror", 981, 439, 1059, 376),
        ],
    },
    {
        "name": "THE WORMHOLE RUN",
        "flavor": "A linked wormhole pair crosses the sealed field.",
        "sector": "HALDE ICE TUNNELS",
        "objective": "Route a shot through the wormhole.",
        "par": 1,
        "palette": "wormhole_violet",
        "decor": "portal_grid",
        "budget": 4,
        "target": (1150, 300),
        "obstacles": [
            ("perpetio", 560, 0, 5, 40),
            ("wormhole", 300, 130, 900, 300),
        ],
    },
    {
        "name": "GRAVITY WELL",
        "flavor": "A gravity anomaly bends every massive projectile.",
        "sector": "NEW SUN FARM RING",
        "objective": "Use gravity to curve a shell past the wall.",
        "par": 1,
        "palette": "gravity_blue",
        "decor": "gravity_dust",
        "budget": 5,
        "target": (1155, 327),
        "obstacles": [
            ("perpetio", 520, 0, 4, 18),
            ("gravitonio", 700, 420, False),
        ],
    },
    {
        "name": "REPULSOR RIDGE",
        "flavor": "The ninth beacon is hidden under an armored roof.",
        "sector": "NEW SUN FREIGHT TUNNELS",
        "objective": "Bank a massive shell from elastonio.",
        "par": 1,
        "palette": "elastonio_magenta",
        "decor": "elastic_ridge",
        "budget": 5,
        "target": (1000, 130),
        "obstacles": [
            ("perpetio", 900, 0, 3, 16),
            ("perpetio", 880, 230, 9, 2),
            ("elastonio", 1160, 80, 1160, 320),
        ],
    },
    {
        "name": "THE GAUNTLET",
        "flavor": "The Foreman's core is rebuilding the colony route.",
        "sector": "FOREMAN COMMAND YARD",
        "objective": "Destroy all three core phases.",
        "par": 3,
        "palette": "foreman_hazard",
        "decor": "hazard",
        "budget": 7,
        # Initial round: enter the wormhole, then bank a massive shell off the
        # elastonio behind the target. A laser passes through the pane.
        "target": (980, 380),
        "obstacles": [
            ("perpetio", 600, 0, 5, 100),
            ("wormhole", 300, 130, 900, 300),
            ("elastonio", 1107, 160, 1233, 340),
        ],
        "boss": {
            "name": "THE FOREMAN",
            "sprite": "sprite_foreman_core",
            "phases": [
                {   # Second round: wormhole access plus a mirror redirects the
                    # laser downward; massive shots splat on the mirror.
                    "target": (1070, 580),
                    "obstacles": [
                        ("perpetio", 590, 0, 5, 100),
                        ("wormhole", 300, 198, 1000, 500),
                        ("mirror", 1150, 440, 1150, 660),
                    ],
                },
                {   # Third round: the laser and bombshell remain invalid, but
                    # the wider upper channel now supports two gravity-bent
                    # bullet bands.  The longer phase-local preview makes the
                    # bend readable without exposing an exact solution.
                    "target": (1050, 120),
                    "preview": {"time": 2.2, "dots": 30},
                    "obstacles": [
                        ("perpetio", 600, 0, 5, 24),
                        ("perpetio", 600, 530, 50, 3),
                        ("perpetio", 780, 325, 4, 4),
                        ("perpetio", 940, 105, 2, 6),
                        ("gravitonio", 800, 330, False),
                    ],
                },
            ],
        },
    },
]

_GRID_BUILDERS = {"rock": Rock, "perpetio": Perpetio}
_PANE_BUILDERS = {"mirror": Mirror, "elastonio": Elastonio}


def level_count():
    return len(LEVELS)


# The story hands weapons out as Toko builds them: the bombshell arrives
# with level 3's briefing, the laser with level 5's. Earlier levels can
# only use what has been delivered.
WEAPON_UNLOCKS = {"bullet": 0, "bombshell": 2, "laser": 4}


def weapons_for(index):
    """The weapon kinds available at this level (story unlocks)."""
    return tuple(w for w, lvl in WEAPON_UNLOCKS.items() if index >= lvl)


def boss_info(index):
    """The level's boss dict ({"name", "sprite", "phases"}) or None."""
    return LEVELS[index].get("boss")


def phase_count(index):
    """How many rounds this level takes: 1, or 1 + extra boss phases."""
    boss = boss_info(index)
    return 1 + len(boss["phases"]) if boss else 1


def _build_obstacles(specs):
    obstacles = []
    for spec in specs:
        kind, args = spec[0], spec[1:]
        if kind in _GRID_BUILDERS:
            obstacles.append(_GRID_BUILDERS[kind](*args))
        elif kind in _PANE_BUILDERS:
            obstacles.append(_PANE_BUILDERS[kind](*args))
        elif kind == "wormhole":
            obstacles.append(Wormhole(*args))
        elif kind == "gravitonio":
            x, y, repulsive = args
            obstacles.append(Gravitonio(x, y, repulsive=repulsive))
        else:
            raise ValueError(f"unknown obstacle kind: {kind!r}")
    return obstacles


def build_level(index, phase=0):
    """Instantiate level `index` (0-based) at the given boss phase
    (phase 0 = the base layout). Returns (obstacle objects, target)."""
    data = LEVELS[index]
    if phase == 0:
        return _build_obstacles(data["obstacles"]), data["target"]
    spec = data["boss"]["phases"][phase - 1]
    return _build_obstacles(spec["obstacles"]), spec["target"]


def preview_config(index, phase=0):
    """Return optional, data-driven trajectory-preview overrides."""
    data = LEVELS[index]
    spec = data if phase == 0 else data["boss"]["phases"][phase - 1]
    return dict(spec.get("preview", {}))


def shot_budget(index, difficulty):
    """Shots allowed for this level at the given difficulty.
    None means unlimited (the assignment allows unlimited rounds)."""
    base = LEVELS[index]["budget"]
    if difficulty == "easy":
        return None
    if difficulty == "hard":
        return max(1, round(base * 0.6))
    return base
