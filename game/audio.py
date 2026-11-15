"""Lazy sound effects and scene-based adaptive music.

Audio is optional presentation: missing files, unsupported codecs and absent
devices are handled without interrupting the game. Runtime MP3 tracks live in
``assets/soundtrack/runtime``; the procedural WAV remains the fallback for every
scene.  At most the current track, a crossfade partner and one prefetched track
are decoded, which prevents the full score from occupying hundreds of MiB.
"""

import math
import os

from kivy.clock import Clock
from kivy.core.audio import SoundLoader


SOUND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "sounds")
SOUNDTRACK_RUNTIME_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "soundtrack", "runtime")

EFFECTS = (
    "fire_bullet", "fire_bomb", "fire_laser",
    "zap_hit", "explosion_small", "explosion_big",
    "reflect", "teleport", "beacon_down", "fail", "click",
    "victory_sting", "warning_pulse",
)
MUSIC = "music_loop"
MUSIC_SCENES = {
    "title": "music_title",
    "menu": "music_menu",
    "story": "music_story",
    "belt": "music_belt",
    "warden": "music_warden",
    "anomaly": "music_anomaly",
    "foreman_p1": "music_foreman_p1",
    "foreman_p2": "music_foreman_p2",
    "foreman_p3": "music_foreman_p3",
    "epilogue": "music_epilogue",
}
SCENE_ALIASES = {"foreman": "foreman_p1"}
CROSSFADE_SECONDS = 2.0
EFFECT_DUCK = {"victory_sting": 0.45, "warning_pulse": 0.45}


def _clamp(value, low=0.0, high=1.0):
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return low


