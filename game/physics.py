"""Geometry and physics helpers shared by the whole game.

The flight model is the one prescribed by the assignment: each simulation
step displaces the position by the instant velocity, then reduces the vertical
velocity component to simulate gravity (massive projectiles only).
Projectile.update() in projectiles.py implements it for real shots;
simulate_trajectory() repeats the same update equations for the aim preview.
It remains a separate fixed-step calculation and does not model every
collision or special obstacle interaction handled by the game screen.
"""

from game import constants as C


def point_segment_dist2(px, py, ax, ay, bx, by):
    """Squared distance between the point P and the segment A->B."""
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    ab_len2 = abx * abx + aby * aby
    if ab_len2 == 0:
        # Degenerate segment (A == B): plain point-to-point distance.
        t = 0.0
    else:
        # Where the projection of P falls along A->B, clamped to the ends.
        t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab_len2))
    qx, qy = ax + t * abx, ay + t * aby   # closest point of the segment to P
    dx, dy = px - qx, py - qy
    return dx * dx + dy * dy


def segment_circle_hit(ax, ay, bx, by, cx, cy, radius):
    """True if the segment A->B passes within `radius` of the point C.

    This helper checks the complete segment from the previous position to the
    new one instead of checking only the endpoint.
    """
    return point_segment_dist2(cx, cy, ax, ay, bx, by) <= radius * radius


def segment_intersection(ax, ay, bx, by, cx, cy, dx, dy):
    """Intersection point of the segments A->B and C->D.

    Returns (t, x, y) where t in [0, 1] is the fraction along A->B,
    or None if the segments do not cross. Standard 2D cross-product
    formulation: A + t*(B-A) == C + u*(D-C) with both t, u in [0, 1].
    """
    rx, ry = bx - ax, by - ay
    sx, sy = dx - cx, dy - cy
    denom = rx * sy - ry * sx
    if abs(denom) < 1e-12:
        return None   # parallel (or degenerate): no single crossing point
    qpx, qpy = cx - ax, cy - ay
    t = (qpx * sy - qpy * sx) / denom
    u = (qpx * ry - qpy * rx) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (t, ax + t * rx, ay + t * ry)
    return None


def reflect(vx, vy, nx, ny):
    """Reflect the vector v about a surface with unit normal n:
    v' = v - 2 (v·n) n. The speed (vector length) is preserved, and the
    sign of the normal does not matter; both sides give the same result.
    """
    dot = vx * nx + vy * ny
    return vx - 2.0 * dot * nx, vy - 2.0 * dot * ny


def simulate_trajectory(x, y, vx, vy, massive, duration, dt, samples,
                        accel_fn=None):
    """Sample points using the flight update equations.

    Returns a flat list [x0, y0, x1, y1, ...] with up to `samples` points,
    ready to be assigned to a kivy Point instruction. Used by the aim
    preview helper.

    `accel_fn(x, y) -> (ax, ay)` optionally adds external force fields
    (the Gravitonio anomalies) for massive projectiles. The caller supplies
    the preview duration and fixed time step. Obstacle interactions are not
    simulated by this helper.
    """
    steps = max(1, int(duration / dt))
    every = max(1, steps // samples)
    points = []
    for step in range(1, steps + 1):
        if massive and accel_fn is not None:
            ax, ay = accel_fn(x, y)
            vx += ax * dt
            vy += ay * dt
        x += vx * dt
        y += vy * dt
        if massive:
            vy -= C.GRAVITY * dt
        if step % every == 0 and len(points) < 2 * samples:
            points.extend((x, y))
    return points
