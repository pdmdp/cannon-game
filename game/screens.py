"""Non-game screens: main menu, Settings, Help and Hall of Fame, plus
shared decorative widgets like the starfield background.

Note on units: the whole game is designed in a fixed virtual space of
SCREEN_WIDTH x SCREEN_HEIGHT; main.py scales it to the real window. For
this reason font sizes are plain numbers (design units), not "sp" strings,
so they cannot be scaled twice on high-DPI displays.
"""

import math
import random

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import (Color, Ellipse, Line, Point, Rectangle,
                           RoundedRectangle)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.utils import escape_markup

from game import art
from game import constants as C
from game import storage
from game import story

FONT_DISPLAY = "GeistDisplay"
FONT_BODY = "GeistBody"
FONT_MONO = "GeistMono"

HALL_OF_FAME_SEEDS = (
    ("NOVA", 16), ("RAVEN", 18), ("KESTREL", 20), ("ECHO", 22),
    ("HELIX", 24), ("ORBIT", 27), ("LYRA", 30), ("VECTOR", 33),
    ("QUASAR", 36), ("PIXEL", 40), ("COMET", 44), ("AURORA", 48),
    ("ROOK", 53), ("CIRCUIT", 59), ("PULSE", 66), ("SABLE", 74),
    ("ATLAS", 83), ("VANTA", 93), ("BISHOP", 105), ("DRIFT", 120),
)


def safe_markup(value):
    """Escape user-controlled text before inserting it in Kivy markup."""
    return escape_markup(str(value))


def panel(x, y, width, height, radius=14):
    """A fixed design-space card shared by secondary screens."""
    holder = Widget(size_hint=(None, None), pos=(x, y), size=(width, height))
    with holder.canvas:
        Color(0.03, 0.05, 0.11, 0.90)
        RoundedRectangle(pos=(x, y), size=(width, height), radius=[radius])
        Color(0.55, 0.85, 1.0, 0.28)
        Line(rounded_rectangle=(x, y, width, height, radius), width=1.1)
    return holder


class StarField(Widget):
    """Background sky: three layers of randomly placed stars that gently
    twinkle (each layer's brightness oscillates slowly).

    The random generator uses a fixed seed, so the star positions repeat
    on every run. The background is decoration and does not affect gameplay.
    """

    # (star count, point size, base alpha): many dim small stars -> few bright ones.
    LAYERS = (
        (60, 1.2, 0.35),
        (25, 2.0, 0.60),
        (10, 3.0, 0.90),
    )
    TWINKLE_FPS = 24  # brightness updates per second (cheap: 3 values)

    def __init__(self, transparent=False, **kwargs):
        super().__init__(**kwargs)
        self._transparent = transparent   # skip the opaque backdrop rect
        self._layer_colors = []   # (Color instruction, base alpha) per layer
        self._twinkle_event = None
        self._phase = 0.0
        # Redraw whenever Kivy assigns us our position/size on screen.
        self.bind(size=self._redraw, pos=self._redraw)
        # Owners explicitly start the animation only while visible.  Hidden
        # screens used to schedule one 24 Hz callback each during boot.

    def _redraw(self, *_args):
        self.canvas.clear()
        self._layer_colors = []
        if self.width < 2 or self.height < 2:
            return  # not laid out yet
        rng = random.Random(2023)
        with self.canvas:
            # The deep-space background itself, so every screen is
            # self-contained and doesn't rely on the window clear color
            # (skipped when the screen provides its own art backdrop).
            if not self._transparent:
                Color(*C.COLOR_BACKGROUND)
                Rectangle(pos=self.pos, size=self.size)
            for count, pointsize, alpha in self.LAYERS:
                color = Color(C.COLOR_STAR[0], C.COLOR_STAR[1], C.COLOR_STAR[2], alpha)
                self._layer_colors.append((color, alpha))
                points = []
                for _ in range(count):
                    points.append(self.x + rng.random() * self.width)
                    points.append(self.y + rng.random() * self.height)
                Point(points=points, pointsize=pointsize)

    def start_twinkle(self):
        if self._twinkle_event is None:
            self._twinkle_event = Clock.schedule_interval(
                self._twinkle, 1.0 / self.TWINKLE_FPS)

    def stop_twinkle(self):
        if self._twinkle_event is not None:
            self._twinkle_event.cancel()
            self._twinkle_event = None

    def _twinkle(self, dt):
        # Each layer breathes with a different rhythm around its base alpha.
        self._phase += dt
        for i, (color, base_alpha) in enumerate(self._layer_colors):
            color.a = base_alpha + 0.12 * math.sin(2.0 * self._phase + 2.1 * i)


class MenuButton(Button):
    """A story-styled button: translucent rounded panel with a thin cyan
    border that brightens on press, matching the dialogue cards."""

    def __init__(self, **kwargs):
        super().__init__(
            background_normal="",
            background_down="",
            background_disabled_normal="",
            background_color=(0, 0, 0, 0),
            color=(0.88, 0.94, 1.0, 1.0),
            disabled_color=(1, 1, 1, 0.28),
            font_name=FONT_BODY,
            **kwargs)
        with self.canvas.before:
            self._bg = Color(0.10, 0.16, 0.30, 0.82)
            self._bg_rect = RoundedRectangle(radius=[10])
            self._border = Color(0.55, 0.85, 1.0, 0.22)
            self._border_line = Line(width=1.1)
        self.bind(pos=self._sync, size=self._sync,
                  state=self._sync, disabled=self._sync)
        self._sync()

    def _sync(self, *_args):
        x, y, w, h = self.x, self.y, self.width, self.height
        self._bg_rect.pos = (x, y)
        self._bg_rect.size = (w, h)
        self._border_line.rounded_rectangle = (x, y, max(w, 2), max(h, 2), 10)
        if self.disabled:
            self._bg.rgba = (1, 1, 1, 0.05)
            self._border.a = 0.08
        elif self.state == "down":
            self._bg.rgba = (0.22, 0.38, 0.62, 0.95)
            self._border.a = 0.60
        else:
            self._bg.rgba = (0.10, 0.16, 0.30, 0.82)
            self._border.a = 0.22


