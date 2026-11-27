"""Drawing blocks: an Excalidraw scene kept in the chapter file (no GTK).

A drawing node's data is the scene: {"elements": [...], "appState": {...}, "files": {...}},
exactly what Excalidraw itself saves, minus its view state. The picture shown in the
outline is not in the chapter file: it is a PNG in the app's cache folder, named by a
hash of the scene, and made again from the scene when it's missing.
"""
from __future__ import annotations

import hashlib
import json
import logging

from . import paths
from .files import atomic_write

log = logging.getLogger(__name__)

SCENE_KEYS = ("elements", "appState", "files")
# What a drawing keeps of Excalidraw's view state: only what changes how it looks
# (APP_STATE_KEYS in web/drawing/main.jsx, which saves the drawing window's scenes).
APP_STATE_KEYS = ("viewBackgroundColor", "gridSize", "gridStep", "gridModeEnabled")
PREVIEW_SCALE = 2      # the PNG has this many pixels per unit of the drawing...
PREVIEW_MAX = (760, 600)  # ...up to the largest size the outline shows one at (larger ones are scaled down)
# The largest preview PNG. A larger drawing is exported smaller, at twice the size it is
# shown at; at twice its own size it made PNGs of 5000 px and more (R29b).
PREVIEW_PIXELS = (PREVIEW_MAX[0] * PREVIEW_SCALE, PREVIEW_MAX[1] * PREVIEW_SCALE)
PREVIEW_VERSION = 2    # raise it when previews are made differently: the cached ones are then made again
CACHE_KEEP = 300       # previews kept in the cache folder; the oldest go first
PLAIN_TEXT = "[Drawing]"


def new_data():
    return {"elements": [], "appState": {}, "files": {}}


def decode(d):
    """A node's data as read from a file. Parts of the wrong type become empty rather than
    refusing the whole chapter; fields this version doesn't know are kept."""
    d = d if isinstance(d, dict) else {}
    out = dict(d)
    elements = d.get("elements")
    out["elements"] = [e for e in elements if isinstance(e, dict)] if isinstance(elements, list) else []
    for k in ("appState", "files"):
        out[k] = d[k] if isinstance(d.get(k), dict) else {}
    return out


def encode(data):
    return {**new_data(), **data}


def scene(data):
    """Only the scene itself, in the order Excalidraw writes it."""
    return {"elements": data.get("elements") or [], "appState": data.get("appState") or {},
            "files": data.get("files") or {}}


def from_scene(value):
    """A drawing's data from a scene made elsewhere (in TopCoding's editor), as the
    drawing window would save it: erased elements, pictures no element shows and view
    state left out. `value` is the scene or its JSON text; None if it isn't a scene."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if not isinstance(value, dict) or not isinstance(value.get("elements"), list):
        return None
    elements = [e for e in value["elements"] if isinstance(e, dict) and not e.get("isDeleted")]
    app_state = value.get("appState") if isinstance(value.get("appState"), dict) else {}
    files = value.get("files") if isinstance(value.get("files"), dict) else {}
    shown = {e.get("fileId") for e in elements if e.get("type") == "image"}
    return {"elements": elements,
            "appState": {k: app_state[k] for k in APP_STATE_KEYS if app_state.get(k) is not None},
            "files": {k: v for k, v in files.items() if k in shown}}


def is_empty(data):
    return not any(not e.get("isDeleted") for e in data.get("elements") or [])


def scene_json(data):
    return json.dumps(scene(data), ensure_ascii=False, separators=(",", ":"))


def preview_key(data):
    """The name of a scene's preview in the cache: a hash of the scene and PREVIEW_VERSION
    (version 1, until R29b, hashed the scene alone)."""
    canonical = json.dumps(scene(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(f"{PREVIEW_VERSION}\n{canonical}".encode("utf-8")).hexdigest()


# --- preview cache -------------------------------------------------------------

def cache_dir(env=None):
    return paths.cache_dir(env) / "drawings"


def preview_path(data, env=None):
    return preview_file(preview_key(data), env)


def preview_file(key, env=None):
    """The preview for a key from preview_key(): hashing a scene with pictures is several
    MB of work, so a caller that has the key already passes it (CR35)."""
    return cache_dir(env) / f"{key}.png"


def store_preview(data, png, env=None):
    """Write a scene's PNG to the cache; returns its path, or None if it can't be written
    (the preview is then simply made again next time)."""
    path = preview_path(data, env)
    try:
        with atomic_write(path, binary=True) as f:
            f.write(png)
        _prune(path.parent)
    except OSError:
        return None
    return path


def _prune(folder):
    files = []
    for p in folder.glob("*.png"):
        try:
            files.append((p.stat().st_mtime, p))
        except OSError as e:  # gone already, most likely
            log.debug("preview cache: %s", e)
    files.sort(reverse=True)
    for _mtime, p in files[CACHE_KEEP:]:
        try:
            p.unlink()
        except OSError as e:
            log.debug("preview cache: can't remove %s: %s", p, e)
