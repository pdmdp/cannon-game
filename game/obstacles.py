"""Obstacles.

- Rock: destructible, made of atomic square cells (ROCK_CELL px) exactly
  as the assignment describes; destroying means removing cells.
- Perpetio: identical grid, but no projectile can destroy it.
- Mirror: indestructible segment that reflects laser impulses.
- Elastonio: indestructible segment that reflects MASSIVE projectiles
  (the mirror's counterpart); lasers pass straight through it.
- Wormhole: two paired portals; whatever enters one exits the other
  with its velocity unchanged.
- Gravitonio: a radial gravity anomaly (attractive or repulsive) that
  bends massive projectiles inside its range; it is a field, not a wall.

The obstacle classes share a small protocol for geometry, damage and drawing.
The game screen uses explicit branches for reflection, teleportation and
gravity-field behaviour.
"""

import math
import random

from kivy.graphics import Color, Ellipse, Line, Rectangle

from game import art
from game import constants as C
from game import physics


class Rock:
    """A grid of destructible cells anchored at (x, y) = bottom-left corner.

    Alive cells live in the set self.cells as (col, row) pairs; geometry
    is derived from the anchor and ROCK_CELL, so membership tests and
    damage are simple set operations that are easy to draw, count and
    serialize.
    """

    kind = "rock"
    destructible = True
    color = C.COLOR_ROCK
    texture_name = "tex_rock"   # seamless texture the cells sample from
    texture_tile = 224.0        # design px covered by one texture repeat

    def __init__(self, x, y, cols, rows):
        self.x, self.y = x, y
        self.cols, self.rows = cols, rows
        self.cells = {(c, r) for c in range(cols) for r in range(rows)}
        # Per-cell brightness so the rock looks textured, deterministic
        # for a given anchor (the same rock always looks the same).
        rng = random.Random(int(x * 31 + y * 17))
        self._shades = {cell: rng.uniform(0.94, 1.06) for cell in self.cells}
        self._group = None   # InstructionGroup adopted via attach()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def cell_center(self, cell):
        col, row = cell
        return (self.x + (col + 0.5) * C.ROCK_CELL,
                self.y + (row + 0.5) * C.ROCK_CELL)

    def cell_at(self, px, py):
        """The alive cell containing the point, or None."""
        col = int((px - self.x) // C.ROCK_CELL)
        row = int((py - self.y) // C.ROCK_CELL)
        if (col, row) in self.cells:
            return (col, row)
        return None

    def left_x(self):
        """Leftmost extent of the obstacle (used for target placement)."""
        return self.x

    def to_dict(self):
        """Serializable state, including exactly which cells survive."""
        return {"kind": self.kind, "x": self.x, "y": self.y,
                "cols": self.cols, "rows": self.rows,
                "cells": sorted(self.cells)}

    @classmethod
    def from_dict(cls, data):
        rock = cls(data["x"], data["y"], data["cols"], data["rows"])
        # JSON stores cell pairs as lists; the set wants tuples back.
        rock.cells = {tuple(cell) for cell in data["cells"]}
        return rock

    def blocks_point(self, px, py):
        """Would this obstacle stop a projectile passing through the point?
        The aim preview uses this test to truncate its sampled dots."""
        return self.cell_at(px, py) is not None

    def overlaps_circle(self, cx, cy, radius):
        """True if any alive cell is (approximately) within the circle.

        Used when placing targets so they never spawn inside a rock."""
        reach = radius + 0.71 * C.ROCK_CELL   # half diagonal of a cell
        reach2 = reach * reach
        for cell in self.cells:
            ccx, ccy = self.cell_center(cell)
            dx, dy = ccx - cx, ccy - cy
            if dx * dx + dy * dy <= reach2:
                return True
        return False

    # ------------------------------------------------------------------
    # Damage (Perpetio overrides these with no-ops)
    # ------------------------------------------------------------------

    def destroy_circle(self, cx, cy, radius):
        """Remove every alive cell whose center lies within the circle.
        Returns how many cells were destroyed."""
        radius2 = radius * radius
        doomed = []
        for cell in self.cells:
            ccx, ccy = self.cell_center(cell)
            dx, dy = ccx - cx, ccy - cy
            if dx * dx + dy * dy <= radius2:
                doomed.append(cell)
        for cell in doomed:
            self.cells.discard(cell)
        return len(doomed)

    def destroy_corridor(self, ax, ay, bx, by, width):
        """Remove every alive cell whose center lies within `width` of the
        segment A->B (the laser's damage corridor). Returns the count."""
        width2 = width * width
        doomed = []
        for cell in self.cells:
            ccx, ccy = self.cell_center(cell)
            if physics.point_segment_dist2(ccx, ccy, ax, ay, bx, by) <= width2:
                doomed.append(cell)
        for cell in doomed:
            self.cells.discard(cell)
        return len(doomed)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def attach(self, group):
        """Adopt an InstructionGroup to draw into (then redraw on damage)."""
        self._group = group
        self.redraw()

    def redraw(self):
        if self._group is None:
            return
        self._group.clear()
        gap = 0.0   # shared edges read as one continuous destructible surface
        side = C.ROCK_CELL - gap
        texture = art.texture(self.texture_name)
        if texture is not None:
            # Each cell samples the region of the seamless texture that
            # sits at its own world position, so the wall reads as one
            # continuous rock face that shatters along the cell grid.
            texture.wrap = "repeat"
            tile = self.texture_tile
            for cell in sorted(self.cells):
                col, row = cell
                x = self.x + col * C.ROCK_CELL
                y = self.y + row * C.ROCK_CELL
                u0, v0 = x / tile, y / tile
                du, dv = side / tile, side / tile
                shade = self._shades[cell]
                self._group.add(Color(shade, shade, shade, 1.0))
                self._group.add(Rectangle(
                    pos=(x, y), size=(side, side), texture=texture,
                    tex_coords=(u0, v0, u0 + du, v0,
                                u0 + du, v0 + dv, u0, v0 + dv)))
            return
        # Fallback: the original flat-color cells.
        r, g, b = self.color[:3]
        for cell in sorted(self.cells):
            shade = self._shades[cell]
            self._group.add(Color(min(1.0, r * shade), min(1.0, g * shade),
                                  min(1.0, b * shade), 1.0))
            col, row = cell
            self._group.add(Rectangle(
                pos=(self.x + col * C.ROCK_CELL, self.y + row * C.ROCK_CELL),
                size=(side, side)))


class Perpetio(Rock):
    """Like Rock, but indestructible: damage calls do nothing (assignment)."""

    kind = "perpetio"
    destructible = False
    color = C.COLOR_PERPETIO
    texture_name = "tex_perpetio"

    def __init__(self, x, y, cols, rows):
        super().__init__(x, y, cols, rows)
        # Flatter texture: perpetio looks denser and more uniform.
        rng = random.Random(int(x * 31 + y * 17))
        self._shades = {cell: rng.uniform(0.98, 1.02) for cell in self.cells}

    def destroy_circle(self, cx, cy, radius):
        return 0

    def destroy_corridor(self, ax, ay, bx, by, width):
        return 0


class Mirror:
    """Bulletproof Mirror (assignment): an indestructible segment that
    reflects laser impulses. Massive projectiles explode against it
    without drilling (it is bulletproof) and without harming it.

    It owns no cells, so cell_at is always None: the game resolves mirror
    hits with a direct intersection test between the flight and pane segments.
    """

    kind = "mirror"
    destructible = False
    color = C.COLOR_MIRROR

    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self._group = None

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def segment(self):
        return (self.x1, self.y1, self.x2, self.y2)

    def normal(self):
        """Unit normal of the segment. The sign (which side it points to)
        does not matter: the reflection formula gives the same result."""
        dx, dy = self.x2 - self.x1, self.y2 - self.y1
        length = math.hypot(dx, dy) or 1.0
        return (-dy / length, dx / length)

    def left_x(self):
        """Leftmost extent of the obstacle (used for target placement)."""
        return min(self.x1, self.x2)

    def to_dict(self):
        return {"kind": self.kind, "x1": self.x1, "y1": self.y1,
                "x2": self.x2, "y2": self.y2}

    @classmethod
    def from_dict(cls, data):
        return cls(data["x1"], data["y1"], data["x2"], data["y2"])

    # ------------------------------------------------------------------
    # Obstacle protocol
    # ------------------------------------------------------------------

    def cell_at(self, px, py):
        return None   # no cells: hits use the segment intersection routine

    def blocks_point(self, px, py):
        near = 4.0    # px: how close a preview dot may get to the glass
        return physics.point_segment_dist2(px, py, *self.segment()) <= near * near

    def overlaps_circle(self, cx, cy, radius):
        return physics.point_segment_dist2(cx, cy, *self.segment()) <= radius * radius

    def destroy_circle(self, cx, cy, radius):
        return 0      # indestructible

    def destroy_corridor(self, ax, ay, bx, by, width):
        return 0      # indestructible

    # ------------------------------------------------------------------
    # Drawing: a bright pane of glass with a soft glow
    # ------------------------------------------------------------------

    def attach(self, group):
        self._group = group
        self.redraw()

    def redraw(self):
        if self._group is None:
            return
        self._group.clear()
        r, g, b = self.color[:3]
        self._group.add(Color(r, g, b, 0.25))
        self._group.add(Line(points=list(self.segment()), width=6))
        self._group.add(Color(r, g, b, 1.0))
        self._group.add(Line(points=list(self.segment()), width=2.2))


class Elastonio(Mirror):
    """Elastonio (assignment, optional): reflects MASSIVE projectiles.

    Geometrically identical to a Mirror, so it inherits everything; only
    who bounces off it differs, and the game screen decides that:
    bullets/bombshells reflect, lasers pass through untouched.
    """

    kind = "elastonio"
    color = C.COLOR_ELASTONIO


class Wormhole:
    """Wormhole (assignment, optional): a two-element indestructible
    obstacle. A projectile hitting either portal continues its trajectory
    out of the other one with the same velocity and a new position.
    """

    kind = "wormhole"
    destructible = False
    color = C.COLOR_WORMHOLE

    def __init__(self, ax, ay, bx, by):
        self.ax, self.ay = ax, ay     # portal A center
        self.bx, self.by = bx, by     # portal B center
        self.radius = C.WORMHOLE_RADIUS
        self._group = None

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def portal_at(self, px, py):
        """'a' or 'b' if the point is inside that portal, else None."""
        r2 = self.radius * self.radius
        if (px - self.ax) ** 2 + (py - self.ay) ** 2 <= r2:
            return "a"
        if (px - self.bx) ** 2 + (py - self.by) ** 2 <= r2:
            return "b"
        return None

    def exit_for(self, px, py):
        """Center of the portal PAIRED with the one containing (px, py)."""
        if self.portal_at(px, py) == "a":
            return (self.bx, self.by)
        return (self.ax, self.ay)

    # ------------------------------------------------------------------
    # Obstacle protocol
    # ------------------------------------------------------------------

    def cell_at(self, px, py):
        return None                    # handled as a teleport, not a wall

    def blocks_point(self, px, py):
        # The preview stops at a portal: what happens beyond is the
        # player's discovery (simulating the exit would spoil the fun).
        return self.portal_at(px, py) is not None

    def overlaps_circle(self, cx, cy, radius):
        reach = radius + self.radius
        return ((cx - self.ax) ** 2 + (cy - self.ay) ** 2 <= reach * reach
                or (cx - self.bx) ** 2 + (cy - self.by) ** 2 <= reach * reach)

    def destroy_circle(self, cx, cy, radius):
        return 0                       # indestructible

    def destroy_corridor(self, ax, ay, bx, by, width):
        return 0                       # indestructible

    def left_x(self):
        return min(self.ax, self.bx) - self.radius

    def to_dict(self):
        return {"kind": self.kind, "ax": self.ax, "ay": self.ay,
                "bx": self.bx, "by": self.by}

    @classmethod
    def from_dict(cls, data):
        return cls(data["ax"], data["ay"], data["bx"], data["by"])

    # ------------------------------------------------------------------
    # Drawing: two ringed portals joined by a very faint thread
    # ------------------------------------------------------------------

    def attach(self, group):
        self._group = group
        self.redraw()

    def redraw(self):
        if self._group is None:
            return
        self._group.clear()
        r, g, b = self.color[:3]
        self._group.add(Color(r, g, b, 0.10))
        self._group.add(Line(points=[self.ax, self.ay, self.bx, self.by],
                             width=1))
        for cx, cy in ((self.ax, self.ay), (self.bx, self.by)):
            rad = self.radius
            self._group.add(Color(r, g, b, 0.18))
            self._group.add(Ellipse(pos=(cx - 1.9 * rad, cy - 1.9 * rad),
                                    size=(3.8 * rad, 3.8 * rad)))
            self._group.add(Color(0.02, 0.02, 0.06, 1.0))
            self._group.add(Ellipse(pos=(cx - rad, cy - rad),
                                    size=(2 * rad, 2 * rad)))
            self._group.add(Color(r, g, b, 0.95))
            self._group.add(Line(circle=(cx, cy, rad), width=2))
            self._group.add(Color(r, g, b, 0.55))
            self._group.add(Line(circle=(cx, cy, rad * 0.55), width=1.4))


class Gravitonio:
    """Gravitonio (assignment, optional): locally alters the gravity.

    A radial force field acting on MASSIVE projectiles only: inside
    GRAVITONIO_RANGE it accelerates them toward (attractive) or away from
    (repulsive) its center, fading linearly with distance. It is a pure
    field: nothing collides with it and nothing can destroy it.
    """

    kind = "gravitonio"
    destructible = False

    def __init__(self, x, y, repulsive=False):
        self.x, self.y = x, y
        self.repulsive = repulsive
        self.color = (C.COLOR_GRAVITONIO_REPULSE if repulsive
                      else C.COLOR_GRAVITONIO)
        self._group = None

    # ------------------------------------------------------------------
    # The field itself
    # ------------------------------------------------------------------

    def field_accel(self, px, py):
        """Acceleration (ax, ay) the anomaly applies at point (px, py).

        Magnitude fades linearly from GRAVITONIO_STRENGTH at the core to
        zero at GRAVITONIO_RANGE; the direction is radial (assignment:
        both velocity components are affected)."""
        dx, dy = self.x - px, self.y - py
        dist = math.hypot(dx, dy)
        if dist >= C.GRAVITONIO_RANGE or dist < 1e-6:
            return (0.0, 0.0)
        strength = C.GRAVITONIO_STRENGTH * (1.0 - dist / C.GRAVITONIO_RANGE)
        if self.repulsive:
            strength = -strength
        return (dx / dist * strength, dy / dist * strength)

    # ------------------------------------------------------------------
    # Obstacle protocol (a field: nothing to hit, nothing to destroy)
    # ------------------------------------------------------------------

    def cell_at(self, px, py):
        return None

    def blocks_point(self, px, py):
        return False                   # the preview flies through (and bends)

    def overlaps_circle(self, cx, cy, radius):
        # Only the small core is kept clear (e.g. for target placement).
        reach = radius + 24.0
        return (cx - self.x) ** 2 + (cy - self.y) ** 2 <= reach * reach

    def destroy_circle(self, cx, cy, radius):
        return 0

    def destroy_corridor(self, ax, ay, bx, by, width):
        return 0

    def left_x(self):
        return self.x - 24.0

    def to_dict(self):
        return {"kind": self.kind, "x": self.x, "y": self.y,
                "repulsive": self.repulsive}

    @classmethod
    def from_dict(cls, data):
        return cls(data["x"], data["y"], repulsive=data["repulsive"])

    # ------------------------------------------------------------------
    # Drawing: concentric rings + a faint circle showing the true range
    # ------------------------------------------------------------------

    def attach(self, group):
        self._group = group
        self.redraw()

    def redraw(self):
        if self._group is None:
            return
        self._group.clear()
        r, g, b = self.color[:3]
        self._group.add(Color(r, g, b, 0.12))
        self._group.add(Line(circle=(self.x, self.y, C.GRAVITONIO_RANGE),
                             width=1))
        for ring_r, alpha in ((40, 0.30), (27, 0.50), (15, 0.80)):
            self._group.add(Color(r, g, b, alpha))
            self._group.add(Line(circle=(self.x, self.y, ring_r), width=1.6))
        self._group.add(Color(r, g, b, 1.0))
        self._group.add(Ellipse(pos=(self.x - 6, self.y - 6), size=(12, 12)))


# Registry for rebuilding any obstacle from its to_dict() form (Save/Load).
OBSTACLE_TYPES = {
    "rock": Rock,
    "perpetio": Perpetio,
    "mirror": Mirror,
    "elastonio": Elastonio,
    "wormhole": Wormhole,
    "gravitonio": Gravitonio,
}


def obstacle_from_dict(data):
    """Rebuild an obstacle of any kind from its serialized dictionary."""
    return OBSTACLE_TYPES[data["kind"]].from_dict(data)