class PanelToggle(ToggleButton):
    """Rounded toggle matching the menu/dialogue visual system."""

    def __init__(self, **kwargs):
        super().__init__(background_normal="", background_down="",
                         background_color=(0, 0, 0, 0),
                         font_name=FONT_BODY, **kwargs)
        with self.canvas.before:
            self._panel_color = Color(0.10, 0.16, 0.30, 0.82)
            self._panel = RoundedRectangle(radius=[8])
            self._line_color = Color(0.55, 0.85, 1, 0.22)
            self._line = Line(width=1.0)
        self.bind(pos=self._sync_panel, size=self._sync_panel,
                  state=self._sync_panel)
        self._sync_panel()

    def _sync_panel(self, *_args):
        self._panel.pos, self._panel.size = self.pos, self.size
        self._line.rounded_rectangle = (*self.pos, max(2, self.width),
                                        max(2, self.height), 8)
        if self.state == "down":
            self._panel_color.rgba = (0.18, 0.38, 0.56, 0.95)
            self._line_color.rgba = (0.55, 0.85, 1, 0.72)
        else:
            self._panel_color.rgba = (0.10, 0.16, 0.30, 0.82)
            self._line_color.rgba = (0.55, 0.85, 1, 0.22)


def menu_button(text, on_press=None, enabled=True):
    """A uniformly styled menu button (with a click sound)."""
    btn = MenuButton(
        text=text,
        size_hint=(1, None),
        height=52,
        font_size=19,
        bold=True,
        disabled=not enabled,
    )

    def pressed(button):
        app = App.get_running_app()
        if getattr(app, "audio", None) is not None:
            app.audio.play("click")
        if on_press is not None:
            on_press(button)

    btn.bind(on_press=pressed)
    return btn


