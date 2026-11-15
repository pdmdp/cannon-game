"""The player's cannon: aiming state, geometry and drawing.

The cannon sits at a fixed pivot point. The player only controls:
- the barrel elevation angle,
- the muzzle velocity,
- the projectile type,
which are the three controls required by the assignment.
"""

import math

from kivy.graphics import (Color, Ellipse, Line, PopMatrix, PushMatrix,
                           Rectangle, Rotate)

from game import art
from game import constants as C

# Order matters: keyboard keys 1, 2, 3 select these types in order.
PROJECTILE_TYPES = ("bullet", "bombshell", "laser")

PROJECTILE_COLORS = {
    "bullet": C.COLOR_BULLET,
    "bombshell": C.COLOR_BOMB,
    "laser": C.COLOR_LASER,
}


def color_hex(color):
    """'rrggbb' string of an RGBA tuple, for Kivy markup [color=...] tags."""
    return "".join(f"{int(round(channel * 255)):02x}" for channel in color[:3])


PROJECTILE_COLORS_HEX = {name: color_hex(col) for name, col in PROJECTILE_COLORS.items()}


class Cannon:
    """Aiming state of the turret plus its canvas drawing."""

    def __init__(self, pivot_x=C.CANNON_X, pivot_y=C.CANNON_Y):
        self.pivot_x = pivot_x
        self.pivot_y = pivot_y
        self.angle = 45.0                        # barrel elevation, degrees (0 = horizontal)
        self.projectile = "bullet"
        self.velocity = 0.75 * C.BULLET_VEL_MAX  # current muzzle velocity, px/s
        self._ins = {}                           # canvas instructions updated by refresh()
        self._recoil = 0.0                       # 1.0 right after firing, decays to 0

    # ------------------------------------------------------------------
    # Aiming state
    # ------------------------------------------------------------------

    def velocity_range(self):
        """(min, max) muzzle velocity allowed for the selected projectile.

        MUZZLE_ENERGY sets the maximum kinetic-energy budget for massive
        projectiles, so v_max = sqrt(2 * E / mass): the heavy bombshell has a
        lower upper limit than the bullet. The player may choose a speed below
        that limit. The massless laser always uses LASER_VEL (assignment rule).
        """
        if self.projectile == "bullet":
            return C.MUZZLE_VEL_MIN, C.BULLET_VEL_MAX
        if self.projectile == "bombshell":
            return C.MUZZLE_VEL_MIN, C.BOMB_VEL_MAX
        return C.LASER_VEL, C.LASER_VEL

    def aim_at(self, x, y):
        """Point the barrel toward (x, y), as used for mouse aiming."""
        self.angle = math.degrees(math.atan2(y - self.pivot_y, x - self.pivot_x))
        self._clamp()

    def nudge_angle(self, delta_deg):
        """Fine-tune the elevation with the keyboard."""
        self.angle += delta_deg
        self._clamp()

    def nudge_velocity(self, delta):
        """Adjust the muzzle velocity (scroll wheel / arrow keys)."""
        self.velocity += delta
        self._clamp()

    def select_projectile(self, name):
        """Switch projectile type; the velocity is re-clamped to its range."""
        if name in PROJECTILE_TYPES:
            self.projectile = name
            self._clamp()

    def _clamp(self):
        """Keep angle and velocity inside their allowed ranges."""
        self.angle = max(C.ANGLE_MIN, min(C.ANGLE_MAX, self.angle))
        vmin, vmax = self.velocity_range()
        self.velocity = max(vmin, min(vmax, self.velocity))

    # ------------------------------------------------------------------
    # Serialization (Save/Load)
    # ------------------------------------------------------------------

    def to_dict(self):
        return {"angle": self.angle, "velocity": self.velocity,
                "projectile": self.projectile}

    def restore(self, data):
        """Adopt a saved aiming state (the drawing refreshes itself)."""
        self.projectile = data["projectile"]
        self.angle = float(data["angle"])
        self.velocity = float(data["velocity"])
        self._clamp()
        self.refresh()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def direction(self):
        """Unit vector (dx, dy) along the barrel."""
        rad = math.radians(self.angle)
        return math.cos(rad), math.sin(rad)

    def muzzle_pos(self):
        """Tip of the barrel, where projectiles spawn."""
        dx, dy = self.direction()
        return self.pivot_x + dx * C.BARREL_LENGTH, self.pivot_y + dy * C.BARREL_LENGTH

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw_on(self, canvas):
        """Create the cannon's canvas instructions (call once).

        Uses the illustrated turret sprites when they exist in
        assets/art/ (the barrel image rotates around the pivot);
        otherwise falls back to the original canvas drawing.
        """
        barrel_tex = art.keyed_texture("sprite_cannon_barrel")
        # The low pedestal keeps a horizontal silhouette at every elevation.
        # Use the taller bundled base if that sprite is unavailable.
        base_name = ("sprite_cannon_base_low"
                     if art.has_art("sprite_cannon_base_low")
                     else "sprite_cannon_base")
        base_tex = art.keyed_texture(base_name)
        radius = 16
        with canvas:
            if base_tex is None:
                # Fallback ledge for the canvas turret; the illustrated
                # backdrops already provide the ground in sprite mode.
                Color(*C.COLOR_PLATFORM)
                Rectangle(pos=(0, 0),
                          size=(2 * self.pivot_x, self.pivot_y - 14))

            # Power guide: faint line from the muzzle showing the shot power.
            self._ins["guide_color"] = Color(*C.COLOR_BULLET)
            self._ins["guide"] = Line(points=[], width=1.2)

            if barrel_tex is not None:
                # Preserve the processed sprite's aspect ratio. Its visible
                # muzzle lands exactly at BARREL_LENGTH from the pivot.
                # The rectangle slides backward briefly on recoil.
                width = C.BARREL_LENGTH + 16
                ratio = barrel_tex.size[1] / max(1.0, barrel_tex.size[0])
                height = width * ratio
                PushMatrix()
                self._ins["rotate"] = Rotate(
                    angle=self.angle, origin=(self.pivot_x, self.pivot_y))
                Color(1, 1, 1, 1)
                self._barrel_base = (self.pivot_x - 16,
                                     self.pivot_y - height / 2)
                self._ins["barrel_rect"] = Rectangle(
                    texture=barrel_tex, pos=self._barrel_base,
                    size=(width, height))
                PopMatrix()
            else:
                Color(*C.COLOR_CANNON)
                self._ins["barrel"] = Line(points=[], width=6)

            if base_tex is not None:
                low_pedestal = base_name == "sprite_cannon_base_low"
                # Soft cyan rim light separates the dark mount from the ridge.
                Color(C.COLOR_CANNON[0], C.COLOR_CANNON[1],
                      C.COLOR_CANNON[2], 0.18)
                if low_pedestal:
                    Ellipse(pos=(self.pivot_x - 55, self.pivot_y - 34),
                            size=(110, 42))
                else:
                    Ellipse(pos=(self.pivot_x - 50, self.pivot_y - 44),
                            size=(100, 88))
                Color(1, 1, 1, 1)
                ratio = base_tex.size[1] / max(1.0, base_tex.size[0])
                width = 110 if low_pedestal else 92
                height = width * ratio
                # In the low sprite the circular trunnion sits at 80% of
                # the cropped texture height. Anchor that joint, rather than
                # the rectangle centre, to the physical firing pivot.
                anchor_y = 0.80 if low_pedestal else 0.50
                Rectangle(texture=base_tex,
                          pos=(self.pivot_x - width / 2,
                               self.pivot_y - height * anchor_y),
                          size=(width, height))
            else:
                # Soft glow behind the turret dome, then the dome itself.
                Color(C.COLOR_CANNON[0], C.COLOR_CANNON[1],
                      C.COLOR_CANNON[2], 0.12)
                Ellipse(pos=(self.pivot_x - 30, self.pivot_y - 30),
                        size=(60, 60))
                Color(C.COLOR_CANNON[0], C.COLOR_CANNON[1],
                      C.COLOR_CANNON[2], 0.20)
                Ellipse(pos=(self.pivot_x - 22, self.pivot_y - 22),
                        size=(44, 44))
                Color(*C.COLOR_CANNON)
                Ellipse(pos=(self.pivot_x - radius, self.pivot_y - radius),
                        size=(2 * radius, 2 * radius))
        self.refresh()

    def kick(self):
        """Start the firing recoil (the barrel slides back briefly)."""
        self._recoil = 1.0

    def refresh(self):
        """Update the moving canvas instructions to match the current state."""
        if not self._ins:
            return   # no canvas instructions have been attached
        mx, my = self.muzzle_pos()
        if "rotate" in self._ins:
            self._ins["rotate"].angle = self.angle
            if "barrel_rect" in self._ins:
                bx, by = self._barrel_base
                self._ins["barrel_rect"].pos = (bx - 14.0 * self._recoil, by)
            self._recoil *= 0.82
        else:
            self._ins["barrel"].points = [self.pivot_x, self.pivot_y, mx, my]

        # Guide length grows with the velocity fraction of its allowed range.
        vmin, vmax = self.velocity_range()
        fraction = 1.0 if vmax == vmin else (self.velocity - vmin) / (vmax - vmin)
        dx, dy = self.direction()
        length = 30.0 + fraction * C.POWER_GUIDE_LEN
        color = PROJECTILE_COLORS[self.projectile]
        self._ins["guide_color"].rgba = (color[0], color[1], color[2], 0.45)
        self._ins["guide"].points = [mx, my, mx + dx * length, my + dy * length]
