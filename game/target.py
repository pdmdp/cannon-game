"""The target, represented in the story as a Rust Swarm signal beacon.

The assignment: the round terminates when a projectile hits the target.
The target can sit at any height relative to the cannon (above or below).
"""

import math

from kivy.graphics import Color, Ellipse, Line, Rectangle

from game import art
from game import constants as C
from game import physics

# Drawn size per sprite; each also has a silhouette-matched hit radius.
_SPRITE_SIZES = {
    "sprite_beacon": 66,
    "sprite_warden": 100,
    "sprite_warden_damaged": 100,
    "sprite_foreman_core": 118,
    "sprite_foreman_damaged": 118,
    "sprite_foreman_critical": 118,
}


class Target:
    """A pulsing beacon with a circular hit area of radius TARGET_RADIUS."""

    def __init__(self, x, y, sprite="sprite_beacon"):
        self.x = x
        self.y = y
        self.sprite = sprite
        self.radius = C.TARGET_RADII.get(sprite, C.TARGET_RADIUS)
        self._phase = 0.0
        self._ins = {}   # canvas instructions updated by refresh()

    def draw_on(self, group):
        """Add the beacon's drawing to an InstructionGroup (called once).
        Uses the illustrated sprite when available, else canvas shapes."""
        r = self.radius
        texture = art.keyed_texture(self.sprite)
        if texture is not None:
            size = _SPRITE_SIZES.get(self.sprite, 66)
            aspect = texture.size[0] / max(1.0, texture.size[1])
            width = size if aspect >= 1 else size * aspect
            height = size / aspect if aspect >= 1 else size
            group.add(Color(1, 1, 1, 1))
            group.add(Rectangle(texture=texture,
                                pos=(self.x - width / 2,
                                     self.y - height / 2),
                                size=(width, height)))
        else:
            # Soft glow halo.
            group.add(Color(C.COLOR_TARGET[0], C.COLOR_TARGET[1],
                            C.COLOR_TARGET[2], 0.16))
            group.add(Ellipse(pos=(self.x - 1.8 * r, self.y - 1.8 * r),
                              size=(3.6 * r, 3.6 * r)))
            # Solid core.
            group.add(Color(*C.COLOR_TARGET))
            group.add(Ellipse(pos=(self.x - 0.55 * r, self.y - 0.55 * r),
                              size=(1.1 * r, 1.1 * r)))
        # Brief white impact wash, normally transparent.
        flash_color = Color(1.0, 0.88, 0.68, 0.0)
        flash = Ellipse(pos=(self.x - 1.25 * r, self.y - 1.25 * r),
                        size=(2.5 * r, 2.5 * r))
        group.add(flash_color)
        group.add(flash)
        self._ins["flash_color"] = flash_color

        # Pulsing ring showing the true hit radius (sprite or not).
        ring_color = Color(C.COLOR_TARGET[0], C.COLOR_TARGET[1],
                           C.COLOR_TARGET[2], 0.9)
        ring = Line(circle=(self.x, self.y, r), width=2)
        group.add(ring_color)
        group.add(ring)
        self._ins["ring_color"] = ring_color
        self._ins["ring"] = ring

    def set_hit_flash(self, active):
        if "flash_color" in self._ins:
            self._ins["flash_color"].a = 0.92 if active else 0.0

    def refresh(self, dt):
        """Animate the beacon (pure decoration; the hit radius is fixed)."""
        if not self._ins:
            return
        self._phase += dt
        pulse = 0.5 + 0.5 * math.sin(3.0 * self._phase)
        self._ins["ring"].circle = (self.x, self.y,
                                    self.radius * (0.70 + 0.30 * pulse))
        self._ins["ring_color"].a = 0.35 + 0.55 * pulse

    def hit_by_segment(self, ax, ay, bx, by):
        """Did a projectile moving from A to B during this step hit the beacon?"""
        return physics.segment_circle_hit(ax, ay, bx, by,
                                          self.x, self.y, self.radius)

    def to_dict(self):
        return {"x": self.x, "y": self.y, "sprite": self.sprite}