class MenuScreen(Screen):
    """Mission-control dashboard shown after the dedicated title screen."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # The outpost panel as a dimmed backdrop, when the art exists.
        backdrop = art.texture("intro_outpost")
        if backdrop is not None:
            image = Image(texture=backdrop, fit_mode="fill", size_hint=(1, 1))
            self.add_widget(image)
            dimmer = Widget(size_hint=(1, 1))
            with dimmer.canvas:
                # At 0.60 alpha even a white source pixel keeps the critical
                # objective text above WCAG 4.5:1 contrast.
                Color(0.02, 0.03, 0.06, 0.60)
                Rectangle(pos=(0, 0), size=(C.SCREEN_WIDTH, C.SCREEN_HEIGHT))
            self.add_widget(dimmer)
        self._stars = StarField(transparent=backdrop is not None)
        self.add_widget(self._stars)

        # A compact operations panel leaves the turret artwork readable.
        self.add_widget(panel(742, 58, 500, 604, radius=20))
        self.add_widget(Label(
            text="PV-1 MISSION CONTROL",
            font_name=FONT_MONO,
            font_size=17,
            bold=True,
            color=(0.62, 0.88, 1.00, 1.0),
            size_hint=(None, None),
            size=(444, 30), pos=(770, 608),
            halign="left", text_size=(444, 30),
        ))
        self.add_widget(Label(
            text="TEN SIGNALS. EIGHT DAYS.",
            font_name=FONT_DISPLAY,
            font_size=31,
            color=(1.0, 0.72, 0.34, 0.95),
            size_hint=(None, None),
            size=(444, 48), pos=(770, 548), halign="left",
            text_size=(444, 48),
        ))
        self.add_widget(Label(
            text=("Destroy all ten route beacons before the fleet "
                  "reaches the colonies."),
            font_name=FONT_BODY,
            font_size=18,
            color=(0.94, 0.97, 1.0, 0.92),
            halign="left",
            valign="middle",
            size_hint=(None, None),
            size=(444, 54), text_size=(444, 54), pos=(770, 490),
        ))
        self._welcome = Label(
            markup=True,
            text="",
            font_name=FONT_BODY,
            font_size=17,
            color=(0.62, 0.88, 1.0, 0.9),
            size_hint=(None, None),
            size=(444, 25), pos=(770, 454), halign="left",
            text_size=(444, 25),
        )
        self.add_widget(self._welcome)

        # Campaign state and ten-beacon rail.
        self._campaign_status = Label(
            text="", font_name=FONT_MONO, font_size=14,
            color=(0.71, 0.89, 1, 0.82), halign="left", valign="middle",
            size_hint=(None, None), size=(444, 26), text_size=(444, 26),
            pos=(770, 416))
        self.add_widget(self._campaign_status)
        rail_x, rail_y = 770, 370
        rail = Widget(size_hint=(None, None), size=(444, 34),
                      pos=(rail_x, rail_y))
        self._rail_colors = []
        with rail.canvas:
            for index in range(10):
                color = Color(1.0, 0.25, 0.20, 0.70)
                self._rail_colors.append(color)
                Ellipse(pos=(rail_x + index * 45 + 4, rail_y + 8),
                        size=(16, 16))
        self.add_widget(rail)

        self._primary = menu_button("NEW MISSION", on_press=self._play)
        self._primary.size_hint = (None, None)
        self._primary.size = (444, 62)
        self._primary.pos = (770, 286)
        self._primary.font_size = 21
        self.add_widget(self._primary)

        buttons = BoxLayout(orientation="vertical", spacing=8,
                            size_hint=(None, None), size=(444, 4 * 43 + 3 * 8),
                            pos=(770, 82))
        self._load_btn = menu_button("LOAD GAME", on_press=self._load)
        self._load_btn.height = 43
        buttons.add_widget(self._load_btn)
        for text, action in (
                ("SETTINGS", self._goto("settings")),
                ("HALL OF FAME", self._goto("hall_of_fame")),
                ("HELP", self._goto("help"))):
            button = menu_button(text, on_press=action)
            button.height = 43
            buttons.add_widget(button)
        self.add_widget(buttons)

        quit_button = menu_button("QUIT", on_press=self._quit)
        quit_button.size_hint = (None, None)
        quit_button.size = (94, 34)
        quit_button.pos = (620, 72)
        quit_button.font_size = 14
        self.add_widget(quit_button)
        self._new_run = menu_button("NEW RUN", on_press=self._restart)
        self._new_run.size_hint = (None, None)
        self._new_run.size = (128, 34)
        self._new_run.pos = (584, 112)
        self._new_run.font_size = 14
        self.add_widget(self._new_run)
        self._restart_armed = False
        self._music_prefetch_event = None

    def on_pre_enter(self, *_args):
        app = App.get_running_app()
        audio = getattr(app, "audio", None)
        title_overlay = getattr(app, "title_overlay", None)
        if (title_overlay is None or title_overlay.parent is None):
            if audio is not None:
                audio.set_music_scene("menu")
        self._stars.start_twinkle()
        name = app.settings.get("player_name", "GUNNER")
        self._welcome.text = ("COMMANDER  [b]"
                              f"{safe_markup(name.upper())}[/b]")
        game = self.manager.get_screen("game") if self.manager.has_screen("game") else None
        active = bool(game and getattr(game, "campaign_active", False))
        completed = 0 if game is None else min(10, getattr(game, "level_index", 0))
        if active:
            self._primary.text = "CONTINUE MISSION"
            self._campaign_status.text = (
                f"RUN ACTIVE  |  BEACON {completed + 1:02d}/10  |  "
                f"{getattr(game, 'shots_total', 0)} SHOTS")
        else:
            self._primary.text = "NEW MISSION"
            self._campaign_status.text = "NO ACTIVE RUN  |  ALL BEACONS ONLINE"
        self._restart_armed = False
        self._new_run.text = "NEW RUN"
        self._new_run.disabled = not active
        self._new_run.opacity = 1.0 if active else 0.0
        for index, color in enumerate(self._rail_colors):
            color.rgba = ((0.20, 0.72, 0.82, 0.34) if index < completed
                          else (1.0, 0.25, 0.20, 0.70))
        self._load_btn.disabled = not storage.has_save()
        if (title_overlay is None or title_overlay.parent is None) and \
                hasattr(audio, "preload_music_scene"):
            if active:
                level = getattr(game, "level_index", 0)
                phase = getattr(game, "phase", 0)
                if level == 9:
                    next_scene = f"foreman_p{max(1, min(3, phase + 1))}"
                elif level >= 6:
                    next_scene = "anomaly"
                elif level >= 4:
                    next_scene = "warden"
                else:
                    next_scene = "belt"
            else:
                next_scene = "belt"
            self._music_prefetch_event = Clock.schedule_once(
                lambda _dt: audio.preload_music_scene(next_scene), 0.25)

    def on_leave(self, *_args):
        if self._music_prefetch_event is not None:
            self._music_prefetch_event.cancel()
            self._music_prefetch_event = None
        self._stars.stop_twinkle()

    def _goto(self, screen_name):
        def switch(_button):
            self.manager.current = screen_name
        return switch

    def _play(self, _button):
        game = self.manager.get_screen("game")
        if not getattr(game, "campaign_active", False):
            if hasattr(game, "new_campaign"):
                game.new_campaign()
            else:
                game.shots_total = 0
                game.start_level(0)
            game.campaign_active = True
        self.manager.current = "game"

    def _load(self, _button):
        app = App.get_running_app()
        if hasattr(app, "open_save_slots"):
            app.open_save_slots("load", return_screen="menu")

    def _restart(self, _button):
        if not self._restart_armed:
            self._restart_armed = True
            self._new_run.text = "CONFIRM"
            self._campaign_status.text = "ABANDON THE ACTIVE RUN?"
            return
        game = self.manager.get_screen("game")
        game.start_campaign()
        self.manager.current = "game"

    def _quit(self, _button):
        App.get_running_app().stop()


class SubScreen(Screen):
    """Shared scaffold for menu sub-pages: starfield, a title, a BACK
    button, and ESC returning to the menu."""

    title_text = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._stars = StarField()
        self.add_widget(self._stars)
        self.add_widget(Label(
            text=self.title_text,
            font_name=FONT_DISPLAY,
            font_size=44,
            bold=True,
            color=(0.55, 0.85, 1.00, 1.0),
            size_hint=(None, None),
            size=(760, 60),
            pos_hint={"center_x": 0.5, "center_y": 0.92},
        ))
        back = menu_button("BACK", on_press=self._back)
        back.size_hint = (None, None)
        back.size = (220, 48)
        back.pos_hint = {"center_x": 0.5, "y": 0.035}
        self.add_widget(back)

    def on_pre_enter(self, *_args):
        app = App.get_running_app()
        if getattr(app, "audio", None) is not None:
            app.audio.set_music_scene(
                getattr(self, "_music_scene_override", "menu"))
        self._stars.start_twinkle()
        Window.bind(on_key_down=self._on_key_down)

    def on_leave(self, *_args):
        self._stars.stop_twinkle()
        Window.unbind(on_key_down=self._on_key_down)

    def _on_key_down(self, _window, key, *_rest):
        if key == 27:                     # ESC
            self._back(None)
            return True
        return False

    def _back(self, _button):
        self.manager.current = "menu"


class SettingsScreen(SubScreen):
    """Player name, difficulty, volumes and the aim-preview toggle.
    Changes update the live settings and are saved after a short debounce."""

    title_text = "SETTINGS"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self._persist_event = None
        self._syncing = False
        self.add_widget(panel(250, 126, 780, 448))

        rows = BoxLayout(
            orientation="vertical",
            spacing=10,
            size_hint=(None, None),
            size=(720, 7 * 50 + 6 * 10),
            pos_hint={"center_x": 0.5, "center_y": 0.50},
        )

        # Player name --------------------------------------------------
        self._name_input = TextInput(
            text="",
            multiline=False,
            write_tab=False,
            font_size=18,
            font_name=FONT_BODY,
            padding=(12, 14),
            background_color=(1, 1, 1, 0.08),
            foreground_color=(0.9, 0.95, 1, 1),
            cursor_color=(0.55, 0.85, 1, 1),
        )
        self._name_input.bind(text=self._on_name)
        rows.add_widget(self._row("Commander name", self._name_input))

        # Difficulty ---------------------------------------------------
        diff_box = BoxLayout(spacing=8)
        self._diff_buttons = {}
        for value, caption in (("easy", "EASY"), ("normal", "NORMAL"),
                               ("hard", "HARD")):
            btn = PanelToggle(
                text=caption,
                group="difficulty",
                allow_no_selection=False,
                font_size=16,
                color=(0.85, 0.93, 1, 1),
            )
            btn.bind(on_press=self._make_difficulty_setter(value))
            self._diff_buttons[value] = btn
            diff_box.add_widget(btn)
        rows.add_widget(self._row("Difficulty (shot budgets)", diff_box))

        # Volumes --------------------------------------------------------
        self._music_slider = Slider(min=0.0, max=1.0, step=0.05)
        self._music_value = Label(size_hint=(None, 1), width=54, font_size=15)
        self._music_value.font_name = FONT_MONO
        self._music_slider.bind(value=self._on_music)
        rows.add_widget(self._row("Music volume", self._volume_box(
            self._music_slider, self._music_value)))

        self._sfx_slider = Slider(min=0.0, max=1.0, step=0.05)
        self._sfx_value = Label(size_hint=(None, 1), width=54, font_size=15)
        self._sfx_value.font_name = FONT_MONO
        self._sfx_slider.bind(value=self._on_sfx)
        rows.add_widget(self._row("Effects volume", self._volume_box(
            self._sfx_slider, self._sfx_value)))

        # Aim preview ----------------------------------------------------
        self._preview_toggle = PanelToggle(
            font_size=16,
            color=(0.85, 0.93, 1, 1),
        )
        self._preview_toggle.bind(on_press=self._on_preview)
        rows.add_widget(self._row("Trajectory preview", self._preview_toggle))

        self._instant_toggle = PanelToggle(
            font_size=16, color=(0.85, 0.93, 1, 1))
        self._instant_toggle.bind(on_press=self._on_instant)
        rows.add_widget(self._row("Instant dialogue text", self._instant_toggle))

        self._motion_toggle = PanelToggle(
            font_size=16, color=(0.85, 0.93, 1, 1))
        self._motion_toggle.bind(on_press=self._on_motion)
        rows.add_widget(self._row("Reduced motion", self._motion_toggle))

        self.add_widget(rows)

    @staticmethod
    def _volume_box(slider, value_label):
        box = BoxLayout(spacing=8)
        box.add_widget(slider)
        box.add_widget(value_label)
        return box

    @staticmethod
    def _row(caption, control):
        row = BoxLayout(size_hint=(1, None), height=50, spacing=16)
        row.add_widget(Label(
            text=caption,
            halign="left",
            valign="middle",
            font_size=18,
            font_name=FONT_BODY,
            color=(1, 1, 1, 0.85),
            size_hint=(0.46, 1),
            text_size=(300, 50),
        ))
        control.size_hint = (0.54, 1)
        row.add_widget(control)
        return row

    def on_pre_enter(self, *args):
        super().on_pre_enter(*args)
        # Sync every control with the live settings (they may have
        # changed elsewhere since this screen was built).
        settings = self.app.settings
        self._syncing = True
        self._name_input.text = settings["player_name"]
        self._diff_buttons[settings["difficulty"]].state = "down"
        self._music_slider.value = settings["music_volume"]
        self._sfx_slider.value = settings["sfx_volume"]
        self._preview_toggle.state = "down" if settings["show_preview"] else "normal"
        self._preview_toggle.text = "ON" if settings["show_preview"] else "OFF"
        instant = settings.get("instant_text", False)
        self._instant_toggle.state = "down" if instant else "normal"
        self._instant_toggle.text = "ON" if instant else "OFF"
        reduced = settings.get("reduced_motion", False)
        self._motion_toggle.state = "down" if reduced else "normal"
        self._motion_toggle.text = "ON" if reduced else "OFF"
        self._syncing = False

    def on_leave(self, *args):
        self._flush_settings()
        super().on_leave(*args)

    def _persist(self):
        if self._syncing:
            return
        if self._persist_event is not None:
            self._persist_event.cancel()
        self._persist_event = Clock.schedule_once(
            lambda _dt: self._flush_settings(), 0.25)

    def _flush_settings(self):
        if self._persist_event is not None:
            self._persist_event.cancel()
            self._persist_event = None
        storage.save_settings(self.app.settings)

    def _on_name(self, _widget, text):
        clean = text[:14]
        if clean != text:
            self._name_input.text = clean   # re-triggers with the short text
            return
        self.app.settings["player_name"] = clean.strip() or "GUNNER"
        self._persist()

    def _make_difficulty_setter(self, value):
        def setter(_button):
            self.app.settings["difficulty"] = value
            self._persist()
        return setter

    def _on_music(self, _widget, value):
        self.app.settings["music_volume"] = round(value, 2)
        self._music_value.text = f"{round(value * 100):d}%"
        self._persist()
        if getattr(self.app, "audio", None) is not None:
            self.app.audio.apply_volumes()   # the music reacts immediately

    def _on_sfx(self, _widget, value):
        self.app.settings["sfx_volume"] = round(value, 2)
        self._sfx_value.text = f"{round(value * 100):d}%"
        self._persist()

    def _on_preview(self, _button):
        enabled = self._preview_toggle.state == "down"
        self.app.settings["show_preview"] = enabled
        self._preview_toggle.text = "ON" if enabled else "OFF"
        self._persist()

    def _on_instant(self, _button):
        enabled = self._instant_toggle.state == "down"
        self.app.settings["instant_text"] = enabled
        self._instant_toggle.text = "ON" if enabled else "OFF"
        self._persist()

    def _on_motion(self, _button):
        enabled = self._motion_toggle.state == "down"
        self.app.settings["reduced_motion"] = enabled
        self._motion_toggle.text = "ON" if enabled else "OFF"
        self._persist()


class HallOfFameScreen(SubScreen):
    """The best campaign runs: fewest total shots first (assignment)."""

    title_text = "HALL OF FAME"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_widget(panel(125, 126, 1030, 478))
        self._list_label = Label(
            markup=True,
            halign="left",
            valign="top",
            font_size=16,
            font_name=FONT_MONO,
            color=(0.9, 0.95, 1, 1),
            size_hint=(None, None),
            size=(960, 424),
            text_size=(960, 424),
            pos_hint={"center_x": 0.5, "center_y": 0.50},
        )
        self.add_widget(self._list_label)

    def on_pre_enter(self, *args):
        app = App.get_running_app()
        from_epilogue = bool(getattr(app, "_hall_from_epilogue", False))
        app._hall_from_epilogue = False
        self._music_scene_override = (
            "epilogue" if from_epilogue else "menu")
        super().on_pre_enter(*args)
        self._music_scene_override = "menu"
        real_entries = [dict(entry, _real=True)
                        for entry in storage.load_hall_of_fame()]
        seeds = [{"name": name, "shots": shots, "date": "", "_real": False}
                 for name, shots in HALL_OF_FAME_SEEDS]
        current = App.get_running_app().settings.get("player_name", "GUNNER")
        # Seed rows live only in code.  Exact real duplicates replace their
        # seed instead of creating an artificial second player.
        real_pairs = {(entry["name"].casefold(), entry["shots"])
                      for entry in real_entries}
        entries = real_entries + [entry for entry in seeds
                                  if (entry["name"].casefold(), entry["shots"])
                                  not in real_pairs]
        entries.sort(key=lambda entry: (
            entry["shots"],
            0 if entry["_real"] and entry["name"].casefold() == current.casefold() else 1,
            entry.get("date", "9999-99-99") or "9999-99-99",
            entry["name"].casefold()))
        entries = entries[:20]
        medals = ("#ffd166", "#c9d6e4", "#cd8b62")
        lines = ["[b]TOP OPERATORS  |  FEWEST SHOTS TO SAVE THE COLONIES[/b]", ""]
        for index in range(min(3, len(entries))):
            entry = entries[index]
            marker = "  [b]YOU[/b]" if entry["_real"] and entry["name"].casefold() == current.casefold() else ""
            lines.append(f"[color={medals[index]}]#{index + 1:<2}  "
                         f"{entry['shots']:>3} SHOTS   "
                         f"{safe_markup(entry['name'][:18]):<18}{marker}[/color]")
        lines += ["", "[color=#557799]RANK  SHOTS  COMMANDER                 RANK  SHOTS  COMMANDER[/color]"]

        def compact(rank):
            if rank >= len(entries):
                return ""
            entry = entries[rank]
            you = " YOU" if entry["_real"] and entry["name"].casefold() == current.casefold() else ""
            color = "#ffcf73" if you else "#dbeeff"
            return (f"[color={color}]#{rank + 1:<2}   {entry['shots']:>3}   "
                    f"{safe_markup(entry['name'][:15]):<15}{you:<4}[/color]")

        # Ranks 4-12 and 13-20 occupy two compact, aligned columns.
        for row in range(9):
            lines.append(f"{compact(3 + row):<64}{compact(12 + row)}")
        self._list_label.text = "\n".join(lines)


class SaveSlotScreen(SubScreen):
    """Three explicit save slots for loading, quick-save and Save As."""

    title_text = "MISSION ARCHIVE"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = "load"
        self.return_screen = "menu"
        self._confirm = None
        self._cards = []
        for index in range(3):
            x = 110 + index * 360
            self.add_widget(panel(x, 190, 340, 360, radius=16))
            heading = Label(text=f"SLOT {index + 1}", font_name=FONT_DISPLAY,
                            font_size=25, color=(0.62, 0.88, 1, 1),
                            size_hint=(None, None), size=(300, 40),
                            pos=(x + 20, 485))
            detail = Label(markup=True, text="", font_name=FONT_MONO,
                           font_size=15, color=(0.9, 0.95, 1, 0.9),
                           halign="left", valign="top", size_hint=(None, None),
                           size=(290, 205), text_size=(290, 205),
                           pos=(x + 25, 272))
            action = menu_button("LOAD", on_press=lambda _b, slot=index + 1:
                                 self._action(slot))
            action.size_hint = (None, None)
            action.size = (210, 46)
            action.pos = (x + 20, 210)
            delete = menu_button("DELETE", on_press=lambda _b, slot=index + 1:
                                 self._delete(slot))
            delete.size_hint = (None, None)
            delete.size = (90, 46)
            delete.pos = (x + 240, 210)
            delete.font_size = 13
            for widget in (heading, detail, action, delete):
                self.add_widget(widget)
            self._cards.append((detail, action, delete))
        self._notice = Label(text="", font_name=FONT_BODY, font_size=15,
                             color=(1, 0.77, 0.38, 1), size_hint=(None, None),
                             size=(900, 28), pos=(190, 148), halign="center")
        self.add_widget(self._notice)

    def configure(self, mode, return_screen="menu"):
        if mode not in ("load", "save"):
            raise ValueError("slot mode must be load or save")
        self.mode = mode
        self.return_screen = return_screen
        self._confirm = None
        self._notice.text = ("CHOOSE A SLOT TO SAVE THE CURRENT AIMING STATE"
                             if mode == "save" else
                             "CHOOSE A VALID MISSION SNAPSHOT")

    def on_pre_enter(self, *args):
        super().on_pre_enter(*args)
        self.refresh()

    def _back(self, _button):
        self.manager.current = self.return_screen

    def refresh(self):
        try:
            slots = storage.list_save_slots()
        except AttributeError:
            slots = [None, None, None]
        by_slot = {}
        if isinstance(slots, dict):
            by_slot = slots
        else:
            for position, value in enumerate(slots or [], 1):
                slot = value.get("slot", position) if isinstance(value, dict) else position
                by_slot[slot] = value
        for slot, (detail, action, delete) in enumerate(self._cards, 1):
            info = by_slot.get(slot)
            status = "empty" if info is None else str(info.get("status", "valid")).lower()
            snapshot = info.get("snapshot", {}) if isinstance(info, dict) else {}
            if isinstance(info, dict) and not snapshot:
                snapshot = info
            if status == "corrupt":
                detail.text = "[color=#ff6b61][b]CORRUPT[/b][/color]\n\nSnapshot cannot be loaded.\nDelete this slot to reuse it."
                action.disabled = True
                delete.disabled = False
            elif status in ("empty", "none"):
                detail.text = "[color=#6e8ba1][b]EMPTY SLOT[/b][/color]\n\nNo mission snapshot."
                action.disabled = self.mode == "load"
                delete.disabled = True
            else:
                level = int(snapshot.get("level_index", 0)) + 1
                phase = int(snapshot.get("phase", 0)) + 1
                difficulty = snapshot.get("campaign_difficulty",
                                          snapshot.get("difficulty", "normal"))
                player = info.get("player_name", "GUNNER")
                saved = info.get("saved_at", "")[:16].replace("T", " ")
                detail.text = (
                    "[color=#65d5ef][b]VALID[/b][/color]\n\n"
                    f"COMMANDER  {safe_markup(player)}\n"
                    f"LEVEL      {level:02d}/10\n"
                    f"PHASE      {phase}\n"
                    f"DIFFICULTY {safe_markup(str(difficulty).upper())}\n"
                    f"SHOTS      {snapshot.get('shots_total', 0)}\n"
                    f"SAVED      {safe_markup(saved)}")
                action.disabled = False
                delete.disabled = False
            action.text = "SAVE HERE" if self.mode == "save" else "LOAD MISSION"
            delete.text = "DELETE"

    def _action(self, slot):
        game = self.manager.get_screen("game")
        if self.mode == "load":
            data = storage.load_game(slot)
            if data is None:
                self._notice.text = "THIS SLOT CANNOT BE LOADED"
                self.refresh()
                return
            if game.restore(data) is False:
                self._notice.text = "SNAPSHOT REJECTED"
                return
            game.active_slot = slot
            game.campaign_active = True
            self.manager.current = "game"
            return

        occupied = False
        for info in storage.list_save_slots():
            if isinstance(info, dict) and info.get("slot") == slot:
                occupied = info.get("status", "valid") == "valid"
        if occupied and self._confirm != ("save", slot):
            self._confirm = ("save", slot)
            self._cards[slot - 1][1].text = "CONFIRM OVERWRITE"
            self._notice.text = f"SLOT {slot} ALREADY CONTAINS A MISSION"
            return
        if hasattr(game, "save_to_slot"):
            success = game.save_to_slot(slot)
        else:
            storage.save_game(game.snapshot(), slot,
                              App.get_running_app().settings.get("player_name", "GUNNER"))
            game.active_slot = slot
            success = True
        if success is not False:
            self.manager.current = "game"

    def _delete(self, slot):
        if self._confirm != ("delete", slot):
            self._confirm = ("delete", slot)
            self._cards[slot - 1][2].text = "CONFIRM"
            self._notice.text = f"DELETE SLOT {slot}? THIS CANNOT BE UNDONE."
            return
        storage.delete_save(slot)
        game = self.manager.get_screen("game")
        if getattr(game, "active_slot", None) == slot:
            game.active_slot = None
        self._confirm = None
        self._notice.text = f"SLOT {slot} DELETED"
        self.refresh()


class DialogueCard(Widget):
    """A story dialogue box: rounded portrait, speaker name, typewriter
    text. The owner calls run() with a list of (speaker, text) lines and
    advance() on SPACE/click: first completes the typing, then moves to
    the next line, then fires the on_done callback."""

    WIDTH, HEIGHT = 920, 168
    X, Y = (C.SCREEN_WIDTH - 920) / 2, 44
    CHARS_PER_SEC = 45.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active = False
        self._lines = []
        self._on_done = None
        self._on_abort = None
        self._full_text = ""
        self._shown = 0.0
        self._type_event = None

        x, y, w, h = self.X, self.Y, self.WIDTH, self.HEIGHT
        with self.canvas:
            self._bg_color = Color(0.03, 0.05, 0.11, 0.0)
            RoundedRectangle(pos=(x, y), size=(w, h), radius=[14])
            self._border_color = Color(0.55, 0.85, 1.0, 0.0)
            Line(rounded_rectangle=(x, y, w, h, 14), width=1.2)
            self._portrait_color = Color(1, 1, 1, 0.0)
            self._portrait = RoundedRectangle(
                pos=(x + 13, y + 13), size=(h - 26, h - 26), radius=[12])

        self._name_label = Label(
            text="", bold=True, font_size=17, font_name=FONT_BODY,
            halign="left", valign="middle",
            size_hint=(None, None), size=(400, 24), text_size=(400, 24),
            pos=(x + h, y + h - 38), opacity=0)
        self.add_widget(self._name_label)
        self._text_label = Label(
            text="", font_size=19, font_name=FONT_BODY,
            halign="left", valign="top", markup=True,
            color=(0.94, 0.96, 1.0, 1.0),
            size_hint=(None, None), size=(w - h - 34, h - 56),
            text_size=(w - h - 34, h - 56),
            pos=(x + h, y + 12), opacity=0)
        self.add_widget(self._text_label)
        self._hint_label = Label(
            text="SPACE: NEXT", font_size=14, font_name=FONT_MONO,
            color=(1, 1, 1, 0.58),
            halign="right", size_hint=(None, None), size=(120, 18),
            text_size=(120, 18), pos=(x + w - 134, y + 8), opacity=0)
        self.add_widget(self._hint_label)

    # ------------------------------------------------------------------

    def run(self, lines, player_name, on_done=None):
        """Play [(speaker, text), ...] with {name} already the player's."""
        self.cancel(invoke_callback=False)
        self._lines = [(speaker, story.fmt(text, safe_markup(player_name)))
                       for speaker, text in lines]
        self._on_done = on_done
        self.active = True
        audio = getattr(App.get_running_app(), "audio", None)
        if audio is not None and hasattr(audio, "set_duck"):
            audio.set_duck("dialogue", 0.58)
        self._set_visible(True)
        self._next_line()

    def advance(self):
        if not self.active:
            return
        if self._shown < len(self._full_text):
            self._shown = len(self._full_text)   # finish typing instantly
            self._text_label.text = self._full_text
        elif self._lines:
            self._next_line()
        else:
            self._finish()

    def _next_line(self):
        speaker, text = self._lines.pop(0)
        info = story.SPEAKERS.get(speaker, {})
        r, g, b = info.get("color", (1, 1, 1))
        self._name_label.text = speaker
        self._name_label.color = (r, g, b, 1)
        self._border_color.rgba = (r, g, b, 0.45)
        portrait = art.texture(info.get("portrait", ""))
        if portrait is not None:
            self._portrait.texture = portrait
            self._portrait_color.rgba = (1, 1, 1, 1)
        else:
            self._portrait_color.rgba = (r * 0.4, g * 0.4, b * 0.4, 1)
        self._full_text = text
        instant = App.get_running_app().settings.get("instant_text", False)
        self._shown = len(text) if instant else 0.0
        self._text_label.text = text if instant else ""
        if self._type_event is None:
            self._type_event = Clock.schedule_interval(self._type_tick,
                                                       1.0 / 30.0)

    def _type_tick(self, dt):
        if not self.active:
            return
        self._shown = min(self._shown + self.CHARS_PER_SEC * dt,
                          len(self._full_text))
        self._text_label.text = self._full_text[:int(self._shown)]

    def _finish(self):
        self.active = False
        self._set_visible(False)
        if self._type_event is not None:
            self._type_event.cancel()
            self._type_event = None
        audio = getattr(App.get_running_app(), "audio", None)
        if audio is not None and hasattr(audio, "clear_duck"):
            audio.clear_duck("dialogue")
        if self._on_done is not None:
            callback, self._on_done = self._on_done, None
            callback()

    def cancel(self, invoke_callback=False):
        """Stop the card and discard stale narrative callbacks by default."""
        callback, self._on_done = self._on_done, None
        self.active = False
        self._lines = []
        self._full_text = ""
        self._shown = 0.0
        if self._type_event is not None:
            self._type_event.cancel()
            self._type_event = None
        self._set_visible(False)
        audio = getattr(App.get_running_app(), "audio", None)
        if audio is not None and hasattr(audio, "clear_duck"):
            audio.clear_duck("dialogue")
        if invoke_callback and callback is not None:
            callback()

    def _set_visible(self, visible):
        alpha = 1.0 if visible else 0.0
        self._bg_color.a = 0.96 * alpha
        self._border_color.a = 0.45 * alpha
        self._portrait_color.a = self._portrait_color.a * 0 + alpha
        for label in (self._name_label, self._text_label, self._hint_label):
            label.opacity = alpha


