"""Where chapter notes live (no GTK, so it can be unit-tested)."""
from __future__ import annotations

import os
from pathlib import Path


def _from_user_dirs(home, key="XDG_DOCUMENTS_DIR"):
    """Read one entry from <home>/.config/user-dirs.dirs (xdg-user-dirs format)."""
    try:
        with open(Path(home) / ".config" / "user-dirs.dirs", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    value = line.split("=", 1)[1].strip().strip('"')
                    return Path(value.replace("$HOME", str(home)))
    except OSError:
        pass
    return None


def documents_dir(env=None, glib_documents=None):
    """The user's (possibly localized) Documents folder.

    Inside a strict snap HOME is the snap's private folder, so the real home
    from SNAP_REAL_HOME is used instead; otherwise GLib's answer.
    """
    env = os.environ if env is None else env
    real = env.get("SNAP_REAL_HOME")
    if real:
        return _from_user_dirs(real) or Path(real) / "Documents"
    if glib_documents:
        return Path(glib_documents)
    return Path.home() / "Documents"


def notes_root(env=None, glib_documents=None):
    return documents_dir(env, glib_documents) / "Notterizmus"


def data_dir(env=None):
    """The app's own data folder (inside a snap, XDG_DATA_HOME is the snap's own)."""
    env = os.environ if env is None else env
    base = env.get("XDG_DATA_HOME") or os.path.join(env.get("HOME") or str(Path.home()), ".local", "share")
    return Path(base) / "notterizmus"


def guide_path(env=None):
    """The Getting Started practice copy, kept in the app's data folder rather than
    among the user's notes."""
    return data_dir(env) / "Getting Started.notz"


def backups_dir(env=None):
    return data_dir(env) / "backups"


def metainfo_path(app_id, env=None):
    """The AppStream metainfo file: the source checkout's, else the installed one
    (found through XDG_DATA_DIRS, which also covers snaps)."""
    env = os.environ if env is None else env
    here = Path(__file__).resolve().parents[1] / "data" / f"{app_id}.metainfo.xml"
    if here.is_file():
        return here
    for d in (env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        p = Path(d) / "metainfo" / f"{app_id}.metainfo.xml"
        if d and p.is_file():
            return p
    return None


def latest_release(app_id, env=None):
    """(version, description markup) of the newest <release> in the metainfo."""
    import xml.etree.ElementTree as ET
    p = metainfo_path(app_id, env)
    if p is None:
        return None, ""
    try:
        rel = ET.parse(p).getroot().find("releases/release")
    except (ET.ParseError, OSError):  # a broken file: About shows no notes (CR27)
        return None, ""
    if rel is None:
        return None, ""
    desc = rel.find("description")
    markup = "" if desc is None else "".join(ET.tostring(c, encoding="unicode").strip() for c in desc)
    return rel.get("version"), markup
