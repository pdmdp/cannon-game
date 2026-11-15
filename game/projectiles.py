"""The three projectile types required by the assignment.

Flight behaviour (this file):
- Bullet and Bombshell are massive: gravity bends them into a parabola.
- Laser is massless: it flies in a straight line at the fixed LASER_VEL
  and is an impulse of length LASER_IMPULSE (drawn as a moving segment).

What they do to obstacles differs too (damage radius, drilling,
penetration); those interactions are resolved by the game screen.
"""

import math

from game import constants as C


class Projectile:
    """Base class: position, velocity and the assignment's physics step."""

    massive = True
    kind = "projectile"
    color = C.COLOR_BULLET
    draw_radius = C.BULLET_DRAW_RADIUS   # visual size only, not damage

    def __init__(self, x, y, vx, vy):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.prev_x, self.prev_y = x, y   # previous step position (collision segment)
        self.age = 0.0

    def update(self, dt):
        """One physics step, exactly as the assignment prescribes:
        displace by the instant velocity, then change the vertical
        velocity to simulate gravity (massive projectiles only)."""
        self.prev_x, self.prev_y = self.x, self.y
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.massive:
            self.vy -= C.GRAVITY * dt
        self.age += dt

    def out_of_field(self):
        """True when the shot left the field and can be discarded.

        The top edge is open only for massive shots: gravity may bring a
        Bullet or Bombshell back into view. A massless Laser can never fall
        back, so leaving the top resolves it immediately instead of keeping
        input locked in an invisible ``flying`` state until the safety TTL."""
        m = C.FIELD_MARGIN
        return (self.x < -m or self.x > C.SCREEN_WIDTH + m
                or self.y < -m
                or (not self.massive and self.y > C.SCREEN_HEIGHT + m)
                or self.age > C.PROJECTILE_TTL)


class Bullet(Projectile):
    kind = "bullet"
    color = C.COLOR_BULLET
    draw_radius = C.BULLET_DRAW_RADIUS


class Bombshell(Projectile):
    kind = "bombshell"
    color = C.COLOR_BOMB
    draw_radius = C.BOMB_DRAW_RADIUS


class Laser(Projectile):
    kind = "laser"
    color = C.COLOR_LASER
    massive = False
    draw_radius = C.LASER_WIDTH

    def __init__(self, x, y, vx, vy):
        super().__init__(x, y, vx, vy)
        # Corner points of the flown path: the spawn point plus every
        # mirror bounce (appended by the game). Lets the visible impulse
        # bend around mirror corners instead of clipping through them.
        self.path = [(x, y)]

    def add_bounce(self, x, y):
        self.path.append((x, y))
        if len(self.path) > 8:      # only the recent corners matter
            self.path.pop(0)

    def reset_path(self, x, y):
        """Restart the beam at a new location (used at a wormhole exit:
        the remaining tail is swallowed by the entry portal)."""
        self.path = [(x, y)]

    def beam_points(self):
        """Flat list [x0, y0, x1, y1, ...] for a kivy Line: the visible
        impulse, walking back LASER_IMPULSE from the head along the flown
        path, turning at each recorded bounce corner."""
        points = [self.x, self.y]
        remaining = C.LASER_IMPULSE
        hx, hy = self.x, self.y
        for px, py in reversed(self.path):
            seg = math.hypot(hx - px, hy - py)
            if seg >= remaining:
                if seg > 0:
                    ux, uy = (px - hx) / seg, (py - hy) / seg
                    points.extend((hx + ux * remaining, hy + uy * remaining))
                break
            points.extend((px, py))
            remaining -= seg
            hx, hy = px, py
        return points


PROJECTILE_CLASSES = {
    "bullet": Bullet,
    "bombshell": Bombshell,
    "laser": Laser,
}


def spawn_projectile(kind, x, y, vx, vy):
    """Create the projectile of the requested type at the muzzle."""
    return PROJECTILE_CLASSES[kind](x, y, vx, vy)
