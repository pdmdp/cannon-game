"""Named constants used by the simulation and interface.

The assignment's physics parameters and the shared presentation values are
kept here. Campaign layouts, budgets and narrative data live in their own
modules.

Units (as defined by the assignment):
- lengths in pixels
- time in seconds
- velocity in pixels/second
"""

import math

# ---------------------------------------------------------------------------
# Window / timing (required by the assignment)
# ---------------------------------------------------------------------------
SCREEN_WIDTH = 1280   # width of the game field, in pixels
SCREEN_HEIGHT = 720   # height of the game field, in pixels
FPS = 60              # target update rate of the game loop
MAX_SIMULATION_STEP = 1.0 / FPS  # large Clock dt values are subdivided
MAX_FRAME_DT = 0.25              # suspend/resume cannot fast-forward a shot

# ---------------------------------------------------------------------------
# World physics (design constants)
# ---------------------------------------------------------------------------
# Downward acceleration applied to massive projectiles, in pixels/s^2.
# With a full-power 45-degree bullet shot (~700 px/s) the range is
# v^2 / GRAVITY = 1400 px, so a good shot can cross the whole screen.
GRAVITY = 350.0

# A shared maximum kinetic-energy budget determines the upper muzzle-velocity
# limit for each massive projectile:
#     v_max = sqrt(2 * MUZZLE_ENERGY / mass)
# This is how the assignment's "mass affects the muzzle velocity range" is
# implemented: heavier projectiles fire slower.
MUZZLE_ENERGY = 980_000.0
MUZZLE_VEL_MIN = 120.0  # minimum muzzle velocity the player can select, px/s

# ---------------------------------------------------------------------------
# Bullet (required by the assignment)
# ---------------------------------------------------------------------------
BULLET_MASS = 4.0     # affects its maximum muzzle velocity (see MUZZLE_ENERGY)
BULLET_RADIUS = 18.0  # radius of destroyed obstacle cells around the impact, px

# ---------------------------------------------------------------------------
# Bombshell (required by the assignment)
# ---------------------------------------------------------------------------
BOMB_MASS = 12.0      # heavier than the bullet => lower maximum muzzle velocity
BOMB_RADIUS = 42.0    # radius of destroyed obstacle cells around the blast, px
BOMB_DRILL = 25.0     # how deep it penetrates into an obstacle before exploding, px

# ---------------------------------------------------------------------------
# Laser (required by the assignment)
# ---------------------------------------------------------------------------
LASER_VEL = 1000.0    # fixed muzzle velocity, px/s (NOT controllable by the player)
LASER_IMPULSE = 60.0  # length of the impulse; also its penetration depth, px
LASER_DIST = 10.0     # damage distance around the beam trajectory, px

# Maximum muzzle velocities derived from the masses (used by the aiming UI).
BULLET_VEL_MAX = math.sqrt(2.0 * MUZZLE_ENERGY / BULLET_MASS)  # ~700 px/s
BOMB_VEL_MAX = math.sqrt(2.0 * MUZZLE_ENERGY / BOMB_MASS)      # ~404 px/s

# ---------------------------------------------------------------------------
# Flight & rounds (design constants)
# ---------------------------------------------------------------------------
FIELD_MARGIN = 60.0      # px beyond the field edges where a shot dies
PROJECTILE_TTL = 12.0    # safety lifetime of a shot, s (avoids endless flights)
SHOW_TRAJECTORY_PREVIEW = True  # default value for the Settings toggle
PREVIEW_TIME = 0.8       # how much flight time the aim preview shows, s
PREVIEW_DOTS = 14        # number of dots drawn by the aim preview

# Visual sizes of the projectiles (the DAMAGE radii are the assignment
# constants BULLET_RADIUS / BOMB_RADIUS / LASER_DIST above, not these).
BULLET_DRAW_RADIUS = 5.0
BOMB_DRAW_RADIUS = 8.0
LASER_WIDTH = 3.0

# Impact feedback (design constants).
PARTICLE_SMALL = 14      # debris particles for a small impact
PARTICLE_BIG = 30        # debris particles for a big explosion
PARTICLE_TTL = 0.9       # max particle lifetime, s
PARTICLE_SIZE = 3.0      # side of one debris square, px
PARTICLE_CAP = 160       # fixed renderer pool: no per-frame instruction churn
SHAKE_TIME = 0.3         # screen-shake duration, s
TARGET_HIT_PAUSE = 0.085 # visual impact hold on a target, s

