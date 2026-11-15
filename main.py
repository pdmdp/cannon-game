"""Cannon: Eight Days Left exam project entry point.

Run the game with:
    python3 main.py
"""

import os

from kivy.config import Config

from game import constants as C

# Window options must be configured before any other Kivy module creates
# the window, which is why these lines come before the remaining imports.
Config.set("graphics", "width", str(C.SCREEN_WIDTH))
Config.set("graphics", "height", str(C.SCREEN_HEIGHT))
Config.set("graphics", "resizable", "1")
Config.set("kivy", "exit_on_escape", "0")  # ESC goes back to the menu instead

from kivy.core.text import LabelBase


def _register_fonts():
    """Register explicit display, body and telemetry families.

    Kivy keeps its own default font untouched. Each UI component chooses
    the alias that matches its job; the pixel face is reserved for titles.
    """
    root = os.path.dirname(os.path.abspath(__file__))
    pixel = os.path.join(
        root, "assets", "Geist_Pixel",
        "GeistPixel-Regular-VariableFont_ELSH.ttf")
    geist = os.path.join(root, "assets", "Geist")
    body = os.path.join(geist, "Geist-Regular.ttf")
    body_bold = os.path.join(geist, "Geist-SemiBold.ttf")
    mono = os.path.join(geist, "GeistMono-Regular.ttf")
    mono_bold = os.path.join(geist, "GeistMono-SemiBold.ttf")

    if os.path.exists(pixel):
        LabelBase.register(name="GeistDisplay", fn_regular=pixel,
                           fn_bold=pixel)
    if os.path.exists(body):
        LabelBase.register(name="GeistBody", fn_regular=body,
                           fn_bold=body_bold if os.path.exists(body_bold) else body)
    if os.path.exists(mono):
        LabelBase.register(name="GeistMono", fn_regular=mono,
                           fn_bold=mono_bold if os.path.exists(mono_bold) else mono)


_register_fonts()

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from game import storage
from game import art
from game.audio import AudioManager
from game.game_screen import GameScreen
from game.screens import (CinematicScreen, EnlistmentScreen, HallOfFameScreen,
                          HelpScreen, MenuScreen, SaveSlotScreen,
                          SettingsScreen, play_cinematic)
from game.title import TitleLoadingOverlay
from game.viewport import DesignViewport

Window.clearcolor = C.COLOR_BACKGROUND


