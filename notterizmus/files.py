"""Writing a file in one step, so that it is never half written (no GTK)."""
from __future__ import annotations

import os
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def atomic_write(path, binary=False):
    """Yield a file for path's new content; when the block ends, it replaces path in one
    step. The content reaches the disk before the old file goes, and the folder's entry
    after, so a crash or power cut leaves the old file or the new one, never a mix or an
    empty file. The new file keeps the old one's permissions, and a new one gets the usual
    ones for the umask: mkstemp's 0600 made every save change a chapter's mode, which sync
    tools notice (CR25 in CODE_REVIEW.md). If the block fails, path stays as it was and no
    temporary file is left behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = None
    tmp = path.parent / f".{uuid.uuid4().hex[:12]}.tmp"  # hidden, and short: names have a byte limit
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)  # the kernel applies the umask
    try:
        try:
            if mode is not None:
                os.fchmod(fd, mode)
            f = os.fdopen(fd, "wb") if binary else os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise
        with f:
            yield f
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _sync_folder(path.parent)


def sync_folder(folder):
    """Make a rename in folder durable, as atomic_write does for the files it writes: for a
    folder renamed into place (an assessment's import)."""
    _sync_folder(folder)


def _sync_folder(folder):
    """Make the new name in folder durable. Some filesystems can't sync a folder; the
    file's content is on the disk by then anyway."""
    try:
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