# Story backdrops (design constants).
PARALLAX_FAR = 10.0      # how far the distant backdrop shifts vs aim, px
PARALLAX_NEAR = 24.0     # how far the near rock layer shifts vs aim, px

# Bounds used when a temporary target is requested. Campaign levels provide
# their own target positions, above or below the cannon.
TARGET_MIN_X, TARGET_MAX_X = 700.0, 1210.0
TARGET_MIN_Y, TARGET_MAX_Y = 60.0, 620.0

# ---------------------------------------------------------------------------
# Obstacles (design constants)
# ---------------------------------------------------------------------------
ROCK_CELL = 14.0      # side of one atomic rock cell (small square), px
WORMHOLE_RADIUS = 24.0        # radius of each of the two portals, px
GRAVITONIO_STRENGTH = 900.0   # peak radial acceleration at the core, px/s^2
GRAVITONIO_RANGE = 260.0      # radius of influence of the anomaly, px

# ---------------------------------------------------------------------------
# Cannon & target (design constants)
# ---------------------------------------------------------------------------
CANNON_X = 60.0        # horizontal position of the cannon pivot (left edge), px
CANNON_Y = 130.0       # height of the cannon pivot in the default scene, px
BARREL_LENGTH = 52.0   # length of the drawn barrel, px
TARGET_RADIUS = 22.0   # radius of the target (enemy beacon), px
TARGET_RADII = {       # dedicated hit areas matching the visible silhouettes
    "sprite_beacon": 22.0,
    "sprite_warden": 38.0,
    "sprite_warden_damaged": 38.0,
    "sprite_foreman_core": 46.0,
    "sprite_foreman_damaged": 46.0,
    "sprite_foreman_critical": 46.0,
}

# Aiming limits and control sensitivity.
ANGLE_MIN = -20.0      # lowest barrel elevation, degrees (targets can sit below us)
ANGLE_MAX = 90.0       # highest barrel elevation, degrees (straight up)
ANGLE_STEP = 1.0       # degrees added/removed per arrow-key press (fine tuning)
VEL_STEP = 10.0        # px/s added/removed per scroll tick or arrow-key press
POWER_GUIDE_LEN = 130.0  # extra length of the muzzle power-guide line at full power, px

# ---------------------------------------------------------------------------
# Colors (design constants): RGBA tuples for Kivy canvas instructions
# ---------------------------------------------------------------------------
COLOR_BACKGROUND = (0.03, 0.04, 0.08, 1.0)   # deep space blue-black
COLOR_STAR = (0.85, 0.88, 1.00, 1.0)         # starfield dots
COLOR_CANNON = (0.55, 0.75, 0.95, 1.0)       # outpost turret
COLOR_BULLET = (1.00, 0.85, 0.40, 1.0)       # plasma shot
COLOR_BOMB = (1.00, 0.45, 0.25, 1.0)         # heavy shell
COLOR_LASER = (0.30, 1.00, 0.60, 1.0)        # laser beam
COLOR_ROCK = (0.45, 0.40, 0.38, 1.0)         # destructible asteroid rock
COLOR_PERPETIO = (0.25, 0.28, 0.35, 1.0)     # indestructible rock
COLOR_MIRROR = (0.70, 0.90, 1.00, 1.0)       # bulletproof mirror
COLOR_WORMHOLE = (0.70, 0.40, 1.00, 1.0)     # portal pair
COLOR_GRAVITONIO = (0.35, 0.55, 1.00, 1.0)   # gravity anomaly (attractive)
COLOR_GRAVITONIO_REPULSE = (1.00, 0.50, 0.30, 1.0)  # gravity anomaly (repulsive)
COLOR_ELASTONIO = (1.00, 0.55, 0.85, 1.0)    # bouncy obstacle
COLOR_TARGET = (1.00, 0.25, 0.25, 1.0)       # enemy beacon
COLOR_PLATFORM = (0.16, 0.15, 0.18, 1.0)     # ledge the turret stands on
COLOR_HUD = (0.85, 0.93, 1.00, 1.0)          # HUD text