class CinematicScreen(Screen):
    """Full-screen story panels: slow pan on each image, a dark text band
    with typewriter dialogue. SPACE/click advances; ESC skips it all."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0.01, 0.015, 0.04, 1)
            Rectangle(pos=(0, 0), size=(C.SCREEN_WIDTH, C.SCREEN_HEIGHT))
        # The panel image is slightly larger than the screen so it can
        # drift (the classic documentary pan) without showing edges.
        self._image = Image(fit_mode="fill",
                            size_hint=(None, None),
                            size=(C.SCREEN_WIDTH * 1.10, C.SCREEN_HEIGHT * 1.10))
        self.add_widget(self._image)

        band = Widget()
        with band.canvas:
            Color(0.01, 0.02, 0.05, 0.85)
            Rectangle(pos=(0, 0), size=(C.SCREEN_WIDTH, 150))
        self.add_widget(band)

        self._name_label = Label(
            text="", bold=True, font_size=17, font_name=FONT_BODY,
            halign="left",
            size_hint=(None, None), size=(600, 24), text_size=(600, 24),
            pos=(70, 112))
        self.add_widget(self._name_label)
        self._text_label = Label(
            text="", font_size=20, font_name=FONT_BODY,
            halign="left", valign="top",
            markup=True,
            color=(0.95, 0.97, 1.0, 1.0), size_hint=(None, None),
            size=(C.SCREEN_WIDTH - 140, 92),
            text_size=(C.SCREEN_WIDTH - 140, 92), pos=(70, 16))
        self.add_widget(self._text_label)
        self.add_widget(Label(
            text="SPACE: NEXT   |   ESC: SKIP", font_size=14,
            font_name=FONT_MONO, color=(1, 1, 1, 0.58),
            halign="right", size_hint=(None, None),
            size=(300, 18), text_size=(300, 18),
            pos=(C.SCREEN_WIDTH - 316, C.SCREEN_HEIGHT - 34)))

        self._panels = []
        self._lines = []
        self._player_name = ""
        self._on_done = None
        self._full_text = ""
        self._shown = 0.0
        self._type_event = None
        self._music_scene = "story"
        self._preload_scene = None
        self._music_prefetch_event = None

    def configure(self, panels, player_name, on_done, on_abort=None,
                  music_scene="story", preload_scene=None):
        """panels = [(image_name, [(speaker, text), ...]), ...]"""
        self.cancel(invoke_callback=False)
        self._panels = list(panels)
        self._player_name = player_name
        self._on_done = on_done
        self._on_abort = on_abort
        self._music_scene = music_scene
        self._preload_scene = preload_scene

    # ------------------------------------------------------------------

    def on_pre_enter(self, *_args):
        Window.bind(on_key_down=self._on_key_down)
        self._type_event = Clock.schedule_interval(self._type_tick, 1.0 / 30.0)
        audio = getattr(App.get_running_app(), "audio", None)
        if audio is not None:
            if hasattr(audio, "set_music_scene"):
                audio.set_music_scene(self._music_scene)
            if hasattr(audio, "set_duck"):
                # Story has no generated speech; retain musical emotion while
                # keeping the text band comfortable to read.
                audio.set_duck("cinematic", 0.78)
            if (self._preload_scene is not None and
                    hasattr(audio, "preload_music_scene")):
                self._music_prefetch_event = Clock.schedule_once(
                    lambda _dt: audio.preload_music_scene(self._preload_scene),
                    0.50)
        self._next_panel()

    def on_leave(self, *_args):
        Window.unbind(on_key_down=self._on_key_down)
        if self._type_event is not None:
            self._type_event.cancel()
            self._type_event = None
        if self._music_prefetch_event is not None:
            self._music_prefetch_event.cancel()
            self._music_prefetch_event = None
        Animation.cancel_all(self._image)
        audio = getattr(App.get_running_app(), "audio", None)
        if audio is not None and hasattr(audio, "clear_duck"):
            audio.clear_duck("cinematic")

    def _on_key_down(self, _window, key, *_rest):
        if key == 27:                                  # ESC: skip everything
            self._abort()
        elif key in (13, 32, 271):                     # ENTER/SPACE
            self.advance()
        return True

    def on_touch_down(self, _touch):
        self.advance()
        return True

    # ------------------------------------------------------------------

    def advance(self):
        if self._shown < len(self._full_text):
            self._shown = len(self._full_text)
            self._text_label.text = self._full_text
        elif self._lines:
            self._next_line()
        elif self._panels:
            self._next_panel()
        else:
            self._finish()

    def _next_panel(self):
        if not self._panels:
            self._finish()
            return
        image_name, lines = self._panels.pop(0)
        self._lines = list(lines)
        panel_tex = art.texture(image_name)
        self._image.texture = panel_tex
        self._image.opacity = 0
        if panel_tex is None:
            # No texture would render solid white: keep the panel dark
            # and let the text carry the moment.
            self._next_line()
            return
        # Slow drift: start slightly off-center, glide toward the other side.
        span_x = C.SCREEN_WIDTH * 0.10
        start = (-span_x if len(self._panels) % 2 else 0.0,
                 -C.SCREEN_HEIGHT * 0.05)
        end = (start[0] + (span_x if len(self._panels) % 2 else -span_x) * 0.6,
               start[1] + C.SCREEN_HEIGHT * 0.02)
        self._image.pos = start
        reduced = App.get_running_app().settings.get("reduced_motion", False)
        if reduced:
            self._image.opacity = 1.0
            self._image.pos = (0, -C.SCREEN_HEIGHT * 0.05)
        else:
            Animation(opacity=1.0, duration=0.5).start(self._image)
            Animation(x=end[0], y=end[1], duration=9.0).start(self._image)
        self._next_line()

    def _next_line(self):
        speaker, text = self._lines.pop(0)
        info = story.SPEAKERS.get(speaker, {})
        r, g, b = info.get("color", (1, 1, 1))
        self._name_label.text = speaker
        self._name_label.color = (r, g, b, 1)
        self._full_text = story.fmt(text, safe_markup(self._player_name))
        instant = App.get_running_app().settings.get("instant_text", False)
        self._shown = len(self._full_text) if instant else 0.0
        self._text_label.text = self._full_text if instant else ""

    def _type_tick(self, dt):
        self._shown = min(self._shown + 45.0 * dt, len(self._full_text))
        self._text_label.text = self._full_text[:int(self._shown)]

    def _finish(self):
        self._on_abort = None
        if self._on_done is not None:
            callback, self._on_done = self._on_done, None
            callback()

    def _abort(self):
        callback = self._on_abort if self._on_abort is not None else self._on_done
        self._on_abort = None
        self._on_done = None
        if callback is not None:
            callback()
        else:
            self.manager.current = "menu"

    def cancel(self, invoke_callback=False):
        callback, self._on_done = self._on_done, None
        self._on_abort = None
        self._panels = []
        self._lines = []
        self._full_text = ""
        self._shown = 0.0
        if self._type_event is not None:
            self._type_event.cancel()
            self._type_event = None
        Animation.cancel_all(self._image)
        if invoke_callback and callback is not None:
            callback()


def play_cinematic(manager, panels, player_name, on_done, on_abort=None,
                   music_scene="story", preload_scene=None):
    """Route the app through the cinematic screen, then call on_done."""
    screen = manager.get_screen("cinematic")
    screen.configure(panels, player_name, on_done, on_abort=on_abort,
                     music_scene=music_scene, preload_scene=preload_scene)
    manager.current = "cinematic"


class EnlistmentScreen(Screen):
    """First-launch screen: Vega asks for the player's name; confirming
    saves it and rolls the intro cinematic."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._stars = StarField()
        self.add_widget(self._stars)

        portrait = art.texture("portrait_gunner")
        if portrait is not None:
            holder = Widget()
            with holder.canvas:
                Color(1, 1, 1, 1)
                RoundedRectangle(
                    pos=(C.SCREEN_WIDTH / 2 - 110, 430), size=(220, 220),
                    radius=[18], texture=portrait)
                Color(0.55, 0.85, 1.0, 0.5)
                Line(rounded_rectangle=(C.SCREEN_WIDTH / 2 - 110, 430,
                                        220, 220, 18), width=1.2)
            self.add_widget(holder)

        self.add_widget(Label(
            text=("[b]VEGA[/b]: PV-1 enlistment terminal.\n"
                  "One cannon. Eight days. Tell me your name."),
            markup=True, halign="center", font_size=20,
            font_name=FONT_BODY,
            color=(0.9, 0.95, 1, 1), size_hint=(None, None),
            size=(760, 70), text_size=(760, 70),
            pos_hint={"center_x": 0.5, "center_y": 0.50}))

        self._name_input = TextInput(
            text="", hint_text="YOUR NAME", multiline=False, write_tab=False,
            font_size=22, font_name=FONT_BODY, padding=(14, 16), halign="center",
            background_color=(1, 1, 1, 0.08),
            foreground_color=(0.9, 0.95, 1, 1),
            hint_text_color=(1, 1, 1, 0.3),
            cursor_color=(0.55, 0.85, 1, 1),
            size_hint=(None, None), size=(360, 58),
            pos_hint={"center_x": 0.5, "center_y": 0.38})
        self._name_input.bind(on_text_validate=lambda *_: self._confirm())
        self.add_widget(self._name_input)

        confirm = menu_button("REPORT FOR DUTY", on_press=lambda *_: self._confirm())
        confirm.size_hint = (None, None)
        confirm.size = (360, 52)
        confirm.pos_hint = {"center_x": 0.5, "center_y": 0.28}
        self.add_widget(confirm)

    def on_pre_enter(self, *_args):
        self._stars.start_twinkle()
        app = App.get_running_app()
        if getattr(app, "audio", None) is not None:
            app.audio.set_music_scene("story")
        current = app.settings.get("player_name", "")
        self._name_input.text = (current
                                 if current and current != "GUNNER" else "")

    def on_leave(self, *_args):
        self._stars.stop_twinkle()

    def _confirm(self):
        app = App.get_running_app()
        name = self._name_input.text.strip()[:14] or "GUNNER"
        app.settings["player_name"] = name
        app.settings["profile_created"] = True
        app.settings["intro_seen"] = False
        storage.save_settings(app.settings)
        app.start_intro(first_run=True)


