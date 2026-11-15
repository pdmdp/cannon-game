"""Validated, atomic JSON persistence for settings, scores and saves.

Runtime callers configure an application-owned data directory with
``configure``.  The module-level project paths remain only as a compatibility
fallback for the original assignment API. Once configured, storage does not
read JSON from the project root.
"""

from datetime import datetime, timezone
import json
import math
import os
import tempfile
import time

from game import constants as C

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.abspath(os.environ.get("CANNON_DATA_DIR", _PROJECT_ROOT))
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
SAVEGAME_FILE = os.path.join(DATA_DIR, "savegame.json")
HALL_OF_FAME_FILE = os.path.join(DATA_DIR, "hall_of_fame.json")
SAVE_SLOT_FILES = {
    slot: os.path.join(DATA_DIR, f"save_slot_{slot}.json")
    for slot in range(1, 4)
}

HALL_OF_FAME_SIZE = 20
SETTINGS_VERSION = 3
SAVE_VERSION = 3
CONTAINER_VERSION = 1
SAVE_SLOTS = (1, 2, 3)
DIFFICULTIES = ("easy", "normal", "hard")
PROJECTILES = ("bullet", "bombshell", "laser")

DEFAULT_SETTINGS = {
    "version": SETTINGS_VERSION,
    "profile_created": False,
    "intro_seen": False,
    "player_name": "GUNNER",
    "difficulty": "normal",
    "music_volume": 0.6,
    "sfx_volume": 0.8,
    "show_preview": C.SHOW_TRAJECTORY_PREVIEW,
    "instant_text": False,
    "reduced_motion": False,
}


def configure(data_dir=None):
    """Point every runtime file at one application-owned directory.

    ``CANNON_DATA_DIR`` has precedence when set, otherwise *data_dir* is
    used (normally Kivy's ``App.user_data_dir``). With neither value the
    existing directory is retained when the module is used before application
    configuration. No legacy file is copied or consulted during configuration.
    The selected absolute path is returned to the boot code.
    """
    global DATA_DIR, SETTINGS_FILE, SAVEGAME_FILE, HALL_OF_FAME_FILE
    global SAVE_SLOT_FILES

    configured = os.environ.get("CANNON_DATA_DIR")
    if not configured:
        configured = data_dir
    if configured is None:
        configured = DATA_DIR
    try:
        configured = os.path.abspath(os.path.expanduser(os.fspath(configured)))
    except TypeError:
        raise ValueError("data directory must be path-like") from None
    if not configured:
        raise ValueError("data directory must not be empty")

    DATA_DIR = configured
    SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
    SAVEGAME_FILE = os.path.join(DATA_DIR, "savegame.json")
    HALL_OF_FAME_FILE = os.path.join(DATA_DIR, "hall_of_fame.json")
    SAVE_SLOT_FILES = {
        slot: os.path.join(DATA_DIR, f"save_slot_{slot}.json")
        for slot in SAVE_SLOTS
    }
    return DATA_DIR


def _read_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return fallback


