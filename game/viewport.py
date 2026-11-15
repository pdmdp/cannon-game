"""Fixed 16:9 design viewport with letterboxing and inverse input mapping."""

from kivy.core.window import Window
from kivy.graphics.transformation import Matrix
from kivy.uix.scatterlayout import ScatterPlane

from game import constants as C


def viewport_metrics(width, height):
    """Return ``(scale, x_offset, y_offset)`` for a centered 1280x720 view."""
    scale = min(float(width) / C.SCREEN_WIDTH,
                float(height) / C.SCREEN_HEIGHT)
    return (scale,
            (float(width) - C.SCREEN_WIDTH * scale) / 2.0,
            (float(height) - C.SCREEN_HEIGHT * scale) / 2.0)


def window_to_design(x, y, width, height):
    scale, offset_x, offset_y = viewport_metrics(width, height)
    return ((x - offset_x) / scale, (y - offset_y) / scale)


class DesignViewport(ScatterPlane):
    """Scatter used only as a deterministic design-space transform."""

    def __init__(self, **kwargs):
        super().__init__(do_translation=False, do_rotation=False,
                         do_scale=False, **kwargs)
        Window.bind(size=self.update_viewport)
        self.update_viewport(Window, Window.size)

    def update_viewport(self, _window, size):
        scale, offset_x, offset_y = viewport_metrics(*size)
        self.transform = Matrix().translate(offset_x, offset_y, 0).scale(
            scale, scale, 1)

    def to_design(self, x, y):
        return window_to_design(x, y, Window.width, Window.height)

    def dispose(self):
        Window.unbind(size=self.update_viewport)
