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
