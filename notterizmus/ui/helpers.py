"""Small helpers shared by the UI modules (CR48 in CODE_REVIEW.md)."""
from __future__ import annotations

import logging
import weakref
from concurrent.futures import ThreadPoolExecutor

from gi.repository import GLib

from .. import paths, state

log = logging.getLogger(__name__)


def run_once(fn, *args):
    """Call fn(*args) and return GLib.SOURCE_REMOVE, so that a GLib.idle_add or
    GLib.timeout_add callback runs once: GLib.idle_add(run_once, entry.grab_focus)."""
    fn(*args)
    return GLib.SOURCE_REMOVE


def weak_handler(method):
    """A signal handler that calls `method` while its object lives, without keeping it
    alive: a widget's handler that held the widget itself would make a cycle through GTK
    that Python's garbage collector can't see (R29c)."""
    ref = weakref.WeakMethod(method)

    def handler(*args):
        m = ref()
        return None if m is None else m(*args)
    return handler


def let_go_when_closed(pop, *controllers):
    """When the popover closes, take it off its parent and take away its child and these
    controllers of ours: their handlers hold it, so it would never be freed."""
    ours = list(controllers)

    def closed(p):
        def later():
            p.unparent()
            for c in ours:
                p.remove_controller(c)
            ours.clear()  # and this handler holds them no more
            p.set_child(None)
        GLib.idle_add(run_once, later)
    pop.connect("closed", closed)


def set_class(widget, name, on):
    """Add the CSS class `name` to the widget when `on` is true, else remove it."""
    if on:
        widget.add_css_class(name)
    else:
        widget.remove_css_class(name)


def notes_root():
    return paths.notes_root(glib_documents=GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS))


def assessments_root():
    return paths.assessments_dir(glib_documents=GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS))


class Worker:
    """One thread for file work that shouldn't hold up the window (assessments: reading,
    parsing and writing their files). Jobs run one at a time, in the order they were
    given, so one job's writes are on disk before the next reads. A job must never touch
    GTK: its result, or its error, comes back on the main loop."""

    def __init__(self):
        self._pool = None
        self.pending = 0  # jobs given whose results haven't come back yet

    def run(self, job, done=None, failed=None):
        """Run job() on the thread, then done(its result) or failed(its exception) on the
        main loop. An exception without failed is raised there (and fails a UI test).
        Returns the job's Future, for the rare caller that must wait for it."""
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notterizmus-files")
        self.pending += 1
        future = self._pool.submit(job)
        future.add_done_callback(lambda f: GLib.idle_add(run_once, self._finished, f, done, failed))
        return future

    def _finished(self, future, done, failed):
        self.pending -= 1
        try:
            result = future.result()
        except Exception as e:
            if failed is None:
                raise
            failed(e)
            return
        if done is not None:
            done(result)

    def wait(self):
        """Block until every job given so far has run (not their done callbacks): before
        the app quits, so that drafts are on disk."""
        if self._pool is not None:
            self._pool.submit(lambda: None).result()


WORKER = Worker()


def load_state():
    return state.load()


def save_state(settings):
    try:
        state.save(settings)
    except OSError as e:  # not remembered this time; nothing else depends on it
        log.warning("can't save the settings: %s", e)