class CannonApp(App):
    """The Kivy application. build() returns the root widget of the window."""

    title = "Cannon: Eight Days Left"

    def build(self):
        # Runtime state belongs to Kivy's per-user application directory.
        # Legacy JSON files beside main.py are intentionally left untouched.
        if hasattr(storage, "configure"):
            storage.configure(self.user_data_dir)
        self.settings = storage.load_settings()
        self.audio = AudioManager(self.settings)

        self.manager = ScreenManager(transition=FadeTransition(duration=0.15))
        manager = self.manager
        manager.size_hint = (None, None)
        manager.size = (C.SCREEN_WIDTH, C.SCREEN_HEIGHT)

        self.stage = FloatLayout(size_hint=(None, None),
                                 size=(C.SCREEN_WIDTH, C.SCREEN_HEIGHT))
        self.stage.add_widget(manager)
        self.title_overlay = TitleLoadingOverlay(on_accept=self._leave_title)
        self.stage.add_widget(self.title_overlay)

        root = DesignViewport()
        self.viewport = root
        root.add_widget(self.stage)
        return root

    def on_start(self):
        # The first frame is now the title itself.  Expensive construction is
        # advanced cooperatively on later Kivy ticks.
        self.title_overlay.activate()
        self._boot_iterator = self._boot_steps()
        self._boot_completed = 0
        self._boot_total = 38
        Clock.schedule_once(self._advance_boot, 0)

    def _boot_steps(self):
        self.title_overlay.load_backdrop()
        yield "TITLE LINK ESTABLISHED"

        if hasattr(self.audio, "load_title_music"):
            self.audio.load_title_music()
            self.audio.set_music_scene("title")
            self.audio.start_music()
        else:
            self.audio.start_music()
        yield "AUDIO CHANNEL OPEN"

        # Runtime images are already preprocessed. Decode one texture per
        # scheduled boot step so the title and its music remain responsive.
        if os.path.isdir(art.RUNTIME_DIR):
            for filename in sorted(os.listdir(art.RUNTIME_DIR)):
                if filename.lower().endswith(".png"):
                    art.texture(os.path.splitext(filename)[0])
                    yield "PRELOADING VISUAL SYSTEMS"

        for screen_class, screen_name in (
                (MenuScreen, "menu"),
                (SettingsScreen, "settings"),
                (HallOfFameScreen, "hall_of_fame"),
                (HelpScreen, "help"),
                (SaveSlotScreen, "save_slots"),
                (CinematicScreen, "cinematic"),
                (EnlistmentScreen, "enlistment")):
            screen = screen_class(name=screen_name)
            self.manager.add_widget(screen)
            yield f"ONLINE: {screen.name.replace('_', ' ').upper()}"

        if hasattr(self.audio, "preload_effects_iter"):
            for sound_name in self.audio.preload_effects_iter():
                yield f"AUDIO: {str(sound_name).replace('_', ' ').upper()}"

        game = GameScreen(name="game")
        self.manager.add_widget(game)
        self.game = game
        yield "SIMULATION CORE ONLINE"

        # Force first-use textures and HUD geometry while still obscured.
        game._update(0.0)
        self.manager.current = "menu"
        if hasattr(self.audio, "set_music_scene"):
            self.audio.set_music_scene("title")
        yield "MISSION DATA VERIFIED"

        if hasattr(self.audio, "preload_music_scene"):
            route_scene = ("story" if
                           (not self.settings.get("profile_created", False) or
                            not self.settings.get("intro_seen", False))
                           else "menu")
            self.audio.preload_music_scene(route_scene)
            yield "NEXT AUDIO SCENE READY"

    def _advance_boot(self, _dt):
        try:
            status = next(self._boot_iterator)
        except StopIteration:
            self.title_overlay.set_progress(1, 1, "SYSTEMS READY")
            self.title_overlay.mark_boot_complete()
            return
        self._boot_completed += 1
        # The total depends on the available preprocessed assets. Expand the
        # denominator when needed so progress does not move backwards.
        self._boot_total = max(self._boot_total, self._boot_completed + 2)
        self.title_overlay.set_progress(self._boot_completed,
                                        self._boot_total, status)
        Clock.schedule_once(self._advance_boot, 0)

    def _leave_title(self):
        if self.title_overlay.parent is self.stage:
            self.stage.remove_widget(self.title_overlay)
        if not self.settings.get("profile_created", False):
            self.audio.set_music_scene("story")
            self.manager.current = "enlistment"
        elif not self.settings.get("intro_seen", False):
            self.audio.set_music_scene("story")
            self.start_intro(first_run=True)
        else:
            self.audio.set_music_scene("menu")
            self.manager.current = "menu"

    def start_intro(self, first_run=False):
        def complete():
            if first_run:
                self.settings["intro_seen"] = True
                storage.save_settings(self.settings)
            self.manager.current = "menu"
        play_cinematic(self.manager, __import__("game.story", fromlist=["INTRO"]).INTRO,
                       self.settings.get("player_name", "GUNNER"), complete,
                       on_abort=lambda: setattr(self.manager, "current", "menu"),
                       preload_scene="menu")

    def open_save_slots(self, mode, return_screen=None):
        if not self.manager.has_screen("save_slots"):
            return
        if return_screen is None:
            return_screen = self.manager.current
        screen = self.manager.get_screen("save_slots")
        screen.configure(mode, return_screen=return_screen)
        self.manager.current = "save_slots"

    def on_stop(self):
        self.audio.stop_music()
        settings_screen = (self.manager.get_screen("settings")
                           if self.manager.has_screen("settings") else None)
        if settings_screen is not None:
            settings_screen._flush_settings()
        if hasattr(self, "viewport"):
            self.viewport.dispose()


if __name__ == "__main__":
    CannonApp().run()
