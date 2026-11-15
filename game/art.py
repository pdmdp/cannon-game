"""Story-art loading.

Textures are loaded once from assets/art/ and cached in memory. Anything
missing returns None. Callers can then use the corresponding canvas
drawing instead.

Sprites and parallax layers are generated on a pure black background;
keyed_texture() turns near-black pixels transparent. Because that is a
slow per-pixel pass in Python, the result can be cached on disk in
assets/art/.keyed/ and reused on later launches.
"""

import json
import hashlib
import os
import zlib

from kivy.core.image import Image as CoreImage
from kivy.graphics.texture import Texture

ART_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "art")
KEYED_CACHE_DIR = os.path.join(ART_DIR, ".keyed")
RUNTIME_DIR = os.path.join(ART_DIR, "runtime")
RUNTIME_MANIFEST = "asset_manifest.json"

# Damaged boss sprites are used only after the generated assets have passed
# the alpha, crop and alignment checks recorded in the runtime manifest.
STRICT_RUNTIME_ASSETS = {
    "sprite_foreman_core",
    "sprite_foreman_damaged",
    "sprite_foreman_critical",
    "sprite_warden_damaged",
}

_textures = {}
_manifest_signature = None
_manifest = None
_validation_cache = {}


def art_path(name):
    return os.path.join(ART_DIR, name + ".png")


def runtime_path(name):
    return os.path.join(RUNTIME_DIR, name + ".png")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _runtime_manifest():
    """Read the generated manifest, refreshing when the file changes."""
    global _manifest_signature, _manifest
    path = os.path.join(RUNTIME_DIR, RUNTIME_MANIFEST)
    try:
        stat = os.stat(path)
        signature = (stat.st_size, stat.st_mtime_ns)
    except OSError:
        signature = None
    if signature == _manifest_signature and _manifest is not None:
        return _manifest
    manifest = {}
    if signature is not None:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict) and isinstance(loaded.get("assets"), dict):
                manifest = loaded
        except (OSError, ValueError):
            manifest = {}
    _manifest_signature = signature
    _manifest = manifest
    _validation_cache.clear()
    return manifest


def runtime_asset_info(name):
    """Manifest record for ``name``, or None when it was not processed."""
    return _runtime_manifest().get("assets", {}).get(name)


def runtime_asset_valid(name):
    """Verify manifest validity, dimensions and both source/runtime hashes."""
    manifest = _runtime_manifest()
    if manifest.get("version") != 4:
        return False
    entry = manifest.get("assets", {}).get(name)
    source = art_path(name)
    built = runtime_path(name)
    if not isinstance(entry, dict) or not entry.get("valid"):
        return False
    if not os.path.exists(source) or not os.path.exists(built):
        return False
    try:
        source_stat = os.stat(source)
        runtime_stat = os.stat(built)
        signature = (source_stat.st_size, source_stat.st_mtime_ns,
                     runtime_stat.st_size, runtime_stat.st_mtime_ns,
                     entry.get("source_sha256"), entry.get("runtime_sha256"))
        cached = _validation_cache.get(name)
        if cached is not None and cached[0] == signature:
            return cached[1]
        valid = (_sha256(source) == entry.get("source_sha256")
                 and _sha256(built) == entry.get("runtime_sha256"))
        if name in STRICT_RUNTIME_ASSETS:
            valid = valid and entry.get("runtime_size") == [384, 384]
            valid = valid and bool(entry.get("runtime_has_alpha"))
        _validation_cache[name] = (signature, valid)
        return valid
    except OSError:
        return False


def has_art(name):
    if name in STRICT_RUNTIME_ASSETS:
        return runtime_asset_valid(name)
    return os.path.exists(runtime_path(name)) or os.path.exists(art_path(name))


def texture(name):
    """The texture for assets/art/<name>.png, or None if missing/broken."""
    if name in _textures:
        return _textures[name]
    tex = None
    if name in STRICT_RUNTIME_ASSETS:
        path = runtime_path(name) if runtime_asset_valid(name) else None
    else:
        path = runtime_path(name) if os.path.exists(runtime_path(name)) else art_path(name)
    if path is not None and os.path.exists(path):
        try:
            tex = CoreImage(path).texture
        except Exception:
            tex = None                 # a broken file must not crash the game
    _textures[name] = tex
    return tex


def _key_pixels(pixels):
    """Make near-black pixels transparent, with a soft edge ramp."""
    data = bytearray(pixels)
    for i in range(0, len(data), 4):
        brightness = max(data[i], data[i + 1], data[i + 2])
        if brightness < 24:
            data[i + 3] = 0
        elif brightness < 56:          # soft fringe so edges don't look cut
            data[i + 3] = min(data[i + 3], (brightness - 24) * 8)
    return bytes(data)


def keyed_texture(name):
    """Like texture(), but the black background becomes transparent.
    The processed pixels are cached in assets/art/.keyed/ after the
    first conversion so later launches can reuse them."""
    cache_key = name + "#keyed"
    if cache_key in _textures:
        return _textures[cache_key]

    # Offline-processed PNGs already carry the required alpha and crop. They
    # are the normal runtime path; dynamic keying handles missing versions.
    if (runtime_asset_valid(name) if name in STRICT_RUNTIME_ASSETS
            else os.path.exists(runtime_path(name))):
        tex = texture(name)
        _textures[cache_key] = tex
        return tex

    tex = None
    base = texture(name)
    if base is not None:
        width, height = int(base.size[0]), int(base.size[1])
        cache_file = os.path.join(KEYED_CACHE_DIR, name + ".rgba.z")
        meta_file = os.path.join(KEYED_CACHE_DIR, name + ".json")
        pixels = None
        stat = os.stat(art_path(name))
        signature = [stat.st_size, stat.st_mtime_ns]
        try:                            # fast path: the disk cache
            with open(meta_file, "r", encoding="utf-8") as handle:
                meta = json.load(handle)
            if (meta.get("size") == [width, height]
                    and meta.get("source_signature") == signature):
                with open(cache_file, "rb") as handle:
                    pixels = zlib.decompress(handle.read())
        except (OSError, ValueError):
            pixels = None
        if pixels is None:              # slow path: key now, cache for later
            pixels = _key_pixels(base.pixels)
            try:
                os.makedirs(KEYED_CACHE_DIR, exist_ok=True)
                with open(cache_file, "wb") as handle:
                    handle.write(zlib.compress(pixels, 6))
                with open(meta_file, "w", encoding="utf-8") as handle:
                    json.dump({"size": [width, height],
                               "source_signature": signature}, handle)
            except OSError:
                pass                    # cache is an optimization, not a need
        try:
            tex = Texture.create(size=(width, height), colorfmt="rgba")
            tex.blit_buffer(pixels, colorfmt="rgba", bufferfmt="ubyte")
        except Exception:
            tex = base

    _textures[cache_key] = tex
    return tex


def preload():
    """Load all processed runtime textures before entering gameplay."""
    if not os.path.isdir(RUNTIME_DIR):
        return
    for filename in sorted(os.listdir(RUNTIME_DIR)):
        if filename.lower().endswith(".png"):
            texture(os.path.splitext(filename)[0])


def clear_cache():
    """Forget textures and validation results after an offline rebuild."""
    global _manifest_signature, _manifest
    _textures.clear()
    _validation_cache.clear()
    _manifest_signature = None
    _manifest = None
