# Work plan: open fixes and features

Written 2026-11-27 at `0601090` (1.8.1). It brings together everything still open:
the findings of [REVIEW.md](REVIEW.md) (the 1.7.0 review of 2026-11-24, none fixed
yet) and the open items of [ROADMAP.md](ROADMAP.md). The roadmap stays the record of
what each R-item is and why; this file is the order to do them in, and the boxes track
progress.

## IDs

- **R…**: roadmap items, as in ROADMAP.md. R35's follow-ups are numbered here as
  R35a–R35e.
- **RV…**: review findings. RV1–RV6 are REVIEW.md's critical issues C1–C6, and RV7 onward
  are findings from its sections 4 and "Product findings", which had no IDs. Commit
  messages name them as with CR, e.g. "Keep the window open when the last save fails
  (RV1)".
- **CR…**: CODE_REVIEW.md, all closed except the item under [With you](#with-you).

## Rules

The [rules for every fix](CODE_REVIEW.md#rules-for-every-fix) in CODE_REVIEW.md apply:
write the test first and see it fail, then fix; both suites pass after each fix
(`python3 -m unittest discover -s tests -t .` and `scripts/ui-tests.sh`); the load check
for anything that touches timing; a changed key or control goes into `guide.py`,
README.md, FEATURES.md and the Shortcuts dialog; one commit per item or group. Every
release follows the [release gate](CODE_REVIEW.md#release-gate). Anything tried on
TopCoding is tried in assignment 2522, chapter 999 only.

## Overview

| Phase | Theme | Items | Size | Release |
|---|---|---|---|---|
| 0 | With you: checks and decisions | 1.8.1 build, R32, decisions below | S | |
| 1 | Data safety | RV1–RV8, RV34 | M | 1.8.2, at once |
| 2 | Assessment practice follow-ups | R35a–R35e | M | 1.9.0 |
| 3 | Desktop basics and readable errors | RV6, RV9–RV15 | M | 1.9.0 |
| 4 | Speed of large chapters and the chapter list | RV16–RV20, R15 | M | 1.10.0 |
| 5 | Accessibility | RV21–RV24 | M | 1.10.0 |
| 6 | Richer notes | R7, R8, R9, R10, R11 | L | one release per item or two |
| 7 | Drawing polish | R30 | S–M | with phase 6 |
| 8 | Distribution and reach | R25, R26, R22, R19, R17, R18, R21, R20 | L | |
| 9 | Code health, no change in behaviour | RV25–RV33 | L | when convenient |
| 10 | Review assistant | R31 | L | after its spike |

Phases 1–5 come first because they fix what can lose notes, then what you asked for,
then what the review found broken. Phase 8's order is fixed by its own dependencies
(the new app ID before any store). Phases 6 and 8 can alternate.

---

## Phase 0: With you (S)

- [ ] Confirm on Launchpad that 1.8.1 built and that its log shows the unit tests ran.
- [ ] R32 (CR9): on the desktop, with nothing selected, Ctrl+I then typing gives italic,
  and Ctrl+B bold, with your input method, in the English and the Bulgarian layout.
- [ ] Decide what to keep of the untracked files: REVIEW.md (commit it, since this plan
  points into it) and `assessment_design_a_rate_limiter_2026-11-23.txt` (your report;
  keep it out of the repository).
- [ ] Decisions the later phases wait on; each has a default that is used if you'd
  rather not choose:
  - **Ctrl+W** (RV11): GNOME keeps it for Close; here it widens the selection. Default:
    keep it as it is.
  - **R30 polish**: paste a selection copied in Excalidraw as a new drawing, and/or copy
    a drawing as a PNG too. Default: neither, and R30 closes.
  - **R31**: provider and model (a cloud API or a local model), whether a paid key is
    acceptable, and what a review checks. Default: phase 10 waits.
  - **R20 translations**: before the course sees the app, or later. Default: with
    phase 8.
  - **Trashed chapters' versions** (RV6): move them to the Trash with the chapter, or
    ask. Default: move them, and undo brings them back.

## Phase 1: Data safety (M)

Nothing here changes how the app looks while saves work. Release as 1.8.2 as soon as it
is done.

- [x] **RV1 (C1)** Closing the window loses edits when the last save fails.
  `_on_close` (`ui/window_saving.py`) keeps the window open when its save fails, first
  writes the unsaved chapter to `<data dir>/unsaved/`, and asks **Retry**, **Save a
  Copy…** or **Quit Without Saving**. Ctrl+Q goes the same way, and the assessments
  window closes only once the answer is given. UI test: a read-only book folder, type,
  close; the window stays and the text is in `unsaved/`.
  Done 2026-11-27: `_on_close` and `_ask_unsaved` in `ui/window_saving.py`,
  `backups.keep_unsaved`, `paths.unsaved_dir()`. Tests: `tests/ui/test_unsaved.py` (8, all
  failed first), `UnsavedTest` in `tests/test_backups.py`. Not released.
- [x] **RV2 (C2)** A failed autosave is a 3-second toast. Keep a "not saved" state: an
  `Adw.Banner` with the chapter's name, the reason (`e.strerror`, not the temporary
  file's name) and **Retry**; a "•" before the title; retries at growing intervals; the
  banner goes on the next save that works. UI test for each.
  Done 2026-11-27: `_saved_state`, `save_banner` and `_retry_save` in
  `ui/window_saving.py`; `FailedAutosaveTest` in `tests/ui/test_unsaved.py`. Not released.
- [x] **RV34** (found while doing RV2) With the last autosave failed and none waiting,
  opening another chapter dropped the edits silently: `_save_pending` only flushed a
  waiting autosave. It now flushes while a save has failed too, and when that fails
  `set_doc` writes the chapter to the unsaved folder and says where. Test:
  `test_opening_another_chapter_writes_the_edits_aside_and_says_where` (failed first).
  Done 2026-11-27, not released.
- [x] **RV3 (C3)** Nothing is saved at logout, shutdown or SIGTERM, and the 800 ms
  debounce can wait for ever while you type. Save at most every 5 s while changes keep
  coming; `GLib.unix_signal_add` for SIGTERM, SIGINT and SIGHUP saves and quits;
  `register_session=True` and a save on `query-end`. Unit test for the maximum wait; UI
  test that sends SIGTERM to the harness's app.
  Done 2026-11-27: `SAVE_MAX_WAIT` (5 s) in `_schedule_save`; `App._quit_on_signal` and
  `query-end` call `Window.save_for_exit()`. Tests: `tests/ui/test_exit.py` (4, all failed
  first). Checked on the real app through `run()` in a private session: SIGTERM, SIGINT
  and SIGHUP each end it with status 0. Not released.
- [ ] **RV4 (C4)** "Keep Mine" can overwrite the other version when it can't be kept.
  When `backups.keep` fails, don't overwrite: write this version next to it as
  `NN Title (conflict YYYY-MM-DD).notz` and say so. The same for Reload. UI test with an
  unwritable data folder.
- [ ] **RV5 (C5)** `_after_move` reads the moved chapter unguarded
  (`ui/window_chapters.py:292`). Catch `OSError` and `ValueError`, keep the new path
  anyway and show a toast. Correct CODE_REVIEW.md's CR27 entry, which says this was
  done. UI test.
- [ ] **RV7** Logging: the `logging` module to stderr (journald), and the 13 silent
  `except …: pass` either log or, for backups (`_backup`, `backups.move`), log and show
  one toast per session that Earlier Versions isn't being kept.
- [ ] **RV8** Backup copies written atomically (`files.atomic_write` in place of
  `shutil.copy2` and `write_bytes` in `backups.py`), and stale `.<hex>.tmp` files older
  than a day removed from a book folder when it is scanned. Unit tests.
- [ ] The failure paths get tests (REVIEW.md §4.9): `window_saving.py`'s save, backup and
  reload failures, and `files.py`'s clean-up on failure.

## Phase 2: Assessment practice follow-ups (M)

What you asked for on 2026-11-26 first.

- [ ] **R35a** Spell checking in the answer editor: the editor's `richtext.Spelling`, in
  the chapter's language, with the same right-click suggestions. UI test.
- [ ] **R35b** The last score next to each question in the list, from your last finished
  attempt, without revealing the sample answer or the original score. UI test that the
  original score stays hidden until Reveal.
- [ ] **R35c** Remove an assessment from the app: a row action that moves its folder in
  `.assessments` to the Trash, with Undo. UI test.
- [ ] **R35d** A key of its own for the assessments window, in `commands.COMMANDS`,
  README, FEATURES, the guide and the Shortcuts dialog.
- [ ] **R35e** Drafts edited on two computers: merge per question (the newer text of each
  question wins, the other goes to the attempts) instead of keeping the whole other
  draft as an attempt. Unit test in `tests/test_assessments.py`.

## Phase 3: Desktop basics and readable errors (M)

- [ ] **RV6 (C6)** Trashed chapters' versions are kept for ever. Move a chapter's
  versions folder to the Trash with it (Undo brings both back), and add **Delete
  Versions** to Earlier Versions, with a confirmation.
- [ ] **RV9** Remember the window's size and maximized state in `state.json`.
- [ ] **RV10** F10 opens the main menu (`primary=True` on the menu button).
- [ ] **RV11** Ctrl+W: as decided in phase 0.
- [ ] **RV12** `state.json` in `$XDG_STATE_HOME/notterizmus` through a new
  `paths.state_dir()`, read from the old place once if the new one has none.
- [ ] **RV13** `GLib.set_prgname("notterizmus")` and an application name, so the desktop
  and screen readers name the app.
- [ ] **RV14** Errors in words: a file that isn't a chapter says so with its name,
  instead of the JSON parser's or the codec's message (full text to the log, RV7).
- [ ] **RV15** The dark-mode find highlight reaches 4.5:1 contrast with its text.

## Phase 4: Speed of large chapters and the chapter list (M)

Measure before and after with the review's chapters of 500, 2,000 and 4,000 items
(REVIEW.md §4.4, §4.7); record the numbers here as the earlier phases did. This also
closes **R15**: the review measured it (1.6 s to open 500 items).

- [ ] **RV16** Opening a chapter is O(n²): `size_new_views` measures the line height once
  from the editor (`create_pango_layout("Ag")` plus the views' margins) instead of
  looking for a realized view for every row.
- [ ] **RV17** Every window activation rescans the notes folder: watch it with
  `Gio.FileMonitor`, resolve the open chapter's path once, and compare
  `(st_dev, st_ino)` in `library.find` instead of `resolve()` per chapter.
- [ ] **RV18** Undo: snapshot at group boundaries only, not on each keystroke, and cap
  the history by size as well as by 500 steps.
- [ ] **RV19** A loading state (a spinner or a status page) while a chapter takes longer
  than about 0.3 s to open.
- [ ] **RV20** Restoring from the Trash enumerates `trash:///` on the main loop; do it on
  the existing background worker.
- [ ] The UI harness's `pump_until` checks its deadline inside the inner loop too, so a
  slow test fails instead of hanging (REVIEW.md §4.9).

A row list that is built lazily or uses `Gtk.ListView` (L) is left out: your largest
chapter has 192 items. Revisit if a chapter passes about 1,000.

## Phase 5: Accessibility (M)

- [ ] **RV21** Each item's text view is named by its number (`Ⅱ.1.a`), without the
  connector glyph.
- [ ] **RV22** Connector and spacer labels are hidden from screen readers.
- [ ] **RV23** The item menu opens with the Menu key and Shift+F10 as well as a click.
- [ ] **RV24** Check with Orca and Accerciser on the desktop; an AT-SPI test on the
  harness's display for RV21 and RV22.

## Phase 6: Richer notes (L)

In the roadmap's order. Each one touches the model, layout, export and paste, so each is
its own release or pair of releases.

- [ ] **R7** Line breaks inside an item (Shift+Enter), indented under the label with `│`
  where the tree continues, exported as `<br>`.
- [ ] **R8** Fold sections (click a label or Ctrl+.), saved per chapter, no effect on
  export.
- [ ] **R9** Search the book or all books: scan `.notz` files on the background worker,
  list hits by book and chapter, open the chapter at the match. (Also REVIEW.md's top
  product gap.)
- [ ] **R10** Drag an item by its prefix to move it or change its level.
- [ ] **R11** Spike, then build: Unicode spaces sized to Roboto's widths so `│` columns
  line up in TopCoding. Try it in assignment 2522, chapter 999.

## Phase 7: Drawing polish (S–M)

- [ ] **R30** What phase 0 decided: pasting an Excalidraw selection as a new drawing,
  and/or a PNG next to the scene when a drawing is copied. With neither, mark R30 done.

## Phase 8: Distribution and reach (L)

In this order; each needs the one before it.

- [ ] **R25** New app ID `dev.simo_andreev.notterizmus`, with `<replaces>` for the old
  one.
- [ ] **R26** A page on `simo-andreev.dev` with Flathub's verification file.
- [ ] **R22** CI on GitHub: the unit suite, the suite without PyGObject, lintian and the
  release checks; and confirm the Launchpad import. Add `pyproject.toml` with ruff
  settings here (RV25).
- [ ] **R19** Copy each release to 26.10 and newer series.
- [ ] **R17** The snap built by Launchpad and uploaded to the store (needs your store
  account).
- [ ] **R18** Screenshots and a feature list in the metainfo.
- [ ] **R21** Flathub: manifest, dictionaries, Documents access.
- [ ] **R20** gettext and a Bulgarian UI, including plural rules and language names
  (REVIEW.md "Localization"), unless phase 0 moved it earlier.

## Phase 9: Code health, no change in behaviour (L)

When convenient, a few at a time between features.

- [ ] **RV25** ruff in `pyproject.toml`; fix what it finds in the package and the tests
  (B023 closures in four UI test files).
- [ ] **RV26** mypy on the GTK-free modules, in CI.
- [ ] **RV27** Dead code: `drawing.SCENE_KEYS`; `Window.notes_root_path`, a test-only
  hook (move its use into the test).
- [ ] **RV28** SHA-1 for cache keys with `usedforsecurity=False`.
- [ ] **RV29** `style.css` named colours to libadwaita's CSS variables.
- [ ] **RV30** The drawing page's npm lockfile: update or drop the dependencies behind the
  12 audit advisories (none ship today), rebuild the page.
- [ ] **RV31** Fewer ticket IDs in code comments: keep the reason, drop the changelog.
- [ ] **RV32** The mixins' shared state declared as typed attributes on `OutlineEditor`
  and `Window`, so mypy can check them.
- [ ] **RV33** UI tests that depend on order: give the ones that write chapters their
  own book folder.

## Phase 10: Review assistant (L)

- [ ] **R31** Spike on the answers from phase 0: provider, where the key is kept, what is
  sent, cost. Then the panel, with each suggestion accepted as its own undo step.

## Not planned

From REVIEW.md, outside the app's scope as ROADMAP.md's "Not planned" sets it: tags and
pins, Markdown, attachments, built-in sync, import from other note apps, file export
other than Copy for TopCoding, right-to-left spelling.
