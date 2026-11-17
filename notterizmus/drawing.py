"""Drawing blocks: an Excalidraw scene kept in the chapter file (no GTK).

A drawing node's data is the scene: {"elements": [...], "appState": {...}, "files": {...}},
exactly what Excalidraw itself saves, minus its view state. The picture shown in the
outline is not in the chapter file: it is a PNG in the app's cache folder, named by a
hash of the scene, and made again from the scene when it's missing.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

SCENE_KEYS = ("elements", "appState", "files")
# What a drawing keeps of Excalidraw's view state: only what changes how it looks
# (APP_STATE_KEYS in web/drawing/main.jsx, which saves the drawing window's scenes).
APP_STATE_KEYS = ("viewBackgroundColor", "gridSize", "gridStep", "gridModeEnabled")
PREVIEW_SCALE = 2      # the PNG has this many pixels per unit of the drawing
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
    canonical = json.dumps(scene(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


# --- preview cache -------------------------------------------------------------

def cache_dir(env=None):
    env = os.environ if env is None else env
    base = env.get("XDG_CACHE_HOME") or os.path.join(env.get("HOME") or str(Path.home()), ".cache")
    return Path(base) / "notterizmus" / "drawings"


def preview_path(data, env=None):
    return cache_dir(env) / f"{preview_key(data)}.png"


def store_preview(data, png, env=None):
    """Write a scene's PNG to the cache; returns its path, or None if it can't be written
    (the preview is then simply made again next time)."""
    path = preview_path(data, env)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(png)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        _prune(path.parent)
    except OSError:
        return None
    return path


def _prune(folder):
    files = []
    for p in folder.glob("*.png"):
        try:
            files.append((p.stat().st_mtime, p))
        except OSError:
            pass
    files.sort(reverse=True)
    for _mtime, p in files[CACHE_KEEP:]:
        try:
            p.unlink()
        except OSError:
            pass