class AudioManager:
    """Lazy, failure-tolerant audio controller.

    ``start_music()``, ``stop_music()`` and ``apply_volumes()`` keep the old
    interface intact. New boot code can load one small piece at a time through
    ``load_title_music()`` and ``preload_effects_iter()``.
    """

    def __init__(self, settings, loader=SoundLoader, clock=Clock):
        self.settings = settings
        self.sounds = {}
        self.music = None
        self.music_scene = None
        self._loader = loader
        self._clock = clock
        self._music_started = False
        self._music_sounds = []
        self._ducks = {}
        self._temporary_duck_events = {}
        self._fade_event = None
        self._fade_from = None
        self._fade_progress = 1.0
        self._music_gain = 1.0
        self._fade_from_gain = 0.0
        self._prefetched_scene = None
        self._prefetched_sound = None

    def _load(self, name):
        if name in self.sounds:
            return self.sounds[name]
        sound = None
        paths = [os.path.join(SOUND_DIR, name + ".wav")]
        if name.startswith("music_"):
            paths.extend(os.path.join(SOUNDTRACK_RUNTIME_DIR, name + ext)
                         for ext in (".mp3", ".ogg", ".wav"))
        for path in paths:
            if not os.path.exists(path):
                continue
            try:
                sound = self._loader.load(path)
            except Exception:
                sound = None
            if sound is not None:
                break
        self.sounds[name] = sound
        return sound

    def _scene_sound(self, scene):
        preferred = self._load(MUSIC_SCENES[scene])
        sound = preferred if preferred is not None else self._load(MUSIC)
        if sound is not None:
            try:
                sound.loop = True
            except Exception:
                pass
            if not any(loaded is sound for loaded in self._music_sounds):
                self._music_sounds.append(sound)
        return sound

    def preload_music_scene(self, scene):
        """Decode one likely next scene without starting playback.

        Only one speculative track is retained.  Prefetching a different scene
        releases the previous unused candidate immediately.
        """
        scene = SCENE_ALIASES.get(scene, scene)
        if scene not in MUSIC_SCENES:
            raise ValueError(f"unknown music scene: {scene}")
        if scene == self.music_scene:
            return self.music
        if self._prefetched_scene not in (None, scene):
            candidate = self._prefetched_sound
            if candidate not in (self.music, self._fade_from):
                self._release_music(candidate)
            self._prefetched_scene = None
            self._prefetched_sound = None
        sound = self._scene_sound(scene)
        self._prefetched_scene = scene
        self._prefetched_sound = sound
        return sound

    def load_title_music(self):
        """Load only the title track (or procedural fallback)."""
        sound = self._scene_sound("title")
        if self.music is None:
            self.music = sound
            self.music_scene = "title"
            self._music_gain = 1.0
            self.apply_volumes()
        return sound

    def preload_effects_iter(self):
        """Load one effect per iteration and yield its name for boot progress."""
        for name in EFFECTS:
            self._load(name)
            yield name

    def play(self, name):
        """Retrigger one effect at the current SFX volume."""
        sound = self._load(name)
        if sound is None:
            return
        try:
            sound.volume = _clamp(self.settings.get("sfx_volume", 0.8))
            if getattr(sound, "state", None) == "play":
                sound.stop()
            sound.play()
        except Exception:
            return
        if name in EFFECT_DUCK:
            reason = "effect:" + name
            self.set_duck(reason, EFFECT_DUCK[name])
            previous = self._temporary_duck_events.pop(reason, None)
            if previous is not None:
                try:
                    previous.cancel()
                except Exception:
                    pass
            try:
                duration = max(0.2,
                               float(getattr(sound, "length", 0.0) or 1.0))
            except (TypeError, ValueError):
                duration = 1.0
            try:
                event = self._clock.schedule_once(
                    lambda _dt, key=reason: self._clear_temporary_duck(key),
                    duration)
                self._temporary_duck_events[reason] = event
            except Exception:
                self.clear_duck(reason)

    def _clear_temporary_duck(self, reason):
        self._temporary_duck_events.pop(reason, None)
        self.clear_duck(reason)

    def set_music_scene(self, scene):
        """Select a narrative/gameplay music state.

        When both scenes resolve to the same fallback Sound, playback simply
        continues. Distinct tracks use a two-second equal-power crossfade.
        """
        scene = SCENE_ALIASES.get(scene, scene)
        if scene not in MUSIC_SCENES:
            raise ValueError(f"unknown music scene: {scene}")
        if self._prefetched_scene not in (None, scene):
            candidate = self._prefetched_sound
            if candidate not in (self.music, self._fade_from):
                self._release_music(candidate)
            self._prefetched_scene = None
            self._prefetched_sound = None
        incoming = self._scene_sound(scene)
        if self._prefetched_scene == scene:
            self._prefetched_scene = None
            self._prefetched_sound = None
        self.music_scene = scene
        if incoming is self.music:
            self.apply_volumes()
            return incoming

        outgoing = self.music
        if not self._music_started or outgoing is None or incoming is None:
            self._cancel_fade()
            if outgoing is not None and outgoing is not incoming:
                self._release_music(outgoing)
            self.music = incoming
            self._music_gain = 1.0
            if self._music_started and incoming is not None:
                self._play_if_needed(incoming)
            self.apply_volumes()
            return incoming

        self._cancel_fade()
        self._fade_from = outgoing
        self.music = incoming
        self._fade_progress = 0.0
        self._fade_from_gain = 1.0
        self._music_gain = 0.0
        self._play_if_needed(incoming)
        self.apply_volumes()
        try:
            self._fade_event = self._clock.schedule_interval(
                self._advance_fade, 1.0 / 60.0)
        except Exception:
            self._finish_fade()
        return incoming

    def _advance_fade(self, dt):
        self._fade_progress = min(
            1.0, self._fade_progress + max(0.0, float(dt)) / CROSSFADE_SECONDS)
        angle = self._fade_progress * math.pi / 2.0
        self._fade_from_gain = math.cos(angle)
        self._music_gain = math.sin(angle)
        self.apply_volumes()
        if self._fade_progress >= 1.0:
            self._finish_fade()
            return False
        return True

    def _finish_fade(self):
        old = self._fade_from
        self._fade_from = None
        self._fade_from_gain = 0.0
        self._music_gain = 1.0
        self._fade_event = None
        if old is not None and old is not self.music:
            self._release_music(old)
        self.apply_volumes()

    def _cancel_fade(self):
        event = self._fade_event
        self._fade_event = None
        if event is not None:
            try:
                event.cancel()
            except Exception:
                try:
                    self._clock.unschedule(event)
                except Exception:
                    pass
        old = self._fade_from
        self._fade_from = None
        if old is not None and old is not self.music:
            self._release_music(old)
        self._fade_from_gain = 0.0
        self._music_gain = 1.0

    def _release_music(self, sound):
        """Stop and unload one decoded track, removing every cache alias."""
        if sound is None:
            return
        self._stop(sound)
        try:
            sound.unload()
        except Exception:
            pass
        self._music_sounds = [item for item in self._music_sounds
                              if item is not sound]
        for name, cached in tuple(self.sounds.items()):
            if cached is sound:
                del self.sounds[name]
        if self._prefetched_sound is sound:
            self._prefetched_scene = None
            self._prefetched_sound = None

    @staticmethod
    def _stop(sound):
        try:
            sound.stop()
        except Exception:
            pass

    @staticmethod
    def _play_if_needed(sound):
        try:
            if getattr(sound, "state", None) != "play":
                sound.play()
        except Exception:
            pass

    def start_music(self):
        """Start the selected scene, defaulting to title."""
        if self.music is None:
            self.load_title_music()
        self._music_started = True
        if self.music is not None:
            self._play_if_needed(self.music)
        self.apply_volumes()

    def stop_music(self):
        self._music_started = False
        self._cancel_fade()
        for sound in tuple(self._music_sounds):
            self._release_music(sound)
        self.music = None
        self.music_scene = None
        self._prefetched_scene = None
        self._prefetched_sound = None

    def set_duck(self, reason, factor):
        """Add or replace a named music attenuation factor."""
        if not reason:
            raise ValueError("duck reason must not be empty")
        self._ducks[str(reason)] = _clamp(factor)
        self.apply_volumes()

    def clear_duck(self, reason):
        self._ducks.pop(str(reason), None)
        self.apply_volumes()

    def _duck_factor(self):
        return min(self._ducks.values(), default=1.0)

    def apply_volumes(self):
        """Apply live master volume, ducking and current fade gains."""
        master = _clamp(self.settings.get("music_volume", 0.6))
        master *= self._duck_factor()
        if self.music is not None:
            try:
                self.music.volume = master * self._music_gain
            except Exception:
                pass
        if self._fade_from is not None:
            try:
                self._fade_from.volume = master * self._fade_from_gain
            except Exception:
                pass