def _write_json(path, data):
    """Write JSON to a temporary file, then atomically replace *path*."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix="." + os.path.basename(path) + ".", suffix=".tmp",
        dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False,
                      allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _number(value, default):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    value = float(value)
    return value if math.isfinite(value) else default


def _clean_settings(data):
    if not isinstance(data, dict):
        data = {}
    name = data.get("player_name", DEFAULT_SETTINGS["player_name"])
    if not isinstance(name, str):
        name = DEFAULT_SETTINGS["player_name"]
    name = name.strip()[:32] or DEFAULT_SETTINGS["player_name"]
    difficulty = data.get("difficulty")
    if difficulty not in DIFFICULTIES:
        difficulty = DEFAULT_SETTINGS["difficulty"]
    music = min(1.0, max(0.0, _number(
        data.get("music_volume"), DEFAULT_SETTINGS["music_volume"])))
    sfx = min(1.0, max(0.0, _number(
        data.get("sfx_volume"), DEFAULT_SETTINGS["sfx_volume"])))
    # ``enlisted`` was the old first-run flag. Its meaning maps exactly to
    # a created profile and a completed intro in the old single-step flow.
    profile_created = data.get(
        "profile_created", data.get("enlisted", data.get("intro_seen", False)))
    intro_seen = data.get("intro_seen", data.get("enlisted", False))
    profile_created = (profile_created
                       if isinstance(profile_created, bool) else False)
    intro_seen = intro_seen if isinstance(intro_seen, bool) else False
    # A completed intro necessarily implies that enlistment already created
    # the profile; this also migrates the former settings schema safely.
    profile_created = profile_created or intro_seen
    return {
        "version": SETTINGS_VERSION,
        "profile_created": profile_created,
        "intro_seen": intro_seen,
        "player_name": name,
        "difficulty": difficulty,
        "music_volume": music,
        "sfx_volume": sfx,
        "show_preview": (data.get("show_preview")
                         if isinstance(data.get("show_preview"), bool)
                         else DEFAULT_SETTINGS["show_preview"]),
        "instant_text": (data.get("instant_text")
                         if isinstance(data.get("instant_text"), bool)
                         else DEFAULT_SETTINGS["instant_text"]),
        "reduced_motion": (data.get("reduced_motion")
                           if isinstance(data.get("reduced_motion"), bool)
                           else DEFAULT_SETTINGS["reduced_motion"]),
    }


def load_settings():
    return _clean_settings(_read_json(SETTINGS_FILE, {}))


def save_settings(settings):
    clean = _clean_settings(settings)
    settings.clear()
    settings.update(clean)
    _write_json(SETTINGS_FILE, clean)


def reset_profile(settings):
    """Reset first-run identity without touching saves, scores or options."""
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object")
    settings["profile_created"] = False
    settings["intro_seen"] = False
    settings["player_name"] = DEFAULT_SETTINGS["player_name"]
    save_settings(settings)
    return settings


def _clean_score(entry):
    if not isinstance(entry, dict):
        return None
    name, shots = entry.get("name"), entry.get("shots")
    if not isinstance(name, str) or isinstance(shots, bool):
        return None
    if not isinstance(shots, int) or shots < 0:
        return None
    date = entry.get("date", "")
    if not isinstance(date, str):
        date = ""
    return {"name": (name.strip()[:32] or "GUNNER"),
            "shots": shots, "date": date[:10]}


def load_hall_of_fame():
    data = _read_json(HALL_OF_FAME_FILE, [])
    entries = [] if not isinstance(data, list) else [
        clean for clean in (_clean_score(item) for item in data)
        if clean is not None]
    entries.sort(key=lambda entry: entry["shots"])
    return entries[:HALL_OF_FAME_SIZE]


def add_hall_of_fame_entry(name, shots):
    entry = _clean_score({"name": name, "shots": shots,
                          "date": time.strftime("%Y-%m-%d")})
    if entry is None:
        raise ValueError("invalid Hall of Fame entry")
    entries = load_hall_of_fame()
    entries.append(entry)
    entries.sort(key=lambda item: item["shots"])
    entries = entries[:HALL_OF_FAME_SIZE]
    _write_json(HALL_OF_FAME_FILE, entries)
    return entries.index(entry) + 1 if entry in entries else len(entries) + 1


def _non_negative_int(data, key, nullable=False):
    value = data.get(key)
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid {key}")
    return value


def validate_save(data):
    """Validate a v1-v3 snapshot, migrating v1 to the compatible v2 shape.

    ``campaign_difficulty`` is exposed for every accepted version so current
    campaign code has one stable read key. ``difficulty`` remains as a
    runtime compatibility alias. New v3 slot files persist only
    ``campaign_difficulty``.
    """
    if not isinstance(data, dict):
        raise ValueError("save is not an object")
    from game import levels  # local import keeps storage lightweight

    version = data.get("version", 1)
    if (isinstance(version, bool) or not isinstance(version, int)
            or version not in (1, 2, SAVE_VERSION)):
        raise ValueError(f"unsupported save version {version!r}")
    index = data.get("level_index")
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError("invalid level index")
    if not 0 <= index < levels.level_count():
        raise ValueError("level index out of range")
    phase = 0 if version == 1 else data.get("phase")
    if isinstance(phase, bool) or not isinstance(phase, int):
        raise ValueError("invalid boss phase")
    if not 0 <= phase < levels.phase_count(index):
        raise ValueError("boss phase out of range")
    if version < SAVE_VERSION:
        difficulty = data.get("difficulty")
    else:
        # Accept the transitional v3 alias used by early save files; new slot
        # files always write ``campaign_difficulty``.
        difficulty = data.get("campaign_difficulty", data.get("difficulty"))
    if difficulty not in DIFFICULTIES:
        raise ValueError("invalid campaign difficulty")

    cannon = data.get("cannon")
    if not isinstance(cannon, dict) or cannon.get("projectile") not in PROJECTILES:
        raise ValueError("invalid cannon")
    projectile = cannon["projectile"]
    if projectile not in levels.weapons_for(index):
        raise ValueError("saved projectile is not unlocked")
    angle = _number(cannon.get("angle"), None)
    velocity = _number(cannon.get("velocity"), None)
    if angle is None or not C.ANGLE_MIN <= angle <= C.ANGLE_MAX:
        raise ValueError("invalid cannon values")
    velocity_ranges = {
        "bullet": (C.MUZZLE_VEL_MIN, C.BULLET_VEL_MAX),
        "bombshell": (C.MUZZLE_VEL_MIN, C.BOMB_VEL_MAX),
        "laser": (C.LASER_VEL, C.LASER_VEL),
    }
    minimum, maximum = velocity_ranges[projectile]
    if (velocity is None or velocity < minimum - 1e-6
            or velocity > maximum + 1e-6):
        raise ValueError("invalid cannon velocity")

    target = data.get("target")
    if version == 1 and isinstance(target, (list, tuple)) and len(target) == 2:
        boss = levels.boss_info(index)
        target = {"x": target[0], "y": target[1],
                  "sprite": boss["sprite"] if boss else "sprite_beacon"}
    if not isinstance(target, dict):
        raise ValueError("invalid target")
    tx, ty = _number(target.get("x"), None), _number(target.get("y"), None)
    sprite = target.get("sprite")
    if tx is None or ty is None or not isinstance(sprite, str):
        raise ValueError("invalid target values")
    obstacles = data.get("obstacles")
    if not isinstance(obstacles, list) or not all(
            isinstance(obstacle, dict) for obstacle in obstacles):
        raise ValueError("invalid obstacles")
    from game.obstacles import obstacle_from_dict
    canonical_obstacles = []
    coordinate_keys = {
        "rock": ("x", "y"), "perpetio": ("x", "y"),
        "mirror": ("x1", "y1", "x2", "y2"),
        "elastonio": ("x1", "y1", "x2", "y2"),
        "wormhole": ("ax", "ay", "bx", "by"),
        "gravitonio": ("x", "y"),
    }
    for description in obstacles:
        kind = description.get("kind")
        if kind not in coordinate_keys:
            raise ValueError("unknown obstacle kind")
        if any(_number(description.get(key), None) is None
               for key in coordinate_keys[kind]):
            raise ValueError("invalid obstacle coordinates")
        if kind in ("rock", "perpetio"):
            cols, rows, cells = (description.get("cols"),
                                 description.get("rows"),
                                 description.get("cells"))
            if (isinstance(cols, bool) or isinstance(rows, bool)
                    or not isinstance(cols, int) or not isinstance(rows, int)
                    or cols <= 0 or rows <= 0 or not isinstance(cells, list)):
                raise ValueError("invalid obstacle grid")
            for cell in cells:
                if (not isinstance(cell, (list, tuple)) or len(cell) != 2
                        or not all(isinstance(value, int)
                                   and not isinstance(value, bool)
                                   for value in cell)
                        or not (0 <= cell[0] < cols and 0 <= cell[1] < rows)):
                    raise ValueError("invalid obstacle cell")
            if len(cells) != len({tuple(cell) for cell in cells}):
                raise ValueError("duplicate obstacle cell")
        if kind == "gravitonio" and not isinstance(
                description.get("repulsive"), bool):
            raise ValueError("invalid gravitonio polarity")
        try:
            canonical_obstacles.append(obstacle_from_dict(description).to_dict())
        except (KeyError, TypeError, ValueError):
            raise ValueError("invalid obstacle description") from None

    _validate_level_layout(levels, index, phase, tx, ty, sprite,
                           canonical_obstacles)

    shots_total = _non_negative_int(data, "shots_total")
    shots_round = _non_negative_int(data, "shots_round")
    shots_left = _non_negative_int(data, "shots_left", nullable=True)
    if shots_total < shots_round:
        raise ValueError("shots total is lower than shots this round")
    budget = levels.shot_budget(index, difficulty)
    if version == SAVE_VERSION:
        if budget is None and shots_left is not None:
            raise ValueError("unlimited campaigns cannot have shots left")
        if (budget is not None
                and (shots_left is None
                     or shots_round + shots_left != budget)):
            raise ValueError("saved shot budget is inconsistent")
    elif budget is not None:
        # Older snapshots counted boss-phase shots differently, so each
        # component is bounded independently while still accepting v1/v2.
        if (shots_left is None or shots_left > budget
                or shots_round > budget):
            raise ValueError("saved shot budget is inconsistent")

    clean = {
        "version": 2 if version < SAVE_VERSION else SAVE_VERSION,
        "level_index": index,
        "phase": phase,
        "campaign_difficulty": difficulty,
        # Temporary runtime alias; see the docstring above.
        "difficulty": difficulty,
        "shots_total": shots_total,
        "shots_round": shots_round,
        "shots_left": shots_left,
        "cannon": {"angle": angle, "velocity": velocity,
                   "projectile": projectile},
        "target": {"x": tx, "y": ty, "sprite": sprite},
        "obstacles": canonical_obstacles,
    }
    return clean


def _validate_level_layout(levels, index, phase, tx, ty, sprite, obstacles):
    """Reject a snapshot whose immutable scenario geometry was fabricated."""
    expected_obstacles, expected_target = levels.build_level(index, phase)
    expected_sprite = (levels.boss_info(index) or {}).get(
        "sprite", "sprite_beacon")
    expected_sprites = {expected_sprite}
    # Visual damage variants share the exact target centre/radius and are
    # legitimate phase-derived state, not user-controlled geometry.
    if index == 4 and phase > 0:
        expected_sprites.add("sprite_warden_damaged")
    if index == 9 and phase == 1:
        expected_sprites.add("sprite_foreman_damaged")
    if index == 9 and phase >= 2:
        expected_sprites.add("sprite_foreman_critical")
    if tx != expected_target[0] or ty != expected_target[1]:
        raise ValueError("saved target does not match level layout")
    if sprite not in expected_sprites:
        raise ValueError("saved target sprite does not match level")
    expected = [obstacle.to_dict() for obstacle in expected_obstacles]
    if len(obstacles) != len(expected):
        raise ValueError("saved obstacles do not match level layout")

    for current, original in zip(obstacles, expected):
        if current.get("kind") != original.get("kind"):
            raise ValueError("saved obstacle kind does not match level")
        kind = current["kind"]
        if kind in ("rock", "perpetio"):
            geometry = ("kind", "x", "y", "cols", "rows")
            if any(current.get(key) != original.get(key) for key in geometry):
                raise ValueError("saved obstacle grid does not match level")
            cells = {tuple(cell) for cell in current["cells"]}
            original_cells = {tuple(cell) for cell in original["cells"]}
            if kind == "rock" and not cells.issubset(original_cells):
                raise ValueError("saved rock cells exceed the level layout")
            if kind == "perpetio" and cells != original_cells:
                raise ValueError("saved perpetio must remain intact")
        elif current != original:
            raise ValueError("saved obstacle does not match level layout")


def _validate_slot(slot):
    if (isinstance(slot, bool) or not isinstance(slot, int)
            or slot not in SAVE_SLOTS):
        raise ValueError("slot must be 1, 2 or 3")
    return slot


def _snapshot_for_disk(snapshot):
    clean = dict(snapshot)
    if clean.get("version") == SAVE_VERSION:
        clean.pop("difficulty", None)
    return clean


def _clean_player_name(player_name):
    if not isinstance(player_name, str):
        raise ValueError("invalid player name")
    player_name = player_name.strip()
    if not player_name or len(player_name) > 32:
        raise ValueError("invalid player name")
    return player_name


def _utc_timestamp():
    return (datetime.now(timezone.utc).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z"))


def _validate_timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("invalid save timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise ValueError("invalid save timestamp") from None
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("save timestamp is not UTC")
    return value


def _validate_container(data, expected_slot):
    if not isinstance(data, dict):
        raise ValueError("save container is not an object")
    version = data.get("container_version")
    if (isinstance(version, bool) or not isinstance(version, int)
            or version != CONTAINER_VERSION):
        raise ValueError("unsupported save container")
    slot = _validate_slot(data.get("slot"))
    if slot != expected_slot:
        raise ValueError("save container is in the wrong slot")
    return {
        "container_version": CONTAINER_VERSION,
        "slot": slot,
        "saved_at": _validate_timestamp(data.get("saved_at")),
        "player_name": _clean_player_name(data.get("player_name")),
        "snapshot": validate_save(data.get("snapshot")),
    }


def save_game(snapshot, slot=None, player_name=None):
    """Persist a snapshot atomically.

    Passing a slot writes a version 1 container to one of the three slots.
    Omitting it preserves the assignment's original single-save wrapper.
    """
    clean = validate_save(snapshot)
    if slot is None:
        _write_json(SAVEGAME_FILE, clean)
        return clean

    slot = _validate_slot(slot)
    container = {
        "container_version": CONTAINER_VERSION,
        "slot": slot,
        "saved_at": _utc_timestamp(),
        "player_name": _clean_player_name(player_name),
        "snapshot": clean,
    }
    on_disk = dict(container)
    on_disk["snapshot"] = _snapshot_for_disk(clean)
    _write_json(SAVE_SLOT_FILES[slot], on_disk)
    return container


def load_game(slot=None):
    """Load a validated snapshot, or ``None`` for missing/corrupt data."""
    if slot is None:
        data = _read_json(SAVEGAME_FILE, None)
    else:
        slot = _validate_slot(slot)
        data = _read_json(SAVE_SLOT_FILES[slot], None)
    try:
        if slot is None:
            return validate_save(data)
        return _validate_container(data, slot)["snapshot"]
    except (KeyError, TypeError, ValueError):
        return None


def list_save_slots():
    """Return three stable metadata records with empty/valid/corrupt status."""
    records = []
    for slot in SAVE_SLOTS:
        path = SAVE_SLOT_FILES[slot]
        if not os.path.isfile(path):
            records.append({"slot": slot, "status": "empty"})
            continue
        data = _read_json(path, None)
        try:
            container = _validate_container(data, slot)
        except (KeyError, TypeError, ValueError):
            records.append({"slot": slot, "status": "corrupt"})
            continue
        snapshot = container["snapshot"]
        records.append({
            "slot": slot,
            "status": "valid",
            "saved_at": container["saved_at"],
            "player_name": container["player_name"],
            "level_index": snapshot["level_index"],
            "phase": snapshot["phase"],
            "campaign_difficulty": snapshot["campaign_difficulty"],
            "shots_total": snapshot["shots_total"],
        })
    return records


def delete_save(slot):
    """Delete one slot.  Return whether a file was actually removed."""
    slot = _validate_slot(slot)
    try:
        os.unlink(SAVE_SLOT_FILES[slot])
    except FileNotFoundError:
        return False
    return True


def has_save(slot=None):
    """Check one slot, or whether any current or legacy save is valid."""
    if slot is not None:
        return load_game(_validate_slot(slot)) is not None
    if any(load_game(candidate) is not None for candidate in SAVE_SLOTS):
        return True
    return load_game() is not None
