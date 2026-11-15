"""Immediate, non-blocking title/loading overlay.

The overlay is deliberately independent from the rest of the screen module:
``CannonApp.build`` can draw it before constructing the expensive gameplay
screen.  All Kivy texture work remains on the UI thread and is split across
Clock ticks by the app boot iterator.
"""

import math
import random
import time

from kivy.animation import Animation
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle, RoundedRectangle
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from game import art
from game import constants as C


class TitleLoadingOverlay(Widget):
    """Opaque title shown on every boot until loading and user consent."""

    MIN_VISIBLE_SECONDS = 1.2

    def __init__(self, on_accept, **kwargs):
        super().__init__(size_hint=(None, None),
                         size=(C.SCREEN_WIDTH, C.SCREEN_HEIGHT), **kwargs)
        self._on_accept = on_accept
        self._started = time.perf_counter()
        self._boot_complete = False
        self._ready = False
        self._accepted = False
        self._held_keys = set()
        self._progress_colors = []
        self._mouse_x = C.SCREEN_WIDTH / 2
        self._mouse_y = C.SCREEN_HEIGHT / 2

        with self.canvas.before:
            Color(0.008, 0.018, 0.045, 1)
            self._background = Rectangle(pos=(0, 0), size=self.size)
            rng = random.Random(8021)
            for depth, count in ((0, 80), (1, 38), (2, 16)):
                alpha = (0.25, 0.48, 0.82)[depth]
                radius = (1.0, 1.5, 2.2)[depth]
                Color(0.60, 0.84, 1.0, alpha)
                for _ in range(count):
                    Ellipse(pos=(rng.randrange(C.SCREEN_WIDTH),
                                 rng.randrange(C.SCREEN_HEIGHT)),
                            size=(radius, radius))

        self._art = Image(opacity=0, fit_mode="fill",
                          size_hint=(None, None),
                          size=(C.SCREEN_WIDTH + 12, C.SCREEN_HEIGHT + 8),
                          pos=(-6, -4))
        self.add_widget(self._art)

        dim = Widget(size_hint=(None, None), size=self.size)
        with dim.canvas:
            Color(0.01, 0.02, 0.055, 0.56)
            Rectangle(pos=(0, 0), size=self.size)
            Color(0.06, 0.20, 0.32, 0.22)
            RoundedRectangle(pos=(250, 152), size=(780, 410), radius=[28])
        self.add_widget(dim)

        self.add_widget(Label(
            text="CANNON", font_name="GeistDisplay", font_size=94,
            bold=True, color=(0.70, 0.91, 1.0, 1),
            size_hint=(None, None), size=(900, 120),
            pos=(190, 392), halign="center", valign="middle"))
        self.add_widget(Label(
            text="EIGHT DAYS LEFT", font_name="GeistBody", font_size=28,
            bold=True, color=(1.0, 0.67, 0.28, 1),
            size_hint=(None, None), size=(900, 42), pos=(190, 350),
            halign="center", valign="middle"))
        self.add_widget(Label(
            text="Destroy all ten route beacons before the fleet reaches the colonies.",
            font_name="GeistBody", font_size=17,
            color=(0.91, 0.96, 1.0, 0.88), size_hint=(None, None),
            size=(900, 36), pos=(190, 301), halign="center", valign="middle"))

        rail_x, rail_y = 345, 242
        rail = Widget(size_hint=(None, None), size=(590, 24),
                      pos=(rail_x, rail_y))
        with rail.canvas:
            for index in range(10):
                color = Color(0.20, 0.43, 0.58, 0.35)
                self._progress_colors.append(color)
                RoundedRectangle(pos=(rail_x + index * 61, rail_y + 4),
                                 size=(48, 10), radius=[5])
        self.add_widget(rail)

        self._status = Label(
            text="LOADING SYSTEMS", font_name="GeistMono", font_size=15,
            color=(0.64, 0.86, 1.0, 0.78), size_hint=(None, None),
            size=(900, 28), pos=(190, 194), halign="center", valign="middle")
        self.add_widget(self._status)
        self._prompt = Label(
            text="", font_name="GeistMono", font_size=18, bold=True,
            color=(1.0, 0.78, 0.39, 1), size_hint=(None, None),
            size=(900, 34), pos=(190, 160), halign="center", valign="middle")
        self.add_widget(self._prompt)

    def activate(self):
        Window.bind(on_key_down=self._on_key_down,
                    on_key_up=self._on_key_up,
                    mouse_pos=self._on_mouse_pos)

    def load_backdrop(self):
        """Decode the title art after the first frame, then fade it in."""
        texture = art.texture("intro_outpost")
        if texture is not None:
            self._art.texture = texture
            Animation(opacity=1, duration=0.45).start(self._art)

    def set_progress(self, completed, total, status):
        ratio = 0 if total <= 0 else max(0.0, min(1.0, completed / total))
        lit = int(math.ceil(ratio * len(self._progress_colors)))
        for index, color in enumerate(self._progress_colors):
            if index < lit:
                color.rgba = (0.26, 0.82, 1.0, 0.92)
            else:
                color.rgba = (0.20, 0.43, 0.58, 0.35)
        self._status.text = status.upper()

    def mark_boot_complete(self):
        self._boot_complete = True
        remaining = self.MIN_VISIBLE_SECONDS - (time.perf_counter() - self._started)
        if remaining <= 0:
            self.mark_ready()
        else:
            from kivy.clock import Clock
            Clock.schedule_once(lambda _dt: self.mark_ready(), remaining)

    def mark_ready(self):
        if not self._boot_complete or self._accepted:
            return
        self._ready = True
        self.set_progress(1, 1, "SYSTEMS READY")
        self._prompt.text = "PRESS SPACE TO BEGIN"
        Animation.cancel_all(self._prompt)
        pulse = (Animation(opacity=0.48, duration=0.65)
                 + Animation(opacity=1.0, duration=0.65))
        pulse.repeat = True
        pulse.start(self._prompt)

    def _on_mouse_pos(self, _window, pos):
        if not self._ready:
            return
        viewport = getattr(getattr(self, "parent", None), "parent", None)
        if viewport is not None and hasattr(viewport, "to_design"):
            x, y = viewport.to_design(*pos)
        else:
            x, y = pos
        self._mouse_x, self._mouse_y = x, y
        app = __import__("kivy.app", fromlist=["App"]).App.get_running_app()
        reduced = getattr(app, "settings", {}).get("reduced_motion", False)
        if reduced:
            return
        dx = max(-6, min(6, (x - C.SCREEN_WIDTH / 2) / 105))
        dy = max(-4, min(4, (y - C.SCREEN_HEIGHT / 2) / 130))
        self._art.pos = (-6 + dx, -4 + dy)

    def _on_key_down(self, _window, key, *_rest):
        if key in self._held_keys:
            return True
        self._held_keys.add(key)
        if key in (13, 32, 271) and self._ready:
            self.accept()
        return True

    def _on_key_up(self, _window, key, *_rest):
        self._held_keys.discard(key)
        return True

    def on_touch_down(self, touch):
        if self._ready and not getattr(touch, "is_mouse_scrolling", False):
            self.accept()
        return True

    def accept(self):
        if not self._ready or self._accepted:
            return
        self._accepted = True
        Window.unbind(on_key_down=self._on_key_down,
                      on_key_up=self._on_key_up,
                      mouse_pos=self._on_mouse_pos)
        Animation.cancel_all(self._prompt)
        self._on_accept()
