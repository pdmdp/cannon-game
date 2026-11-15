"""The screen where the game is played: the game loop, input handling,
the HUD and the campaign flow.

The hand-crafted 10-level campaign. Each level declares its shot budget
at the start (per the assignment); running out means retrying the level,
and every shot ever fired counts toward the total used by the Hall
of Fame ranks. S/L save and load a full snapshot of the run at any
moment while aiming (assignment: Save/Load).

Campaign flow (self.state):
    "briefing"      -> SPACE/click arms the cannon; it does not fire
    "aiming"        -> player controls the cannon, SPACE/click fires
    "flying"        -> a projectile is in flight (no firing meanwhile)
    "won"           -> beacon destroyed; ENTER starts the next level
    "failed"        -> budget exhausted; ENTER retries the level
    "campaign_over" -> last beacon down; ENTER returns to the menu
"""

import math
import random

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import (Color, Ellipse, InstructionGroup, Line, Point,
                           PopMatrix, PushMatrix, Rectangle, Rotate,
                           RoundedRectangle, Translate)
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from game import art
from game import constants as C
from game import levels
from game import physics
from game import storage
from game import story
from game.cannon import Cannon, PROJECTILE_COLORS, PROJECTILE_TYPES
from game.obstacles import obstacle_from_dict
from game.projectiles import spawn_projectile
from game.particles import ParticleRenderer
from game.screens import (DialogueCard, FONT_BODY, FONT_DISPLAY, FONT_MONO,
                          StarField, play_cinematic)
from game.target import Target

# Integer key codes delivered by Kivy's Window.on_key_down event.
KEY_ESC = 27
KEY_ENTER = 13
KEY_NUMPAD_ENTER = 271
KEY_SPACE = 32
KEY_UP = 273
KEY_DOWN = 274
KEY_RIGHT = 275
KEY_LEFT = 276

# HUD weapon-chip icons and particle textures (missing files fall back).
_WEAPON_ICONS = {"bullet": "icon_bullet", "bombshell": "icon_bomb",
                 "laser": "icon_laser"}
_FX_TEXTURES = {"spark": "fx_spark", "smoke": "fx_smoke", "flash": "fx_flash"}


def music_scene_for_level(index, phase=0):
    """Return the score state for one deterministic campaign round."""
    if index == 9:
        return f"foreman_p{max(1, min(3, int(phase) + 1))}"
    if index >= 6:
        return "anomaly"
    if index >= 4:
        return "warden"
    return "belt"


def next_music_scene_to_prefetch(index, phase=0):
    """One upcoming state worth decoding while the player is occupied."""
    if index == 3:
        return "warden"
    if index == 5:
        return "anomaly"
    if index == 8:
        return "foreman_p1"
    if index == 9 and phase < 2:
        return f"foreman_p{phase + 2}"
    return None


def _point_along(points, frac):
    """The point at fraction `frac` (0..1) along a flat polyline
    [x0, y0, x1, y1, ...], used to slide energy packets down the laser."""
    if len(points) < 4:
        return points[0], points[1]
    segments = []
    total = 0.0
    for i in range(0, len(points) - 2, 2):
        ax, ay, bx, by = points[i], points[i + 1], points[i + 2], points[i + 3]
        length = math.hypot(bx - ax, by - ay)
        segments.append((ax, ay, bx, by, length))
        total += length
    if total <= 0:
        return points[0], points[1]
    distance = frac * total
    for ax, ay, bx, by, length in segments:
        if distance <= length and length > 0:
            t = distance / length
            return ax + (bx - ax) * t, ay + (by - ay) * t
        distance -= length
    return segments[-1][2], segments[-1][3]


