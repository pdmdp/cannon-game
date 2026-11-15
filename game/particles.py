"""Fixed-size particle renderer; canvas instructions are allocated once."""

from kivy.graphics import Color, Rectangle

from game import art
from game import constants as C

_FX_TEXTURES = {"spark": "fx_spark", "smoke": "fx_smoke",
                "flash": "fx_flash"}


class ParticleRenderer:
    def __init__(self, group, capacity=C.PARTICLE_CAP):
        self.slots = []
        self.textures = {kind: art.keyed_texture(name)
                         for kind, name in _FX_TEXTURES.items()}
        for _ in range(capacity):
            color = Color(1, 1, 1, 0)
            rect = Rectangle(pos=(-100, -100), size=(0, 0))
            group.add(color)
            group.add(rect)
            self.slots.append((color, rect))

    def draw(self, particles):
        for index, (color, rect) in enumerate(self.slots):
            if index >= len(particles):
                color.a = 0
                rect.pos = (-100, -100)
                rect.size = (0, 0)
                continue
            particle = particles[index]
            fade = 1.0 - particle["age"] / particle["ttl"]
            if particle["kind"] == "smoke":
                fade *= 0.55
            color.rgba = (*particle["rgb"], fade)
            texture = self.textures.get(particle["kind"])
            rect.texture = texture
            size = particle["size"] if texture is not None else C.PARTICLE_SIZE
            rect.pos = (particle["x"] - size / 2,
                        particle["y"] - size / 2)
            rect.size = (size, size)