class HelpScreen(SubScreen):
    """How to play (assignment requirement): story, controls, rules."""

    title_text = "HELP"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._reset_armed = False
        self._reset_event = None
        self.add_widget(panel(90, 135, 1100, 455))
        text = (
            "[b]THE MISSION[/b]\n"
            "Destroy all ten route beacons before the fleet reaches the colonies. "
            "Rounds end when a "
            "projectile hits the beacon.\nEach level declares its plasma budget; "
            "run dry and you retry. [i]Every shot ever fired counts.[/i]\n"
            "Finish the campaign in the fewest total shots to enter the Hall of Fame.\n\n"
            "[b]CONTROLS[/b]\n"
            "mouse: aim the turret      scroll / up-down: muzzle velocity\n"
            "left/right: fine-tune the angle      SPACE or click: fire\n"
            "1 / 2 / 3: choose weapon      S / L: save / load      ESC: menu\n\n"
            "[b]WEAPONS[/b]\n"
            f"[color=#{'ffd966'}]BULLET[/color]: fast, arcs under gravity, "
            "blasts a small crater\n"
            f"[color=#{'ff7340'}]BOMBSHELL[/color]: heavy and slower, drills "
            "into rock before a big blast\n"
            f"[color=#{'4dff99'}]LASER[/color]: massless impulse at fixed "
            "speed: flies straight, carves a thin channel, bounces off mirrors\n\n"
            "[b]THE DEBRIS FIELD[/b]\n"
            "[color=#9e8f88]rock[/color] crumbles · "
            "[color=#5a6474]perpetio[/color] is indestructible · "
            "[color=#b3e6ff]mirrors[/color] reflect lasers · "
            "[color=#ff8cd9]elastonio[/color] bounces shells ·\n"
            "[color=#b366ff]wormholes[/color] teleport whatever enters · "
            "[color=#598cff]gravity anomalies[/color] bend massive shots "
            "(blue pulls, orange pushes)"
        )
        self.add_widget(Label(
            markup=True,
            text=text,
            halign="center",
            valign="top",
            font_size=16,
            font_name=FONT_BODY,
            color=(0.92, 0.95, 1, 0.95),
            size_hint=(None, None),
            size=(1040, 420),
            text_size=(1040, 420),
            pos_hint={"center_x": 0.5, "center_y": 0.50},
        ))
        rewatch = menu_button("REWATCH INTRO", on_press=self._rewatch)
        rewatch.size_hint = (None, None)
        rewatch.size = (220, 44)
        rewatch.pos_hint = {"center_x": 0.36, "y": 0.115}
        self.add_widget(rewatch)

        self._reset_button = menu_button(
            "RESET COMMANDER & STORY", on_press=self._reset_onboarding)
        self._reset_button.size_hint = (None, None)
        self._reset_button.size = (300, 44)
        self._reset_button.pos_hint = {"center_x": 0.64, "y": 0.115}
        self.add_widget(self._reset_button)

    def on_leave(self, *args):
        self._cancel_reset()
        super().on_leave(*args)

    def _rewatch(self, _button):
        app = App.get_running_app()
        play_cinematic(self.manager, story.INTRO,
                       app.settings.get("player_name", "GUNNER"),
                       lambda: setattr(self.manager, "current", "help"),
                       preload_scene="menu")

    def _reset_onboarding(self, _button):
        if not self._reset_armed:
            self._reset_armed = True
            self._reset_button.text = "CONFIRM RESET"
            self._reset_event = Clock.schedule_once(
                lambda _dt: self._cancel_reset(), 4.0)
            return

        app = App.get_running_app()
        self._cancel_reset()
        storage.reset_profile(app.settings)

        # Restore the first-run route without deleting save slots or Hall of
        # Fame entries. Detach any unsaved in-memory run from the old profile.
        if self.manager.has_screen("game"):
            game = self.manager.get_screen("game")
            game.campaign_active = False
            game.active_slot = None
        enlistment = self.manager.get_screen("enlistment")
        enlistment._name_input.text = ""
        self.manager.current = "enlistment"

    def _cancel_reset(self):
        if self._reset_event is not None:
            self._reset_event.cancel()
            self._reset_event = None
        self._reset_armed = False
        if hasattr(self, "_reset_button"):
            self._reset_button.text = "RESET COMMANDER & STORY"