class GameScreen(Screen):
    """Owns the world drawing, the HUD, the update loop and the round state."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()   # holds the live settings dict
        self.cannon = Cannon()
        self.target = None
        self.projectile = None
        self.last_shot_outcome = None
        self.obstacles = []
        self.state = "briefing"
        self._hit_pause = 0.0
        self.level_index = 0
        self.campaign_difficulty = self.app.settings.get(
            "difficulty", "normal")
        # ``difficulty`` remains as a compatibility alias for v1/v2 saves.
        self.difficulty = self.campaign_difficulty
        self.weapons = ("bullet",)   # story unlocks fill this per level
        self.shots_left = None       # None = unlimited
        self.shots_round = 0
        self.shots_total = 0
        self.campaign_active = False
        self.active_slot = None
        self._phase_event = None

        # Children are drawn in the order they are added:
        # sky at the bottom, then the game world, then the HUD on top.
        self._stars = StarField()
        self.add_widget(self._stars)

        # Illustrated backdrops (drawn over the starfield; an Image with
        # no texture renders nothing, so missing art falls back to stars).
        # Slightly oversized to keep the edge outside the parallax drift.
        self._bg_far = Image(fit_mode="fill",
                             size_hint=(None, None),
                             size=(C.SCREEN_WIDTH + 56, C.SCREEN_HEIGHT + 32))
        self.add_widget(self._bg_far)
        self._bg_near = Image(fit_mode="fill",
                              size_hint=(None, None),
                              size=(C.SCREEN_WIDTH + 96, C.SCREEN_HEIGHT + 54))
        self.add_widget(self._bg_near)

        # Per-level non-colliding decoration and restrained color grading.
        # These layers change the sector identity without changing a single
        # physics coordinate or puzzle solution.
        self._decor_layer = Widget()
        self.add_widget(self._decor_layer)
        self._grade_layer = Widget()
        with self._grade_layer.canvas:
            self._grade_color = Color(0, 0, 0, 0)
            self._grade_rect = Rectangle(
                pos=(0, 0), size=(C.SCREEN_WIDTH, C.SCREEN_HEIGHT))
        self.add_widget(self._grade_layer)
        self._mouse_x = C.SCREEN_WIDTH / 2
        self._ambient_t = 0.0

        self.world = Widget()
        self.add_widget(self.world)

        # Screen shake: the whole world canvas is drawn inside a
        # translation that the shake wiggles for a fraction of a second.
        with self.world.canvas.before:
            PushMatrix()
            self._shake_translate = Translate(0, 0, 0)
        with self.world.canvas.after:
            PopMatrix()
        self._shake = None   # None or {"mag", "age"}

        # World draw order = creation order below: cannon, obstacles,
        # aim preview, projectile, target, explosion ring, particles.
        self.cannon.draw_on(self.world.canvas)

        self._obstacles_group = InstructionGroup()
        self.world.canvas.add(self._obstacles_group)

        with self.world.canvas:
            self._preview_color = Color(1, 1, 1, 0)
            self._preview = Point(points=[], pointsize=2.5)

        self._proj_group = InstructionGroup()
        self.world.canvas.add(self._proj_group)
        self._proj_ins = {}
        self._target_group = InstructionGroup()
        self.world.canvas.add(self._target_group)

        with self.world.canvas:
            self._boom_color = Color(1, 1, 1, 0)
            self._boom_ring = Line(circle=(0, 0, 1), width=2.5)
        self._boom = None   # None or {"x", "y", "age", "max_r", "rgb"}

        # Debris state plus a fixed pool of canvas instructions.
        self._particles = []
        self._particles_group = InstructionGroup()
        self.world.canvas.add(self._particles_group)
        self._particle_renderer = ParticleRenderer(self._particles_group)

        self._build_hud()
        self.dialogue = DialogueCard()
        self.add_widget(self.dialogue)
        self._briefing_pending = None
        self._space_held = False
        self._visible = False
        self._trail_timer = 0.0
        self._hit_pause = 0.0
        self._loop_event = None
        self._music_prefetch_event = None
        self.start_level(0)

    # ------------------------------------------------------------------
    # Campaign flow
    # ------------------------------------------------------------------

    def _player_name(self):
        return self.app.settings.get("player_name", "GUNNER")

    def _cancel_dialogue(self):
        """Discard a narrative card without running its completion callback.

        The fallback clears the same state on dialogue objects that do not
        provide the public ``cancel`` method.
        """
        dialogue = getattr(self, "dialogue", None)
        if dialogue is None:
            return
        cancel = getattr(dialogue, "cancel", None)
        if callable(cancel):
            cancel(invoke_callback=False)
            return
        dialogue._on_done = None
        dialogue._lines = []
        dialogue.active = False
        event = getattr(dialogue, "_type_event", None)
        if event is not None:
            event.cancel()
            dialogue._type_event = None
        set_visible = getattr(dialogue, "_set_visible", None)
        if callable(set_visible):
            set_visible(False)

    def start_campaign(self):
        """Start a new run and lock Settings difficulty for its lifetime."""
        self._cancel_dialogue()
        selected = self.app.settings.get("difficulty", "normal")
        self.campaign_difficulty = (
            selected if selected in ("easy", "normal", "hard") else "normal")
        self.difficulty = self.campaign_difficulty
        self.shots_total = 0
        self.shots_round = 0
        self.active_slot = None
        self.campaign_active = True
        self.start_level(0)

    # UI-facing name used by the mission-control menu.
    new_campaign = start_campaign

    def _start_aiming(self):
        """Dismiss the briefing without spending a shot."""
        dialogue = getattr(self, "dialogue", None)
        if self.state != "briefing" or getattr(dialogue, "active", False):
            return False
        self.state = "aiming"
        self.overlay.text = ""
        return True

    def start_level(self, index, retry=False, phase=0):
        """Enter a campaign level (or a boss phase of it): build the
        scenario, declare the shot budget (assignment: declared at the
        beginning of the round) and show the briefing until the first
        shot. Boss phases share the level's budget and shot count."""
        self.level_index = index
        self.phase = phase
        self._cancel_dialogue()
        self.state = "briefing"
        self._clear_projectile()
        self._boom = None
        self._boom_color.a = 0

        boss = levels.boss_info(index)
        obstacles, target = levels.build_level(index, phase)
        self.set_obstacles(obstacles)
        sprite = boss["sprite"] if boss else "sprite_beacon"
        if index == 4 and phase > 0 and art.has_art("sprite_warden_damaged"):
            sprite = "sprite_warden_damaged"
        elif index == 9 and phase == 1 and art.has_art("sprite_foreman_damaged"):
            sprite = "sprite_foreman_damaged"
        elif index == 9 and phase >= 2 and art.has_art("sprite_foreman_critical"):
            sprite = "sprite_foreman_critical"
        self.place_target(*target, sprite=sprite)
        self._set_backdrop(index)
        scene = music_scene_for_level(index, phase)
        # The constructor builds a dormant level behind the title screen.  Do
        # not let that invisible setup replace the title music.  New/load runs
        # and visible boss phases switch immediately.
        if ((getattr(self, "_visible", False) or
             getattr(self, "campaign_active", False)) and
                hasattr(self.app.audio, "set_music_scene")):
            self.app.audio.set_music_scene(scene)
        schedule_prefetch = getattr(self, "_schedule_music_prefetch", None)
        if callable(schedule_prefetch):
            schedule_prefetch(index, phase)

        # Story unlocks: only weapons Toko has delivered are usable.
        self.weapons = levels.weapons_for(index)
        if self.cannon.projectile not in self.weapons:
            self.cannon.select_projectile("bullet")

        if phase == 0:
            # Settings may change while a run is paused; only
            # ``start_campaign`` is allowed to change this locked value.
            self.difficulty = self.campaign_difficulty
            self.shots_round = 0
            self.shots_left = levels.shot_budget(
                index, self.campaign_difficulty)

        data = levels.LEVELS[index]
        if index == levels.level_count() - 1 and phase == 0 and not retry:
            self.app.audio.play("warning_pulse")
        if self.shots_left is None:
            budget_line = "Plasma budget: unlimited"
        else:
            budget_line = f"Plasma budget: {self.shots_left} shells"
        title = f"LEVEL {index + 1:02d}: {data['name']}"
        if boss and phase > 0:
            title = f"{boss['name']}: PHASE {phase + 1}"
        prefix = "RETRY: " if retry else ""
        self.overlay.text = (
            f"[b]{prefix}{title}[/b]\n"
            f"[i]{data['flavor']}[/i]\n"
            f"{budget_line}\n\n"
            "[color=#ffca70]PRESS SPACE TO START LEVEL[/color]"
        )

        # The story briefing plays on a fresh visit (not on retries or
        # boss phases, whose dialogue is handled at the transition).
        if phase == 0 and not retry:
            lines = story.BRIEFINGS.get(index)
            if lines:
                if self._visible:
                    self.dialogue.run(lines, self._player_name())
                else:
                    self._briefing_pending = lines

    def _set_backdrop(self, index):
        """Pick the act's illustrated backdrop (missing art -> starfield)."""
        if index <= 2:
            far = "bg_act1"
        elif index <= 6:
            far = "bg_act2"
        else:
            far = "bg_act3"
        if index == levels.level_count() - 1 and art.has_art("bg_boss"):
            far = "bg_boss"
        near = {"bg_act1": "bg_act1_near", "bg_act2": "bg_act2_near",
                "bg_act3": "bg_act3_near"}.get(far)
        far_tex = art.texture(far)
        near_tex = art.keyed_texture(near) if near else None
        self._bg_far.texture = far_tex
        self._bg_near.texture = near_tex
        # A kivy Image with no texture renders a solid white quad, so any
        # missing layer must be hidden entirely (the starfield shows through).
        self._bg_far.opacity = 1.0 if far_tex is not None else 0.0
        self._bg_near.opacity = 1.0 if near_tex is not None else 0.0
        self._set_scene_style(index)

    def _set_scene_style(self, index):
        """Apply deterministic palette grading and non-gameplay decor."""
        data = levels.LEVELS[index]
        palette = levels.PALETTES[data["palette"]]
        self._grade_color.rgba = palette["tint"]
        accent = palette["accent"]
        decor = data["decor"]
        self._decor_layer.canvas.clear()
        with self._decor_layer.canvas:
            Color(*accent, 0.11)
            if decor in ("outpost", "steel_grid", "mirror_array"):
                for x in range(390, 1280, 150):
                    Line(points=(x, 60, x + 90, 700), width=0.7)
            elif decor in ("debris", "blast_marks", "canyon"):
                rng = random.Random(index + 811)
                for _ in range(24):
                    x, y = rng.randrange(340, 1260), rng.randrange(45, 680)
                    Ellipse(pos=(x, y), size=(rng.randrange(2, 8),
                                              rng.randrange(2, 8)))
            elif decor == "portal_grid":
                for radius in (90, 150, 220, 300):
                    Line(circle=(780, 350, radius), width=0.8)
            elif decor == "gravity_dust":
                for radius in (80, 135, 200, 270):
                    Line(ellipse=(700 - radius, 420 - radius * 0.45,
                                  radius * 2, radius * 0.9), width=0.8)
            elif decor == "elastic_ridge":
                for y in range(80, 660, 80):
                    Line(points=(360, y, 760, y + 24, 1120, y - 8), width=0.8)
            elif decor == "hazard":
                for x in range(330, 1300, 90):
                    Line(points=(x, 24, x + 54, 76), width=2.0)

    def set_obstacles(self, obstacles):
        """Adopt the round's obstacles and draw each in its own group."""
        self.obstacles = list(obstacles)
        self._obstacles_group.clear()
        for obstacle in self.obstacles:
            group = InstructionGroup()
            self._obstacles_group.add(group)
            obstacle.attach(group)

    def place_target(self, x, y, sprite="sprite_beacon"):
        """Create the round's target at (x, y) and draw it."""
        self.target = Target(x, y, sprite=sprite)
        self._target_group.clear()
        self.target.draw_on(self._target_group)

    def _try_select(self, name):
        """Switch weapon if the story has delivered it yet."""
        if (self.state != "aiming"
                or getattr(getattr(self, "dialogue", None), "active", False)):
            return False
        if name not in self.weapons:
            self._toast("LOCKED: Toko hasn't delivered that yet")
            return False
        if name != self.cannon.projectile:
            self.cannon.select_projectile(name)
            self.app.audio.play("click")
        return True

    def fire(self):
        """Launch the selected projectile from the muzzle (one at a time)."""
        if (self.state != "aiming"
                or getattr(getattr(self, "dialogue", None), "active", False)):
            return False
        if self.shots_left is not None and self.shots_left <= 0:
            # Clamp a restored edge case or input arriving before the next
            # update, then resolve the exhausted budget.
            self.shots_left = 0
            self._on_level_failed()
            return False
        mx, my = self.cannon.muzzle_pos()
        dx, dy = self.cannon.direction()
        speed = self.cannon.velocity
        self.projectile = spawn_projectile(self.cannon.projectile,
                                           mx, my, dx * speed, dy * speed)
        self.last_shot_outcome = None
        self.shots_round += 1
        self.shots_total += 1
        if self.shots_left is not None:
            self.shots_left = max(0, self.shots_left - 1)
        self.state = "flying"
        self.overlay.text = ""      # the briefing disappears at the first shot
        self._draw_projectile()
        # Muzzle flash, a few sparks and the barrel recoil sell the shot.
        self._spawn_particles(mx, my, 5, self.projectile.color[:3])
        self.cannon.kick()
        self.app.audio.play({"bullet": "fire_bullet",
                             "bombshell": "fire_bomb",
                             "laser": "fire_laser"}[self.projectile.kind])
        return True

    def _on_target_hit(self):
        """Target down: next boss phase, next level, or the campaign ends."""
        self._start_boom(self.target.x, self.target.y, 110, (1, 0.85, 0.7))
        self._spawn_particles(self.target.x, self.target.y,
                              C.PARTICLE_BIG, C.COLOR_TARGET[:3])
        self._start_shake(12)
        self.app.audio.play("explosion_big")
        self.app.audio.play("beacon_down")
        if self.phase + 1 >= levels.phase_count(self.level_index):
            self.app.audio.play("victory_sting")
        self._clear_projectile()
        name = self._player_name()

        # A boss with phases left: play the transition dialogue, rebuild the
        # arena and keep the level budget running. Each phase follows a hit.
        if self.phase + 1 < levels.phase_count(self.level_index):
            # Destroying an intermediate core with the final shell is still
            # a failed level: the remaining boss phases cannot be played
            # with an exhausted budget. A retry rebuilds phase one.
            if self.shots_left is not None and self.shots_left <= 0:
                self.shots_left = 0
                # The 85 ms target hit-pause has already shown the impact;
                # fail now, before any next-phase arena can become playable.
                self._on_level_failed()
                return
            self.state = "phase_transition"
            next_phase = self.phase + 1
            lines = story.PHASE_DIALOGUE.get((self.level_index, next_phase))

            def next_phase_now(_dt=0):
                self._phase_event = None
                self.start_level(self.level_index, phase=next_phase)
                if lines:
                    self.dialogue.run(lines, name)

            self.overlay.text = (
                f"[b]CORE INTEGRITY {2 - self.phase}/3[/b]\n"
                "FOREMAN ARRAY RECONFIGURING")
            self.app.audio.play("warning_pulse")
            delay = (0.0 if self.app.settings.get("reduced_motion", False)
                     else 0.9)
            self._phase_event = Clock.schedule_once(next_phase_now, delay)
            return

        victory_lines = story.VICTORIES.get(self.level_index, [])
        if self.level_index + 1 >= levels.level_count():
            self.state = "campaign_over"
            self.overlay.text = ""
            def show_final_result():
                self._show_result()
            if victory_lines:
                self.dialogue.run(victory_lines, name, show_final_result)
            else:
                show_final_result()
        else:
            self.state = "won"
            self.overlay.text = ""

            def show_won_overlay():
                self._show_result()
            if victory_lines:
                self.dialogue.run(victory_lines, name, show_won_overlay)
            else:
                show_won_overlay()

    def _begin_target_hit(self):
        """Hold the impact image briefly before resolving the round."""
        if self.app.settings.get("reduced_motion", False):
            self._on_target_hit()
            return
        self.state = "hit_pause"
        self._hit_pause = C.TARGET_HIT_PAUSE
        if self.target is not None:
            self.target.set_hit_flash(True)

    def _show_result(self):
        data = levels.LEVELS[self.level_index]
        if hasattr(self.app.audio, "preload_music_scene"):
            if self.level_index + 1 >= levels.level_count():
                self.app.audio.preload_music_scene("epilogue")
            elif self.level_index in story.INTERLUDES:
                self.app.audio.preload_music_scene("story")
        self.overlay.text = (
            f"[b]BEACON {self.level_index + 1:02d}/10 DESTROYED[/b]\n"
            f"{self.shots_round} SHOTS   |   PAR {data['par']}   |   "
            f"{self.shots_total} TOTAL\n"
            "[i]Press Enter to continue[/i]"
        )

    def _advance_after_result(self):
        next_index = self.level_index + 1
        interlude = story.INTERLUDES.get(self.level_index)
        if interlude:
            play_cinematic(self.manager, interlude, self._player_name(),
                           lambda: self._resume_at(next_index),
                           preload_scene=music_scene_for_level(next_index, 0))
        else:
            self.start_level(next_index)

    def _resume_at(self, index):
        self.start_level(index)
        self.manager.current = "game"

    def _finish_campaign(self):
        if self.state != "campaign_over":
            return
        self.state = "epilogue"
        self._hall_place = storage.add_hall_of_fame_entry(
            self._player_name(), self.shots_total)
        play_cinematic(self.manager, story.EPILOGUE, self._player_name(),
                       self._after_epilogue, music_scene="epilogue")

    def _after_epilogue(self):
        """Back from the epilogue: show the new Hall of Fame result."""
        self.campaign_active = False
        self.active_slot = None
        self.app._hall_from_epilogue = True
        self.manager.current = "hall_of_fame"

    def _on_level_failed(self):
        """The budget is spent and the beacon still stands."""
        self.app.audio.play("fail")
        self.state = "failed"
        self.overlay.text = (
            "[b]OUT OF PLASMA[/b]\n"
            "The beacon still stands. Every fired shot remains in your total.\n"
            "[i]Press Enter to retry the level[/i]"
        )

    # ------------------------------------------------------------------
    # Save / Load (assignment requirement): one full-snapshot slot
    # ------------------------------------------------------------------

    def snapshot(self):
        """The saveable run as a dictionary: progress, aiming state, target,
        obstacles, and surviving cells for cell-based obstacles."""
        return {
            "version": storage.SAVE_VERSION,
            "level_index": self.level_index,
            "phase": self.phase,
            # Schema v3 names the locked value explicitly. Keep the older key
            # as a runtime compatibility alias for v1/v2 snapshots.
            "campaign_difficulty": getattr(
                self, "campaign_difficulty", self.difficulty),
            "difficulty": getattr(
                self, "campaign_difficulty", self.difficulty),
            "shots_total": self.shots_total,
            "shots_round": self.shots_round,
            "shots_left": self.shots_left,
            "cannon": self.cannon.to_dict(),
            "target": self.target.to_dict(),
            "obstacles": [ob.to_dict() for ob in self.obstacles],
        }

    def restore(self, data):
        """Adopt a snapshot produced by snapshot(). Raises on bad data."""
        data = storage.validate_save(data)
        # Call through the implementation because dialogue cancellation is a
        # UI-only helper that may be absent on a partly constructed screen.
        GameScreen._cancel_dialogue(self)
        if getattr(self, "_phase_event", None) is not None:
            self._phase_event.cancel()
            self._phase_event = None
        index = data["level_index"]
        self.level_index = index
        self.phase = data["phase"]
        self.campaign_difficulty = data.get(
            "campaign_difficulty", data.get("difficulty", "normal"))
        self.difficulty = self.campaign_difficulty
        self.shots_total = data["shots_total"]
        self.shots_round = data["shots_round"]
        self.shots_left = data["shots_left"]
        self.weapons = levels.weapons_for(index)
        if data["cannon"]["projectile"] not in self.weapons:
            raise ValueError("saved projectile is not unlocked")
        self._clear_projectile()
        self._boom = None
        self._boom_color.a = 0
        self.set_obstacles([obstacle_from_dict(d) for d in data["obstacles"]])
        target = data["target"]
        self.place_target(target["x"], target["y"], sprite=target["sprite"])
        self.cannon.restore(data["cannon"])
        self._set_backdrop(index)
        self._briefing_pending = None
        self.state = "aiming"
        self.campaign_active = True
        self.overlay.text = ""

    def save_snapshot(self):
        if self.state != "aiming":
            self._toast("SAVE: only while aiming")
            return False
        if self.active_slot is None:
            self.app.open_save_slots("save", return_screen="game")
            return False
        return self.save_to_slot(self.active_slot)

    def save_to_slot(self, slot):
        if self.state != "aiming":
            self._toast("SAVE: only while aiming")
            return False
        storage.save_game(self.snapshot(), slot, self._player_name())
        self.active_slot = slot
        self._toast(f"MISSION SAVED TO SLOT {slot}")
        return True

    def load_snapshot(self):
        if self.dialogue.active or self.state != "aiming":
            self._toast("LOAD: only while aiming")
            return False
        self.app.open_save_slots("load", return_screen="game")
        return True

    # ------------------------------------------------------------------
    # Collisions and damage
    # ------------------------------------------------------------------

    def _first_event(self, ax, ay, bx, by, is_laser, exclude=None):
        """The earliest thing met along the movement segment A->B.

        Returns (kind, t, x, y, obj) with t in [0, 1] along the segment,
        kind in {"target", "rock", "mirror", "elastonio", "wormhole"},
        or None for a free path.

        Thin panes (mirror/elastonio) use a direct segment-segment
        intersection test; the target, rock cells and wormhole portals are
        tested by sampling every quarter cell, which also keeps the order
        of events correct (a rock in front of the beacon protects it).
        Lasers ignore elastonio panes entirely. `exclude` skips the pane
        we just bounced off within this same simulation step.
        """
        best = None
        for ob in self.obstacles:
            if ob is exclude:
                continue
            if ob.kind == "mirror" or (ob.kind == "elastonio" and not is_laser):
                hit = physics.segment_intersection(ax, ay, bx, by, *ob.segment())
                if hit is not None and (best is None or hit[0] < best[1]):
                    best = (ob.kind, hit[0], hit[1], hit[2], ob)

        step = C.ROCK_CELL / 4.0
        length = math.hypot(bx - ax, by - ay)
        steps = max(1, int(length / step) + 1)
        for i in range(1, steps + 1):
            t = min(1.0, i / steps)
            if best is not None and t >= best[1]:
                break   # the pane hit happens before this sample
            sx, sy = ax + (bx - ax) * t, ay + (by - ay) * t
            tdx, tdy = sx - self.target.x, sy - self.target.y
            if tdx * tdx + tdy * tdy <= self.target.radius ** 2:
                return ("target", t, sx, sy, None)
            for obstacle in self.obstacles:
                if obstacle.kind == "wormhole":
                    if obstacle.portal_at(sx, sy) is not None:
                        return ("wormhole", t, sx, sy, obstacle)
                elif obstacle.cell_at(sx, sy) is not None:
                    return ("rock", t, sx, sy, obstacle)
        return best

    def _field_accel(self, px, py):
        """Total acceleration from every Gravitonio anomaly at a point."""
        ax = ay = 0.0
        for ob in self.obstacles:
            if ob.kind == "gravitonio":
                fx, fy = ob.field_accel(px, py)
                ax += fx
                ay += fy
        return ax, ay

    def _advance_projectile(self, p, dt):
        """Move the projectile one simulation step and resolve what it meets.

        Returns "hit_target", "impacted" (shot spent on an obstacle) or
        "flying". Panes reflect (mirror: lasers, elastonio: massive) and
        wormholes teleport, both continuing the leftover movement of the
        step, with at most four events resolved by this call.
        """
        if p.massive:
            # Gravitonio anomalies bend massive projectiles (assignment:
            # both velocity components, radially).
            fx, fy = self._field_accel(p.x, p.y)
            p.vx += fx * dt
            p.vy += fy * dt
        p.update(dt)
        ax, ay = p.prev_x, p.prev_y
        bx, by = p.x, p.y
        exclude = None
        # The fixed cap bounds work in degenerate layouts. If all four events
        # are used, the remaining endpoint is accepted after the loop.
        for _ in range(4):
            event = self._first_event(ax, ay, bx, by, p.kind == "laser", exclude)
            if event is None:
                p.x, p.y = bx, by
                return "flying"
            kind, _t, hx, hy, obj = event
            if kind == "target":
                return "hit_target"
            if kind == "rock":
                self._impact_at(hx, hy)
                return "impacted"

            speed = math.hypot(p.vx, p.vy) or 1.0
            ux, uy = p.vx / speed, p.vy / speed
            leftover = math.hypot(bx - hx, by - hy)

            if kind == "wormhole":
                # Out of the paired portal, velocity unchanged. The exit
                # point sits just outside the portal's rim, so the shot
                # does not instantly re-enter it.
                ex, ey = obj.exit_for(hx, hy)
                nx = ex + ux * (obj.radius + 2.0)
                ny = ey + uy * (obj.radius + 2.0)
                if p.kind == "laser":
                    p.reset_path(nx, ny)
                self.app.audio.play("teleport")
                ax, ay = nx, ny
                bx, by = nx + ux * leftover, ny + uy * leftover
                exclude = None
                continue

            # A pane. Mirror reflects lasers; elastonio reflects massive
            # projectiles (lasers never even collide with it). A massive
            # projectile reaching a mirror splats against the glass.
            if kind == "mirror" and p.kind != "laser":
                self._impact_at(hx, hy, on_mirror=True)
                return "impacted"
            p.vx, p.vy = physics.reflect(p.vx, p.vy, *obj.normal())
            self.app.audio.play("reflect")
            speed = math.hypot(p.vx, p.vy) or 1.0
            ux, uy = p.vx / speed, p.vy / speed
            if p.kind == "laser":
                p.add_bounce(hx, hy)
            # Continue the leftover movement in the new direction,
            # starting a hair off the pane to avoid re-hitting it.
            ax, ay = hx + ux * 0.01, hy + uy * 0.01
            bx, by = hx + ux * leftover, hy + uy * leftover
            exclude = obj
        p.x, p.y = bx, by
        return "flying"

    def _impact_at(self, impact_x, impact_y, on_mirror=False):
        """Apply the weapon's damage pattern at the impact point.

        Damage is applied to every obstacle in range (Perpetio and Mirror
        damage methods are no-ops), then the projectile is spent. On a
        mirror surface the bombshell cannot drill in (it is bulletproof),
        so it explodes right where it touched.
        """
        p = self.projectile
        speed = math.hypot(p.vx, p.vy)
        ux, uy = (p.vx / speed, p.vy / speed) if speed else (1.0, 0.0)
        removed = 0

        if p.kind == "bullet":
            # Crater around the impact point (assignment: BULLET_RADIUS).
            for ob in self.obstacles:
                removed += ob.destroy_circle(impact_x, impact_y, C.BULLET_RADIUS)
            self._start_boom(impact_x, impact_y, 40, p.color[:3])
            self._spawn_particles(impact_x, impact_y, C.PARTICLE_SMALL,
                                  p.color[:3])
            self.app.audio.play("explosion_small")
        elif p.kind == "bombshell":
            # Drill BOMB_DRILL deeper along the flight direction, then
            # explode with the bigger BOMB_RADIUS (assignment).
            drill = 0.0 if on_mirror else C.BOMB_DRILL
            cx = impact_x + ux * drill
            cy = impact_y + uy * drill
            for ob in self.obstacles:
                removed += ob.destroy_circle(cx, cy, C.BOMB_RADIUS)
            self._start_boom(cx, cy, 85, p.color[:3])
            self._spawn_particles(cx, cy, C.PARTICLE_BIG, p.color[:3])
            self._start_shake(8)
            self.app.audio.play("explosion_big")
        else:
            # Laser: carve a corridor LASER_IMPULSE deep and LASER_DIST
            # wide along the trajectory (assignment), then the impulse
            # is spent.
            ex = impact_x + ux * C.LASER_IMPULSE
            ey = impact_y + uy * C.LASER_IMPULSE
            for ob in self.obstacles:
                removed += ob.destroy_corridor(impact_x, impact_y, ex, ey,
                                               C.LASER_DIST)
            self._start_boom(impact_x, impact_y, 30, p.color[:3])
            self._spawn_particles(impact_x, impact_y, C.PARTICLE_SMALL,
                                  p.color[:3])
            self.app.audio.play("zap_hit")

        if removed:
            # Rock dust flies off whatever crumbled.
            self._spawn_particles(impact_x, impact_y,
                                  min(removed, C.PARTICLE_SMALL),
                                  C.COLOR_ROCK[:3])
            for ob in self.obstacles:
                ob.redraw()
        self._clear_projectile()   # the shot is spent; keep aiming
        self.last_shot_outcome = "obstacle"
        self.state = "aiming"

    # ------------------------------------------------------------------
    # Debris particles and screen shake
    # ------------------------------------------------------------------

    def _spawn_particles(self, x, y, count, rgb):
        """An impact burst: one bright flash, glowing sparks flying out,
        and a few smoke puffs rising after. They use textures when the FX art
        exists, plain squares otherwise."""
        reduced = self.app.settings.get("reduced_motion", False)
        if reduced:
            count = max(2, count // 3)
        self._particles.append({
            "kind": "flash", "x": x, "y": y, "vx": 0.0, "vy": 0.0,
            "age": 0.0, "ttl": 0.08 if reduced else 0.18,
            "size": 14.0 if reduced else 30.0,
            "grow": 100.0 if reduced else 420.0,
            "rgb": (1.0, 0.97, 0.88)})
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(70, 300)
            self._particles.append({
                "kind": "spark", "x": x, "y": y,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed + 60,
                "age": 0.0, "ttl": random.uniform(0.3, C.PARTICLE_TTL),
                "size": random.uniform(8, 18), "grow": 0.0, "rgb": rgb})
        for _ in range(max(2, count // 4)):
            self._particles.append({
                "kind": "smoke",
                "x": x + random.uniform(-8, 8), "y": y + random.uniform(-8, 8),
                "vx": random.uniform(-30, 30), "vy": random.uniform(25, 70),
                "age": 0.0, "ttl": random.uniform(0.7, 1.4),
                "size": random.uniform(20, 40), "grow": 46.0,
                "rgb": (0.62, 0.66, 0.74)})
        del self._particles[:-C.PARTICLE_CAP]   # oldest dropped first

    def _update_particles(self, dt):
        """Sparks obey gravity, smoke rises and swells, flashes bloom."""
        alive = []
        for particle in self._particles:
            particle["age"] += dt
            if particle["age"] >= particle["ttl"]:
                continue
            if particle["kind"] == "spark":
                particle["vy"] -= C.GRAVITY * 0.7 * dt
            particle["x"] += particle["vx"] * dt
            particle["y"] += particle["vy"] * dt
            particle["size"] += particle["grow"] * dt
            alive.append(particle)
        self._particles = alive
        self._particle_renderer.draw(alive)

    def _emit_trail(self, p, dt):
        """A flying shot leaves its signature behind: sparks for the
        bullet, smoke and embers for the heavy bombshell, a faint
        shimmer for the laser head."""
        self._trail_timer += dt
        if self._trail_timer < 0.045:
            return
        self._trail_timer = 0.0
        r, g, b = p.color[:3]
        speed = math.hypot(p.vx, p.vy) or 1.0
        ux, uy = p.vx / speed, p.vy / speed
        tail_x, tail_y = p.x - ux * 14, p.y - uy * 14
        self._particles.append({
            "kind": "spark", "x": tail_x, "y": tail_y,
            "vx": -ux * 40 + random.uniform(-15, 15),
            "vy": -uy * 40 + random.uniform(-15, 15),
            "age": 0.0, "ttl": random.uniform(0.18, 0.35),
            "size": random.uniform(6, 11), "grow": 0.0, "rgb": (r, g, b)})
        if p.kind == "bombshell":
            self._particles.append({
                "kind": "smoke", "x": tail_x, "y": tail_y,
                "vx": -ux * 20 + random.uniform(-12, 12),
                "vy": -uy * 20 + random.uniform(0, 25),
                "age": 0.0, "ttl": random.uniform(0.4, 0.8),
                "size": random.uniform(12, 20), "grow": 30.0,
                "rgb": (0.62, 0.66, 0.74)})
        del self._particles[:-C.PARTICLE_CAP]

    def _start_shake(self, magnitude):
        if self.app.settings.get("reduced_motion", False):
            self._shake = None
            self._shake_translate.x = 0
            self._shake_translate.y = 0
            return
        self._shake = {"mag": magnitude, "age": 0.0}

    def _update_shake(self, dt):
        if self._shake is None:
            return
        self._shake["age"] += dt
        progress = self._shake["age"] / C.SHAKE_TIME
        if progress >= 1.0:
            self._shake = None
            self._shake_translate.x = 0
            self._shake_translate.y = 0
            return
        strength = self._shake["mag"] * (1.0 - progress)
        self._shake_translate.x = random.uniform(-strength, strength)
        self._shake_translate.y = random.uniform(-strength, strength)

    # ------------------------------------------------------------------
    # Projectile drawing (instructions live in self._proj_group)
    # ------------------------------------------------------------------

    def _draw_projectile(self):
        """Create the canvas instructions for the projectile just fired."""
        p = self.projectile
        self._proj_group.clear()
        self._proj_ins = {}
        r, g, b = p.color[:3]
        if p.kind == "laser":
            glow = Line(points=[0, 0, 0, 0], width=C.LASER_WIDTH * 2.5)
            core = Line(points=[0, 0, 0, 0], width=C.LASER_WIDTH)
            glow_color = Color(r, g, b, 0.30)
            self._proj_group.add(glow_color)
            self._proj_group.add(glow)
            self._proj_group.add(Color(r, g, b, 1.0))
            self._proj_group.add(core)
            self._proj_ins["lines"] = (glow, core)
            self._proj_ins["glow_color"] = glow_color
            # Bright energy packets that flow along the beam.
            packet_tex = art.keyed_texture("fx_spark")
            packets = []
            for _ in range(3):
                self._proj_group.add(Color(r, g, b, 0.95))
                if packet_tex is not None:
                    rect = Rectangle(texture=packet_tex,
                                     pos=(-99, -99), size=(16, 16))
                else:
                    rect = Rectangle(pos=(-99, -99), size=(5, 5))
                self._proj_group.add(rect)
                packets.append(rect)
            self._proj_ins["packets"] = packets
            # A bright pulsing head, so the impulse has a visible "shot".
            head_tex = art.keyed_texture("fx_spark")
            if head_tex is not None:
                self._proj_group.add(Color(r, g, b, 0.95))
                head = Rectangle(texture=head_tex, pos=(-99, -99),
                                 size=(26, 26))
                self._proj_group.add(head)
                self._proj_ins["head"] = head
        else:
            radius = p.draw_radius
            glow = Ellipse(pos=(0, 0), size=(4 * radius, 4 * radius))
            self._proj_group.add(Color(r, g, b, 0.25))
            self._proj_group.add(glow)
            self._proj_ins["glow"] = glow
            # In flight the shot wears its weapon's art, rotated to the
            # flight direction, so the bullet and shell look like
            # what the player selected.
            sprite_tex = art.keyed_texture(_WEAPON_ICONS[p.kind])
            if sprite_tex is not None:
                size = 34 if p.kind == "bullet" else 46
                aspect = sprite_tex.size[0] / max(1.0, sprite_tex.size[1])
                sw = size if aspect >= 1 else size * aspect
                sh = size / aspect if aspect >= 1 else size
                rotate = Rotate(angle=0, origin=(0, 0))
                self._proj_group.add(PushMatrix())
                self._proj_group.add(rotate)
                self._proj_group.add(Color(1, 1, 1, 1))
                rect = Rectangle(texture=sprite_tex, pos=(0, 0),
                                 size=(sw, sh))
                self._proj_group.add(rect)
                self._proj_group.add(PopMatrix())
                self._proj_ins["rotate"] = rotate
                self._proj_ins["sprite"] = rect
            else:
                core = Ellipse(pos=(0, 0), size=(2 * radius, 2 * radius))
                self._proj_group.add(Color(r, g, b, 1.0))
                self._proj_group.add(core)
                self._proj_ins["core"] = core
        self._move_projectile()

    def _move_projectile(self):
        """Update the drawing to the projectile's current position."""
        p = self.projectile
        if p.kind == "laser":
            beam = p.beam_points()
            glow, core = self._proj_ins["lines"]
            glow.points = beam
            core.points = beam
            # The beam is alive: it pulses, and energy packets stream
            # from the tail toward the head.
            t = self._ambient_t
            pulse = 1.0 + 0.30 * math.sin(t * 26.0)
            core.width = max(1.0, C.LASER_WIDTH * pulse)
            glow.width = C.LASER_WIDTH * 2.6 * pulse
            self._proj_ins["glow_color"].a = 0.24 + 0.12 * math.sin(t * 26.0 + 1.3)
            for i, rect in enumerate(self._proj_ins["packets"]):
                frac = 1.0 - ((t * 1.8 + i / 3.0) % 1.0)
                px, py = _point_along(beam, frac)
                w, h = rect.size
                rect.pos = (px - w / 2, py - h / 2)
            if "head" in self._proj_ins:
                head = self._proj_ins["head"]
                pulse = 26 + 6 * math.sin(self._ambient_t * 30.0)
                head.size = (pulse, pulse)
                head.pos = (p.x - pulse / 2, p.y - pulse / 2)
        else:
            radius = p.draw_radius
            self._proj_ins["glow"].pos = (p.x - 2 * radius, p.y - 2 * radius)
            if "sprite" in self._proj_ins:
                rotate = self._proj_ins["rotate"]
                rotate.angle = math.degrees(math.atan2(p.vy, p.vx))
                rotate.origin = (p.x, p.y)
                sprite = self._proj_ins["sprite"]
                w, h = sprite.size
                sprite.pos = (p.x - w / 2, p.y - h / 2)
            else:
                self._proj_ins["core"].pos = (p.x - radius, p.y - radius)

    def _clear_projectile(self):
        self.projectile = None
        self._proj_group.clear()
        self._proj_ins = {}

    # ------------------------------------------------------------------
    # HUD
    # ------------------------------------------------------------------

    def _build_hud(self):
        """The cockpit: a turret-control panel with stat chips and a power
        bar, a weapon-chip row with icons, a mission box and a hint strip
        in the same visual language as the dialogue cards."""
        panel_x, panel_w, panel_h = 10, 330, 150
        panel_y = C.SCREEN_HEIGHT - 10 - panel_h
        chip_x, chip_w = panel_x + 12, panel_w - 24
        self._power_bar = (chip_x + 96, panel_y + 56, chip_w - 96 - 86, 6)

        self._cockpit = Widget()
        self.add_widget(self._cockpit)
        self._chip_bounds = []
        # These rectangles consume HUD clicks before they reach ``fire``.
        # Coordinates are in the 1280x720
        # design space, just like the rest of the game.
        self._hud_bounds = [
            (panel_x, panel_y - 68, panel_w, panel_h + 68),
            (C.SCREEN_WIDTH - 510, C.SCREEN_HEIGHT - 112, 500, 102),
            (0, 0, C.SCREEN_WIDTH, 44),
        ]
        self._chip_bg = []
        self._chip_border = []
        self._chip_icon_color = []
        with self._cockpit.canvas:
            # Turret-control panel.
            Color(0.03, 0.05, 0.11, 0.74)
            RoundedRectangle(pos=(panel_x, panel_y),
                             size=(panel_w, panel_h), radius=[12])
            Color(0.55, 0.85, 1.0, 0.30)
            Line(rounded_rectangle=(panel_x, panel_y, panel_w, panel_h, 12),
                 width=1.1)
            # Three stat chips inside it.
            Color(1, 1, 1, 0.06)
            RoundedRectangle(pos=(chip_x, panel_y + 80),
                             size=(chip_w, 32), radius=[7])
            RoundedRectangle(pos=(chip_x, panel_y + 44),
                             size=(chip_w, 32), radius=[7])
            RoundedRectangle(pos=(chip_x, panel_y + 8),
                             size=(chip_w, 32), radius=[7])
            # Power bar inside the POWER chip.
            bx, by, bw, bh = self._power_bar
            Color(1, 1, 1, 0.10)
            RoundedRectangle(pos=(bx, by), size=(bw, bh), radius=[3])
            self._power_color = Color(1, 0.85, 0.4, 0.9)
            self._power_fill = RoundedRectangle(pos=(bx, by), size=(6, bh),
                                                radius=[3])
            # Weapon chips under the panel.
            chip_row_y = panel_y - 68
            for i, kind in enumerate(PROJECTILE_TYPES):
                cx = panel_x + i * 68
                self._chip_bounds.append((cx, chip_row_y, 58, 58))
                bg = Color(0.03, 0.05, 0.11, 0.74)
                self._chip_bg.append(bg)
                RoundedRectangle(pos=(cx, chip_row_y), size=(58, 58),
                                 radius=[10])
                icon_color = Color(1, 1, 1, 1)
                self._chip_icon_color.append(icon_color)
                icon_tex = art.texture(_WEAPON_ICONS[kind])
                if icon_tex is not None:
                    aspect = icon_tex.size[0] / max(1.0, icon_tex.size[1])
                    iw = 48 if aspect >= 1 else 48 * aspect
                    ih = 48 / aspect if aspect >= 1 else 48
                    Rectangle(pos=(cx + 29 - iw / 2,
                                   chip_row_y + 29 - ih / 2),
                              size=(iw, ih), texture=icon_tex)
                else:
                    r, g, b = PROJECTILE_COLORS[kind][:3]
                    Color(r, g, b, 1)
                    Ellipse(pos=(cx + 17, chip_row_y + 17), size=(24, 24))
                border = Color(1, 1, 1, 0.2)
                self._chip_border.append(border)
                Line(rounded_rectangle=(cx, chip_row_y, 58, 58, 10),
                     width=1.4)
            # Mission card and ten-beacon progress rail, top right.
            Color(0.03, 0.05, 0.11, 0.74)
            RoundedRectangle(pos=(C.SCREEN_WIDTH - 510, C.SCREEN_HEIGHT - 112),
                             size=(500, 102), radius=[10])
            Color(0.55, 0.85, 1.0, 0.30)
            Line(rounded_rectangle=(C.SCREEN_WIDTH - 510,
                                    C.SCREEN_HEIGHT - 112, 500, 102, 10),
                 width=1.1)
            self._progress_colors = []
            self._progress_nodes = []
            for i in range(levels.level_count()):
                color = Color(1, 0.28, 0.24, 0.72)
                node = Ellipse(pos=(C.SCREEN_WIDTH - 482 + i * 45,
                                    C.SCREEN_HEIGHT - 102), size=(13, 13))
                self._progress_colors.append(color)
                self._progress_nodes.append(node)
            self._integrity_colors = []
            for i in range(3):
                color = Color(1.0, 0.40, 0.16, 0.0)
                self._integrity_colors.append(color)
                RoundedRectangle(pos=(1132 + i * 42, 610),
                                 size=(32, 5), radius=[2.5])
            # Result and briefing card.  Its alpha follows overlay text.
            self._overlay_bg_color = Color(0.02, 0.035, 0.08, 0)
            RoundedRectangle(pos=(300, 242), size=(680, 214), radius=[18])
            self._overlay_border_color = Color(0.55, 0.85, 1.0, 0)
            Line(rounded_rectangle=(300, 242, 680, 214, 18), width=1.5)
            # Contextual command bar: a single, opaque 44 px line.
            Color(0.008, 0.018, 0.045, 0.96)
            Rectangle(pos=(0, 0), size=(C.SCREEN_WIDTH, 44))
            Color(0.35, 0.72, 0.92, 0.30)
            Line(points=(0, 44, C.SCREEN_WIDTH, 44), width=1.0)

        def hud_label(text, x, y, w, h, size=14, halign="left",
                      font_name=FONT_BODY, **kw):
            label = Label(text=text, font_size=size, halign=halign,
                          font_name=font_name,
                          valign="middle", size_hint=(None, None),
                          size=(w, h), text_size=(w, h), pos=(x, y), **kw)
            self.add_widget(label)
            return label

        hud_label("TURRET CONTROL", chip_x, panel_y + panel_h - 34,
                  chip_w, 24, size=15, bold=True,
                  color=(0.62, 0.88, 1.0, 0.95))
        hud_label("ANGLE", chip_x + 10, panel_y + 80, 110, 32,
                  color=(1, 1, 1, 0.5))
        hud_label("POWER", chip_x + 10, panel_y + 44, 110, 32,
                  color=(1, 1, 1, 0.5))
        hud_label("PLASMA", chip_x + 10, panel_y + 8, 110, 32,
                  color=(1, 1, 1, 0.5))
        self._angle_value = hud_label("", chip_x + chip_w - 130,
                                      panel_y + 80, 120, 32, size=17,
                                      halign="right", bold=True,
                                      font_name=FONT_MONO,
                                      color=(0.94, 0.97, 1.0, 1.0))
        self._power_value = hud_label("", chip_x + chip_w - 90,
                                      panel_y + 44, 80, 32, size=17,
                                      halign="right", bold=True,
                                      font_name=FONT_MONO,
                                      color=(0.94, 0.97, 1.0, 1.0))
        self._plasma_value = hud_label("", chip_x + 92, panel_y + 8,
                                       chip_w - 102, 32, size=17,
                                       halign="right", bold=True,
                                       font_name=FONT_MONO,
                                       color=(0.94, 0.97, 1.0, 1.0))
        for i in range(3):
            cx, cy, _cw, _ch = self._chip_bounds[i]
            hud_label(str(i + 1), cx + 4, cy + 38, 16, 16, size=11,
                      color=(1, 1, 1, 0.55))

        self.mission_label = Label(
            text="",
            halign="right",
            valign="middle",
            font_size=17,
            font_name=FONT_DISPLAY,
            color=(0.62, 0.85, 1.0, 0.95),
            size_hint=(None, None),
            size=(470, 28),
            text_size=(470, 28),
            pos=(C.SCREEN_WIDTH - 495, C.SCREEN_HEIGHT - 43),
        )
        self.add_widget(self.mission_label)
        self.objective_label = Label(
            text="", halign="right", valign="middle",
            font_size=17, font_name=FONT_BODY,
            color=(0.94, 0.97, 1.0, 0.96),
            size_hint=(None, None), size=(470, 32), text_size=(470, 32),
            pos=(C.SCREEN_WIDTH - 495, C.SCREEN_HEIGHT - 74),
        )
        self.add_widget(self.objective_label)

        # Short transient messages ("GAME SAVED", ...) under the mission label.
        self.toast = Label(
            text="",
            halign="center",
            valign="middle",
            font_size=17,
            color=(1.0, 0.9, 0.5, 0.95),
            size_hint=(None, None),
            size=(460, 24),
            text_size=(460, 24),
            font_name=FONT_BODY,
            pos=(C.SCREEN_WIDTH / 2 - 230, C.SCREEN_HEIGHT - 132),
        )
        self.add_widget(self.toast)
        self._toast_event = None

        # Center-screen overlay for round-won messages.
        self.overlay = Label(
            markup=True,
            halign="center",
            valign="middle",
            font_size=26,
            font_name=FONT_DISPLAY,
            color=(1, 1, 1, 0.95),
            size_hint=(None, None),
            size=(640, 190),
            text_size=(620, 190),
            pos=(320, C.SCREEN_HEIGHT / 2 - 95),
        )
        self.add_widget(self.overlay)

        self._command_label = Label(
            text="",
            halign="center",
            valign="middle",
            font_size=17,
            font_name=FONT_MONO,
            color=(0.91, 0.96, 1, 0.92),
            size_hint=(None, None),
            size=(C.SCREEN_WIDTH, 44),
            text_size=(C.SCREEN_WIDTH - 24, 44),
            pos=(0, 0),
        )
        self.add_widget(self._command_label)

    def _refresh_hud(self):
        cannon = self.cannon
        vmin, vmax = cannon.velocity_range()
        self._angle_value.text = f"{cannon.angle:.1f}°"
        if cannon.projectile == "laser":
            self._power_value.text = "FIXED"
            fraction = 1.0
        else:
            self._power_value.text = f"{cannon.velocity:.0f}"
            fraction = (0.0 if vmax == vmin
                        else (cannon.velocity - vmin) / (vmax - vmin))
        bx, by, bw, bh = self._power_bar
        self._power_fill.pos = (bx, by)
        self._power_fill.size = (max(6.0, bw * fraction), bh)
        r, g, b = PROJECTILE_COLORS[cannon.projectile][:3]
        self._power_color.rgba = (r, g, b, 0.95)

        left = "MAX" if self.shots_left is None else str(self.shots_left)
        self._plasma_value.text = f"{left} LEFT / {self.shots_total} TOTAL"

        commands = {
            "briefing": "[SPACE] START LEVEL    [ESC] MENU",
            "aiming": ("[MOUSE] AIM   [WHEEL] POWER   [1|2|3] WEAPON   "
                       "[SPACE] FIRE   [S] SAVE   [L] LOAD   [ESC] MENU"),
            "flying": "SHOT IN FLIGHT    [ESC] MENU",
            "hit_pause": "TARGET IMPACT    [ESC] MENU",
            "phase_transition": "FOREMAN RECONFIGURING    [ESC] MENU",
            "failed": "[ENTER] RETRY    [ESC] MENU",
            "won": "[ENTER] CONTINUE    [ESC] MENU",
            "campaign_over": "[ENTER] COMPLETE MISSION    [ESC] MENU",
            "epilogue": "MISSION COMPLETE",
        }
        self._command_label.text = commands.get(self.state, "[ESC] MENU")

        # Weapon chips: bright frame on the selection, dimmed when the
        # story hasn't delivered a weapon yet.
        for i, kind in enumerate(PROJECTILE_TYPES):
            unlocked = kind in self.weapons
            selected = kind == cannon.projectile
            cr, cg, cb = PROJECTILE_COLORS[kind][:3]
            if not unlocked:
                self._chip_bg[i].rgba = (0.02, 0.03, 0.06, 0.55)
                self._chip_border[i].rgba = (1, 1, 1, 0.06)
                self._chip_icon_color[i].rgba = (1, 1, 1, 0.15)
            elif selected:
                self._chip_bg[i].rgba = (cr * 0.28, cg * 0.28, cb * 0.28, 0.94)
                self._chip_border[i].rgba = (cr, cg, cb, 0.95)
                self._chip_icon_color[i].rgba = (1, 1, 1, 1)
            else:
                self._chip_bg[i].rgba = (0.03, 0.05, 0.11, 0.74)
                self._chip_border[i].rgba = (1, 1, 1, 0.20)
                self._chip_icon_color[i].rgba = (1, 1, 1, 0.72)

        data = levels.LEVELS[self.level_index]
        phase = ""
        count = levels.phase_count(self.level_index)
        if count > 1:
            phase = f"  |  PHASE {self.phase + 1}/{count}"
        self.mission_label.text = (
            f"LEVEL {self.level_index + 1:02d}/{levels.level_count()}  |  "
            f"{data['name']}{phase}")
        self.objective_label.text = data["objective"]

        completed = self.level_index
        if self.state in ("won", "campaign_over", "epilogue"):
            completed += 1
        for i, color in enumerate(self._progress_colors):
            if i < completed:
                color.rgba = (0.22, 0.72, 0.82, 0.34)
            elif i == self.level_index and completed == self.level_index:
                pulse = 0.68 + 0.24 * math.sin(self._ambient_t * 5.0)
                accent = levels.PALETTES[data["palette"]]["accent"]
                color.rgba = (*accent, pulse)
            else:
                color.rgba = (1.0, 0.24, 0.20, 0.72)
        for index, color in enumerate(self._integrity_colors):
            if self.level_index != 9:
                color.rgba = (0, 0, 0, 0)
            elif index < self.phase:
                color.rgba = (0.18, 0.42, 0.48, 0.28)
            elif index == self.phase:
                pulse = (0.82 if self.app.settings.get("reduced_motion", False)
                         else 0.72 + 0.22 * math.sin(self._ambient_t * 5.0))
                color.rgba = (1.0, 0.56, 0.18, pulse)
            else:
                color.rgba = (0.88, 0.22, 0.16, 0.62)

    # ------------------------------------------------------------------
    # Screen lifecycle: bind input and start the loop only while visible
    # ------------------------------------------------------------------

    def on_pre_enter(self, *_args):
        self._visible = True
        self._space_held = False
        if hasattr(self.app.audio, "set_music_scene"):
            self.app.audio.set_music_scene(
                music_scene_for_level(self.level_index, self.phase))
        self._schedule_music_prefetch(self.level_index, self.phase)
        self._stars.start_twinkle()
        Window.bind(mouse_pos=self._on_mouse_pos,
                    on_key_down=self._on_key_down,
                    on_key_up=self._on_key_up)
        self._loop_event = Clock.schedule_interval(self._update, 1.0 / C.FPS)
        if self._briefing_pending is not None:
            lines, self._briefing_pending = self._briefing_pending, None
            self.dialogue.run(lines, self._player_name())

    def on_leave(self, *_args):
        self._visible = False
        self._space_held = False
        if self._music_prefetch_event is not None:
            self._music_prefetch_event.cancel()
            self._music_prefetch_event = None
        self._stars.stop_twinkle()
        Window.unbind(mouse_pos=self._on_mouse_pos,
                      on_key_down=self._on_key_down,
                      on_key_up=self._on_key_up)
        if self._loop_event is not None:
            self._loop_event.cancel()
            self._loop_event = None

    def _schedule_music_prefetch(self, index, phase):
        """Decode one future act/phase after the current frame is responsive."""
        if self._music_prefetch_event is not None:
            self._music_prefetch_event.cancel()
            self._music_prefetch_event = None
        scene = next_music_scene_to_prefetch(index, phase)
        if scene is None or not hasattr(self.app.audio, "preload_music_scene"):
            return

        def preload(_dt):
            self._music_prefetch_event = None
            if self.level_index == index and self.phase == phase:
                self.app.audio.preload_music_scene(scene)

        self._music_prefetch_event = Clock.schedule_once(preload, 0.35)

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _on_mouse_pos(self, _window, pos):
        # Window.mouse_pos uses window coordinates; the game lives in a
        # virtual SCREEN_WIDTH x SCREEN_HEIGHT space scaled by main.py,
        # so we convert the position back into design coordinates.
        if self.state != "aiming" or getattr(self.dialogue, "active", False):
            return False
        x, y = self.app.viewport.to_design(*pos)
        self._mouse_x = max(0.0, min(C.SCREEN_WIDTH, x))
        self.cannon.aim_at(x, y)
        return True

    def _on_key_up(self, _window, key, *_rest):
        """Re-arm Space only after a physical release."""
        if key == KEY_SPACE:
            self._space_held = False
            return True
        return False

    def _on_key_down(self, _window, key, _scancode, codepoint, _modifiers, *_rest):
        # Escape is navigation, not combat input, and remains available in
        # every state (including an active DialogueCard).
        if key == KEY_ESC:
            self.manager.current = "menu"
            return True

        if key == KEY_SPACE:
            if self._space_held:
                return True
            self._space_held = True

        if self.dialogue.active and key in (KEY_SPACE, KEY_ENTER,
                                            KEY_NUMPAD_ENTER):
            self.dialogue.advance()
            return True

        # Results have one intentional action; all combat controls remain
        # gated until a new level reaches briefing/aiming.
        if key in (KEY_ENTER, KEY_NUMPAD_ENTER):
            if self.state == "won":
                self._advance_after_result()
            elif self.state == "failed":
                self.start_level(self.level_index, retry=True)
            elif self.state == "campaign_over":
                self._finish_campaign()
            return True

        if self.state == "briefing":
            if key == KEY_SPACE:
                self._start_aiming()
                return True
            return (key in (KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN)
                    or codepoint in ("1", "2", "3", "s", "S", "l", "L"))

        if self.state != "aiming" or self.dialogue.active:
            # Consume known combat controls so no widget behind the game can
            # react while a projectile, pause or transition is active.
            return (key in (KEY_SPACE, KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN)
                    or codepoint in ("1", "2", "3", "s", "S", "l", "L"))

        if key == KEY_LEFT:
            self.cannon.nudge_angle(+C.ANGLE_STEP)
        elif key == KEY_RIGHT:
            self.cannon.nudge_angle(-C.ANGLE_STEP)
        elif key == KEY_UP:
            self.cannon.nudge_velocity(+C.VEL_STEP)
        elif key == KEY_DOWN:
            self.cannon.nudge_velocity(-C.VEL_STEP)
        elif codepoint in ("1", "2", "3"):
            self._try_select(PROJECTILE_TYPES[int(codepoint) - 1])
        elif codepoint in ("s", "S"):
            if "shift" in (_modifiers or ()):
                self.app.open_save_slots("save", return_screen="game")
            else:
                self.save_snapshot()
        elif codepoint in ("l", "L"):
            self.load_snapshot()
        elif key == KEY_SPACE:
            self.fire()
        else:
            return False  # not our key: let someone else handle it
        return True

    @staticmethod
    def _inside_bounds(x, y, bounds):
        bx, by, bw, bh = bounds
        return bx <= x <= bx + bw and by <= y <= by + bh

    def on_touch_down(self, touch):
        if self.dialogue.active:
            if not getattr(touch, "is_mouse_scrolling", False):
                self.dialogue.advance()
            return True
        scrolling = getattr(touch, "is_mouse_scrolling", False)

        # A plain click dismisses the briefing only.  A distinct subsequent
        # click in the arena is required to fire.
        if self.state == "briefing":
            if not scrolling:
                self._start_aiming()
            return True

        x, y = touch.x, touch.y
        if not (0 <= x <= C.SCREEN_WIDTH and 0 <= y <= C.SCREEN_HEIGHT):
            return True

        # Clicking a weapon chip selects that weapon (if delivered).
        for i, (cx, cy, cw, ch) in enumerate(self._chip_bounds):
            if self._inside_bounds(x, y, (cx, cy, cw, ch)):
                if self.state == "aiming" and not scrolling:
                    self._try_select(PROJECTILE_TYPES[i])
                return True
        # The scroll wheel arrives as a special "touch" in Kivy.
        if scrolling:
            if self.state != "aiming":
                return True
            if touch.button == "scrolldown":
                self.cannon.nudge_velocity(+C.VEL_STEP)
            elif touch.button == "scrollup":
                self.cannon.nudge_velocity(-C.VEL_STEP)
            return True
        if any(self._inside_bounds(x, y, bounds)
               for bounds in self._hud_bounds):
            return True
        if self.state == "aiming":
            self.fire()
        return True

    # ------------------------------------------------------------------
    # Game loop (Clock calls this FPS times per second)
    # ------------------------------------------------------------------

    def _update(self, dt):
        """Advance real elapsed time through bounded simulation substeps."""
        dt = max(0.0, min(float(dt), C.MAX_FRAME_DT))
        steps = max(1, int(math.ceil(dt / C.MAX_SIMULATION_STEP)))
        step_dt = dt / steps
        for _ in range(steps):
            self._simulation_step(step_dt)
        self._refresh_hud()

    def _simulation_step(self, dt):
        # Hide the result layer while a dialogue occupies the centre.
        overlay_visible = bool(self.overlay.text) and not self.dialogue.active
        self.overlay.opacity = 1.0 if overlay_visible else 0.0
        self._overlay_bg_color.a = 0.93 if overlay_visible else 0.0
        self._overlay_border_color.a = 0.55 if overlay_visible else 0.0
        self.cannon.refresh()
        if self.target is not None:
            self.target.refresh(dt)
        self._refresh_preview()
        self._refresh_boom(dt)
        self._update_particles(dt)
        self._update_shake(dt)
        self._update_backdrop(dt)

        if self.state == "hit_pause":
            self._hit_pause -= dt
            if self._hit_pause <= 0:
                if self.target is not None:
                    self.target.set_hit_flash(False)
                self._on_target_hit()
            return

        if self.state == "flying" and self.projectile is not None:
            p = self.projectile
            outcome = self._advance_projectile(p, dt)
            if outcome == "hit_target":
                self.last_shot_outcome = "target"
                self._begin_target_hit()
            elif outcome == "flying":
                if p.out_of_field():
                    self._clear_projectile()   # missed: shot lost, aim again
                    self.last_shot_outcome = "miss"
                    self.state = "aiming"
                else:
                    self._move_projectile()
                    self._emit_trail(p, dt)
            # "impacted": _impact_at already spent the shot

            # The last budgeted shot just resolved without a win?
            if self.state == "aiming" and self.shots_left == 0:
                self._on_level_failed()

    def _refresh_preview(self):
        """Draw an approximate flight indication with faint dots.

        The calculation uses the flight equations and shared field
        acceleration at a fixed 1/FPS time step. Dot sampling truncates the
        line near blocking geometry; reflections, teleports and target hits
        remain part of the runtime collision code rather than this preview.
        """
        if self.state != "aiming" or not self.app.settings.get("show_preview", True):
            self._preview_color.a = 0
            self._preview.points = []
            return
        mx, my = self.cannon.muzzle_pos()
        dx, dy = self.cannon.direction()
        speed = self.cannon.velocity
        is_laser = self.cannon.projectile == "laser"
        preview = levels.preview_config(self.level_index, self.phase)
        points = physics.simulate_trajectory(
            mx, my, dx * speed, dy * speed,
            massive=not is_laser,
            duration=preview.get("time", C.PREVIEW_TIME),
            dt=1.0 / C.FPS,
            samples=preview.get("dots", C.PREVIEW_DOTS),
            accel_fn=self._field_accel)   # the preview bends in anomalies too
        visible = []
        for i in range(0, len(points), 2):
            px, py = points[i], points[i + 1]
            blocked = any(
                ob.blocks_point(px, py) for ob in self.obstacles
                # lasers sail straight through elastonio panes
                if not (is_laser and ob.kind == "elastonio"))
            if blocked:
                break
            visible.extend((px, py))
        r, g, b = PROJECTILE_COLORS[self.cannon.projectile][:3]
        self._preview_color.rgba = (r, g, b, 0.35)
        self._preview.points = visible

    def _update_backdrop(self, dt):
        """Parallax: the backdrops shift a little against the aim, plus a
        slow ambient drift, so the belt feels alive behind the action."""
        self._ambient_t += dt
        if self.app.settings.get("reduced_motion", False):
            self._bg_far.pos = (-28, -16)
            self._bg_near.pos = (-48, -27)
            return
        t = self._ambient_t
        offset = (self._mouse_x / C.SCREEN_WIDTH - 0.5) * 2.0   # -1 .. 1
        self._bg_far.pos = (
            -28 - offset * C.PARALLAX_FAR + math.sin(t * 0.31) * 2.5,
            -16 + math.cos(t * 0.23) * 1.8)
        self._bg_near.pos = (
            -48 - offset * C.PARALLAX_NEAR + math.sin(t * 0.41 + 1.7) * 4.0,
            -27 + math.cos(t * 0.29 + 0.6) * 2.6)

    # ------------------------------------------------------------------
    # Toast (short transient message)
    # ------------------------------------------------------------------

    def _toast(self, text):
        self.toast.text = text
        if self._toast_event is not None:
            self._toast_event.cancel()
        self._toast_event = Clock.schedule_once(self._clear_toast, 1.8)

    def _clear_toast(self, _dt):
        self.toast.text = ""
        self._toast_event = None

    # ------------------------------------------------------------------
    # Explosion ring
    # ------------------------------------------------------------------

    def _start_boom(self, x, y, max_radius, rgb):
        self._boom = {"x": x, "y": y, "age": 0.0,
                      "max_r": max_radius, "rgb": rgb}

    def _refresh_boom(self, dt):
        """Animate the expanding impact/explosion ring."""
        if self._boom is None:
            return
        self._boom["age"] += dt
        progress = self._boom["age"] / 0.45
        if progress >= 1.0:
            self._boom = None
            self._boom_color.a = 0
            return
        r, g, b = self._boom["rgb"]
        self._boom_ring.circle = (self._boom["x"], self._boom["y"],
                                  8 + self._boom["max_r"] * progress)
        self._boom_color.rgba = (r, g, b, 0.9 * (1 - progress))
