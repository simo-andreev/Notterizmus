# Notterizmus 1.7.0: critical review

Reviewed 2026-11-24 at `abb7e69` (`main`, clean tree). Covers all 45 Python modules
(9,344 lines), the packaging, the drawing page's build inputs and both test suites.
The generated Excalidraw bundle was checked only for which libraries ship in it.

**Method.** Read-only: this file is the only one written in the repo. Every tool ran on a
`git archive` copy in a scratch folder, from throwaway venvs: `venv-tools` for
ruff/mypy/bandit/vulture/pip-audit, and `venv-sys` (`--system-site-packages`) for the
tests, which need the distro's PyGObject. UI probes ran inside the project's own harness
on a private GTK Broadway display (headless Weston for the AT-SPI dump), with scratch
config, data and Documents folders. Your notes and your running copy of the app were not
touched.

**Labels.** **Verified** means I read the code or ran it, and the evidence is cited.
**Inferred** means reasoned from the code or from platform behaviour, not reproduced.

---

## 1. Verdict

Notterizmus isn't a general note-taking app. It's a single-user GNOME outliner for one
job: numbered, tree-drawn book-chapter notes that paste cleanly into TopCoding. The core
that does that job is careful work: atomic, fsynced saves; conflict detection against
sync tools; rollback-safe renames; a forward-compatible file format; automatic version
history; and 430 unit plus 284 real-input UI tests at 89% combined coverage. Against
modern desktop practice the UI layer falls short. It has no type hints, no logging, no
translations and no accessibility work, all its I/O runs on the main loop, and the editor
builds a text view per item and re-serializes the whole chapter on every keystroke.
Opening a chapter freezes the window for 1.6 s at 500 items, 7.7 s at 2,000 and 20 s at
4,000. One data-loss path is verified: when the final save fails (full disk, read-only folder),
closing the window discards the unsaved edits without asking. **Technical 6/10, product
5/10.** It's fit for daily use as-is for its author's TopCoding workflow at today's
chapter sizes (about 100 items, the largest 192: `ROADMAP.md:46`, `:122`), as long as "Save failed" toasts are heeded. It's not
fit as a general notes app, for large chapters, or for screen-reader users.

## 2. Scorecard

| Area | Score | One-line justification |
|---|---|---|
| **Technical overall** | **6/10** | |
| Architecture | 3/5 | The GTK-free core is cleanly separated and tested. The UI is two god objects split into 13 mixins that share about 100 undeclared attributes (mypy: 390 `attr-defined`). |
| Data integrity | 4/5 | Atomic fsynced writes, conflict check, rollback, forward compatibility and versions. A failed save on close loses edits, there's no session-end flush, and backup failures are silent. |
| Linux / XDG compliance | 4/5 | Config, data and cache come from `$XDG_*_HOME` through one module, notes go in the localized XDG Documents folder, and folders are created on demand. `state.json` belongs in `$XDG_STATE_HOME`. |
| GUI threading & responsiveness | 2/5 | There are no threads, so no thread misuse. Everything (fsync saves, folder scans, whole-chapter layout) runs on the main loop and scales super-linearly. |
| Error handling | 3/5 | Corrupt files and failed saves never crash and always show a toast. There's no logging, 13 silent `except …: pass`, raw Python error text in toasts, and failure is only ever a transient toast. |
| Security & privacy | 4/5 | No eval/pickle/shell, a sandboxed drawing page with a strict CSP, and the vulnerable npm packages aren't shipped. Notes are plaintext (normal for the category), and a trashed chapter's versions are kept forever. |
| Performance | 2/5 | Fine at about 150 items. Opening a chapter is O(n²), each keystroke is O(n), undo keeps up to 500 full-text snapshots, and the sidebar spends 0.7–0.95 s per window activation at 10k chapters. |
| Code quality | 3/5 | Consistent, documented, little dead code and no calls to nonexistent APIs. But 41 annotated lines in 9.3k, 547 mypy errors, no linter/formatter config and no CI. |
| Testing | 4/5 | 714 tests drive real modules with real input, coverage is 89%, and a run fails on any warning. The save-failure and close paths are untested, and the WebKit path is at 22% by default. |
| Packaging & distribution | 4/5 | The .deb is clean (lintian: 1 pedantic), the desktop file, metainfo, MIME type and icons are valid, and there's a PPA. No pyproject, the snap was never built, no Flatpak, one Ubuntu series. |
| AI-generation smells | 3/5 | One consistent style, which is unusual for vibe-coded apps. But comments double as a changelog (89 ticket references), a 97 KB self-review makes claims that have drifted from the code, and test hooks were left in. |
| **Product overall** | **5/10** | |
| Core loop | 4/5 | Launch reopens the last chapter, typing autosaves, and a new chapter is Ctrl+N plus one dialog. Old notes can only be found by browsing book → chapter. |
| Feature set | 2/5 | Deep outlining features (tables, drawings, versions, spelling, completion, multi-cursor). Missing note-app basics: search across chapters, tags/pins, sync, Markdown, attachments, file import/export. |
| Desktop integration | 3/5 | Idiomatic libadwaita, follows dark mode, adaptive split view, Trash, MIME type. No window-size memory, F10 and F6 do nothing, Ctrl+W is repurposed, no logout handling. |
| Edge cases & states | 3/5 | Good empty state; corrupt files and the 255-byte name limit are handled; Unicode renders. Failures are 3-second toasts, there's no loading state during multi-second opens, and RTL text is flagged as misspelled. |
| UX polish & consistency | 4/5 | Clean, native-looking and consistent in light and dark. Table toolbars are always visible, and error texts are raw exception strings. |
| Accessibility | 2/5 | GTK's defaults name the header buttons. Item text views have no name and no link to their number, connector glyphs and spacer lines are read out, and the item menu is mouse-only. |
| Localization | 1/5 | No gettext. The UI is English-only with English plural rules, next to GTK's own Bulgarian window controls for its bg_BG user. |
| Differentiation | 2/5 | Nothing else produces TopCoding chapter notes in this outline style. For anyone else, Obsidian, Joplin or Logseq do more. |

---

## 3. Critical issues

Anything that can lose data, crash, or leak data. No crash was found: the UI suite fails on
any exception raised in a callback and passed, and 9 kinds of corrupted chapter files all
ended in a toast (§4.5). No leak of note content was found (§4.6).

### C1. Closing the window discards edits when the final save fails (High, Verified)

- **Where:** `notterizmus/ui/window_saving.py:143-148` (`_on_close` always returns
  `False`, so the window closes) and `:72-77` (a failed save only shows a toast, on a
  window that is about to disappear). Ctrl+Q goes through the same path
  (`notterizmus/ui/app.py:50`).
- **What happens:** with the chapter's folder unwritable or the disk full, every autosave
  fails, and closing (window button, Ctrl+Q) runs one last save that fails too, then lets
  the window go. Everything typed since the last successful save is gone, with no prompt.
- **Reproduced:** in the probe, after `chmod 555` on the book folder and typing " EDITED",
  `_on_close` returned `False`. In memory the text was `'Before EDITED'`; on disk it was
  `'Before'`. The only signal was the toast
  `Save failed: [Errno 13] Отказан достъп: '…/ReadOnly/.c21875143543.tmp'`.
- **To reproduce by hand:** open a chapter, run `chmod a-w "<Documents>/Notterizmus/<Book>"`,
  type a word, press Ctrl+Q, restore the mode and reopen the chapter.
- **Fix:** if the save in `_on_close` fails, return `True` (keep the window open) and show
  an `Adw.AlertDialog` with **Retry**, **Save a Copy…** (`Gtk.FileDialog.save`) and
  **Quit Without Saving**. As a safety net, write the unsaved JSON to
  `$XDG_DATA_HOME/notterizmus/unsaved/` (or `$XDG_STATE_HOME`) before offering to discard.

### C2. Failed autosaves are a 3-second toast and nothing else (Medium, Verified)

- **Where:** `notterizmus/ui/window_saving.py:72-77`, `notterizmus/ui/window.py:270-276`
  (toast timeout 3 s). The error text comes from the temp file:
  `notterizmus/files.py:26-27`.
- **What happens:** each failed autosave shows one transient toast. The title, the header
  and the Save action don't change. In the probe the title stayed `'Chapter 1 — RO2 ·
  Notterizmus'` across two failures, and Save stayed enabled. Someone who looks away keeps
  typing into a chapter that isn't being saved, and C1 then loses it all at close. The
  message names a hidden temp file (`.d6b85efdfe83.tmp`), not the chapter, and mixes the
  OS's Bulgarian `strerror` into an English sentence.
- **Fix:** keep a "not saved" state. Show an `Adw.Banner` with the chapter path, the
  reason and **Retry**, prefix the title with "•", and retry with backoff. Report the
  chapter's path and `e.strerror`, not the temp file's.

### C3. No flush at logout, shutdown or SIGTERM; the debounce can postpone saving indefinitely (Medium, Inferred)

- **Where:** `notterizmus/ui/app.py:33-57`: no `register-session`, no `query-end`, no
  `GLib.unix_signal_add` (`grep -rn "unix_signal\|SIGTERM\|query-end\|register.session"
  notterizmus` finds nothing). `notterizmus/ui/window_saving.py:47-50` restarts the
  800 ms timer on every change and has no maximum wait.
- **What happens:** at logout or system shutdown the session kills the app (SIGTERM, or
  the display connection closes) without a `close-request`, so `_on_close` never runs and
  the pending autosave is dropped. Normally that's under a second of typing. During
  continuous typing with no 800 ms pause it's everything since the last pause.
- **Fix:** add `GLib.unix_signal_add(GLib.PRIORITY_HIGH, SIGTERM|SIGINT|SIGHUP, …)` that
  flushes and quits, set `register_session=True` and flush on `query-end`, and force a save
  at least every 5–10 s while changes keep arriving.

### C4. "Keep Mine" can overwrite another program's version without keeping it (Medium, Verified by reading)

- **Where:** `notterizmus/ui/window_saving.py:79-86` (an `OSError` from `backups.keep` is
  swallowed and the save proceeds), `:117` (the toast then says "the other version is in
  Earlier Versions" regardless), and `:130-134` (the same pattern in Reload).
- **What happens:** if the data folder can't be written (full, read-only, quota) while the
  notes folder can, a version that a sync tool or a second machine wrote is overwritten
  and not kept, and the user is told it was kept.
- **Fix:** if keeping the other version fails, don't overwrite. Save this version next to
  it as `NN Title (conflict <date>).notz` and say so.

### C5. A chapter that moved but can't be read back raises into GTK and can duplicate the chapter (Low, Verified by reading; consequence Inferred)

- **Where:** `notterizmus/ui/window_chapters.py:287`: `_after_move` calls
  `Document.load(new)` without a guard. The project's own review says this was fixed
  (`CODE_REVIEW.md:607-609`, CR27). It wasn't, here or in the CR27 commit `2ba6d5b`.
- **What happens:** the exception escapes the callback, so `doc.path` still names the
  removed file. The next autosave after an edit treats the missing file as unchanged
  (`model.py:478-485`) and writes the chapter back under its old name, which leaves two files for one chapter.
- **Fix:** wrap it in `except (OSError, ValueError)`, keep the new path anyway, and show a
  toast.

### C6. Trashed chapters live on in Earlier Versions forever (Low, privacy, Verified by reading)

- **Where:** `notterizmus/ui/window_chapters.py:331-346` (Trash doesn't touch backups) and
  `notterizmus/backups.py:23-28` (weekly copies are kept "for good").
- **What happens:** a chapter deleted to Trash, even after the Trash is emptied, survives
  as full copies under `~/.local/share/notterizmus/backups/<Book>/<chapter>/`. Nothing in
  the UI shows or removes them.
- **Fix:** when the Trash's Undo toast expires, either move the versions folder to Trash
  too or offer "Also delete earlier versions". Add a "Delete versions" action to the
  Earlier Versions dialog.

---

## 4. Findings by area

### 4.1 Architecture (3/5)

- **Medium, Verified.** The UI is two god objects. `OutlineEditor` is a
  `Gtk.ScrolledWindow` with 8 mixins (`notterizmus/ui/outline.py:57-58`), and `Window` is
  an `Adw.ApplicationWindow` with 5 (`notterizmus/ui/window.py:26`). The mixins share
  mutable state that's declared only in a docstring (`outline.py:1-33` lists who may
  change what) and isn't enforced. `mypy --check-untyped-defs` reports 390
  `attr-defined` errors, nearly all of the form "`WindowZoom` has no attribute `editor`".
  It's one object of about 100 attributes split across files, not modularity.
- **Low, Verified.** Module-level singletons: `completion._DICT_CACHE`
  (`completion.py:75`), `drawing_web._context` (`ui/drawing_web.py:47`, `global` at :83),
  and `window_zoom._ZOOM_PROVIDER` (`ui/window_zoom.py:50`, `global` at :54).
- **Good, Verified.** Domain and storage are separate from GTK: 18 modules (`model`,
  `layout`, `export`, `importer`, `library`, `backups`, `files`, `state`, …) import no GTK,
  and `tests/test_without_gtk.py` enforces that by re-running the unit suite with
  PyGObject blocked. One pattern is applied everywhere; nothing is half-migrated.

### 4.2 Data integrity (4/5)

The critical items are C1–C5. Further findings:

- **Good, Verified.** Saves are atomic and durable. `files.atomic_write`
  (`notterizmus/files.py:11-47`) writes a temp file in the same folder with `O_EXCL`,
  `fsync`s it, `os.replace`s it, then `fsync`s the folder, and keeps the old file's
  mode. Chapters (`model.py:464-471`) and `state.json` (`state.py:41-43`) both use it.
- **Good, Verified.** Conflicts with other writers are detected. Inode, mtime and size are
  remembered on load and save (`model.py:478-496`), and a mismatch asks Reload / Keep
  Mine (`ui/window_saving.py:88-106`). This is covered by `tests/ui/test_disk.py`.
- **Good, Verified.** Renumbering and reordering stage files under hidden names and roll
  back on any error (`library.py:203-262`). Files stranded by a crash are offered back at
  start-up (`library.py:265-286`, `ui/window_chapters.py:300-319`).
- **Good, Verified.** Format versioning is forward-compatible. `"format":
  "notterizmus/1"`, unknown kinds and unknown fields are all kept and written back
  unchanged (`model.py:159-209`, `:409-445`; `tests/test_unknown_blocks.py`). There are no
  migrations yet, and none are needed at format 1.
- **Good, Verified.** Single instance: `Adw.Application` is unique on D-Bus
  (`ui/app.py:35`, no `NON_UNIQUE`), so a second launch hands its files to the first. No
  file locks are needed on one machine.
- **Medium, Verified.** Backup failures are invisible. `_backup`
  (`ui/window_saving.py:26-29`) and `backups.move` after a rename
  (`ui/window_chapters.py:280-283`) swallow `OSError`, so Earlier Versions can stop working
  without the user ever knowing.
- **Low, Verified.** Backup copies aren't atomic (`backups.py:95` `shutil.copy2`, `:113`
  `write_bytes`). A crash mid-copy leaves a truncated "newest" copy, which the dialog shows
  as "can't be read" (`ui/versions.py:125-132`).
- **Low, Verified.** A crash between creating and replacing the temp file leaves a hidden
  `.<12 hex>.tmp` in the book folder that nothing ever cleans up (`files.py:26`, removed
  only on exception at :41-46).
- **Low, Verified.** A move is write-new-then-unlink-old (`library.py:132-134`). A crash
  between the two leaves two copies of the chapter rather than losing it, which is the
  right failure direction.
- **Low, Verified.** Undo history is dropped whenever a chapter is opened
  (`ui/outline.py:165-167`). Earlier Versions covers this, at 10-minute granularity
  (`backups.py:21`).

### 4.3 Linux / XDG compliance (4/5)

- **Good, Verified.** All base folders come from one module: `paths.py:42-67`
  (`$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, `$XDG_CACHE_HOME`, an empty value treated as
  unset, `$XDG_DATA_DIRS`). Notes go in the localized XDG Documents folder via GLib
  (`ui/helpers.py:54-55`, `paths.py:23-39`). That's correct for user-visible documents,
  and it's `~/Документи` on this machine. On first run the folders are made on demand
  (`files.py:21`, `ui/window_chapters.py:72`). Nothing is written next to the script.
- **Low, Verified.** `state.json` (last file, sidebar width, zoom) sits in the config folder
  (`state.py:18-19`). Since XDG Base Directory 0.8, that's `$XDG_STATE_HOME`
  (`~/.local/state`).
- **Low, Verified.** Files are created `0664` and folders `0775` under the default umask
  002 (probe P1c), so their privacy depends on the home folder being `0750`, as it is
  here.

### 4.4 GUI threading & responsiveness (2/5)

- **Good, Verified.** There are no threads (`grep` finds no `threading`, `asyncio` or
  `Gio.Task`), so GTK is never called from a worker thread.
- **High, Verified.** Opening a chapter is O(n²) in Python.
  `OutlineEditor.size_new_views` (`ui/outline.py:188-197`) scans `all_views()` for a
  realized view for each new row. During a load none is realized and `_line_h` stays 0,
  so each of the n rows scans all the rows before it. Profile of opening 1,000 items:
  508,507 generator steps in `all_views` (`ui/outline.py:200-202`) and 0.73 s in that
  scan alone. `refresh()` itself spends 1.09 s self time (`ui/outline.py:214-286`).
  Measured open-until-laid-out times on the test display: 250 items 0.98 s, 500 items
  1.6–1.7 s, 1,000 items 3.7 s (under the profiler), 2,000 items 7.7 s and 4,000 items
  20.2 s. At 2,000 and 4,000 items, 6.0 s and 17.5 s of that is the one synchronous
  `open_path` call, and at 4,000 items 4 of the 6 stack samples (one every 3 s) were in
  this scan (`ui/outline.py:192`, `:202`). The window is frozen throughout, with no busy
  state.
- **Medium, Verified.** Every window activation rescans the notes folder on the main loop:
  `notify::is-active` → `_reload_sidebar` (`ui/window.py:251`) → `library.scan` +
  `library.find`. `find` calls `Path.resolve()` twice per chapter (`library.py:67-82`).
  At 10,000 chapters in 100 books that's 94 ms (scan) + 627 ms (find) = 721 ms per
  activation in isolation, and 940–970 ms inside the app (probe P3). A full sidebar
  rebuild is another 812 ms.
- **Low, Verified.** The autosave runs `json.dumps(indent=1)` plus two `fsync`s on the
  main loop: 1.5 ms at 500 items, 31 ms at 10,000 items. Restoring a file from Trash
  enumerates the whole `trash:///` synchronously (`ui/window_chapters.py:368-386`).

### 4.5 Error handling (3/5)

- **Good, Verified.** Corrupt input never crashes. Probe P5 opened 9 broken files
  (truncated JSON, wrong types, empty, binary, 200,000-deep nesting, a non-object,
  `1e400`, invalid UTF-8, NUL in the title). Each one gave a toast and left the previous
  chapter open; nothing raised. The model turns every shape error into one `ValueError`
  (`model.py:444-445`, `:454-455`).
- **Medium, Verified.** There's no logging at all: no `logging` module, no `print` and no
  stderr writes in the package (`grep`). A failure the user dismissed or never saw leaves
  no trace for a bug report.
- **Medium, Verified.** 13 handlers silently `pass`. The ones that matter are around
  backups (`ui/window_saving.py:28`, `:85`, `:133`; `ui/window_chapters.py:282`), state
  (`ui/helpers.py:65`), the preview cache (`drawing.py:125`, `:131`) and the dictionary
  read (`completion.py:102`).
- **Low, Verified.** Toasts show raw exception text: "Expecting ',' delimiter: line 1
  column 81 (char 80)", "'utf-8' codec can't decode byte 0x80 in position 128" (probe P5).
- **Good, Verified.** Toasts that carry titles or errors use `use_markup=False`
  (`ui/window.py:271`), so "Q&A" no longer blanks a toast.

### 4.6 Security & privacy (4/5)

- **Good, Verified.** No `eval`, `exec`, `pickle`, `marshal`, `subprocess` or
  `shell=True` in the package (`grep`). Chapter files are plain JSON.
- **Good, Verified.** The Excalidraw page is well contained. It's served through the
  app's own URI scheme with a path-traversal check (`ui/drawing_web.py:54-68`, check at :59), from an
  ephemeral network session with downloads cancelled (`:91-92`); navigation outside the
  scheme is refused (`:107-118`); and the CSP is `default-src 'self'; script-src 'self';
  … frame-src 'none'; object-src 'none'` with no `unsafe-eval`
  (`notterizmus/drawing_web/index.html:6`).
- **Low, Verified.** `npm audit` on `web/drawing/package-lock.json` (with its project name
  anonymized) reports 12 advisories: 9 high, 1 moderate, 2 low. All come through
  mermaid, chevrotain, langium, lodash-es, katex or nanoid. Mermaid is aliased to a stub
  (`scripts/build-drawing-editor.sh:16`), and none of those libraries' marker strings
  appear in the 77 shipped chunks. Exposure is nil today, but the lockfile will keep
  failing audits.
- **Low, Verified.** The drawing page may read the clipboard without a user gesture
  (`ui/drawing_web.py:95`). The page is first-party code, so the risk is small.
- **Low, Verified.** Notes, backups and previews are unencrypted (normal for local note
  apps) and readable per the umask (§4.3). See also C6 for trashed chapters.
- **Info, Verified.** Bandit's 4 findings are false positives in context. SHA-1 is used
  for cache keys and folder names (`backups.py:59`, `drawing.py:88`; add
  `usedforsecurity=False`), and `xml.etree` parses the app's own metainfo file
  (`paths.py:100`).

### 4.7 Performance (2/5)

Scaling of the GTK-free core, measured on synthetic chapters (12 words per item;
`json.dumps` of the content, which is what `outline_undo._content` does for each
change):

| Chapter | File | Undo snapshot per change | Layout | HTML export | Save + fsync | Load | One snapshot in RAM | 500-step history |
|---|---|---|---|---|---|---|---|---|
| 500 items | 0.11 MB | 1.2 ms | 1.3 ms | 1.7 ms | 1.5 ms | 2.0 ms | 0.30 MB | ~150 MB |
| 2,000 items | 0.46 MB | 4.8 ms | 4.7 ms | 8.0 ms | 5.5 ms | 7.5 ms | 1.2 MB | ~600 MB |
| 10,000 items | 2.29 MB | 28 ms | 27 ms | 42 ms | 31 ms | 43 ms | 6.0 MB | ~3 GB |
| 1 item, 1.2 MB | 1.20 MB | 5.2 ms | 0.0 ms | 1.9 ms | 8.2 ms | 2.9 ms | 3.7 MB | ~1.8 GB |

(The RAM column includes one emoji per chapter, which makes CPython store every
character in 4 bytes. Plain Cyrillic text is about half that, ASCII about a quarter. The
project's own measurement of a real chapter is 31–32 KB per step: `ROADMAP.md:168`.)

- **High, Verified.** The chapter-open cost is in §4.4.
- **Medium, Verified.** Undo is whole-chapter text. Every committed change calls
  `_snapshot()`, which serializes the entire chapter (`ui/outline_undo.py:57-67`,
  `:69-87`). Each word typed is a new step (`:173-189`), and up to 500 steps are kept
  (`:80`). In the app, 100 word edits added 15 MB RSS in a 500-item chapter, 59 MB at
  2,000 items and 118 MB at 4,000 (probes P2, P10), so a full 500-step history of a
  4,000-item chapter would hold about 600 MB. The keystroke handler's median was 1.4 ms at
  500 items, 5.4 ms at 2,000 and 13.6 ms at 4,000 (max 19.6 ms, more than a 60 Hz frame).
  At 10,000 items the snapshot alone is 28 ms.
- **Medium, Verified.** Nothing is virtualized. The editor is a `Gtk.Box` of row widgets,
  one `GtkTextView` per item and per table cell (`ui/outline.py:71-73`). An open chapter costs
  about 150 KB of RAM per item: +84 MB at 500 items, +303 MB at 2,000 (413 MB in all), and
  722 MB in all with a 4,000-item chapter open. The sidebar is a `Gtk.ListBox` (`ui/sidebar.py:61`), which is
  tolerable only because collapsed books have no rows.
- **Medium, Verified.** Search is a linear scan, per chapter only. `find.find_all` runs a
  regex over each item (`find.py:18-21`), which is fine: 19.5 ms for 10,000 items. There's
  no index and no search across chapters (§Product).
- **Low, Verified.** Startup takes the same O(n²) path, because `Window.__init__` reopens
  the last chapter (`ui/window.py:60-62`) before anything is realized.

### 4.8 Code quality (3/5)

- **Medium, Verified.** Type hints are essentially absent: 41 annotated lines in 9,344.
  `mypy` (defaults) reports 4 errors. `mypy --check-untyped-defs` reports 547 in 33
  files: 390 `attr-defined` (the mixins), 67 `union-attr`. I spot-checked all 20
  `arg-type`, `call-arg`, `index` and `operator` hits; none was a real bug (they're
  walrus-name reuse, e.g. `ui/rows.py:226-231`, and Optional inference).
- **Medium, Verified.** There's no tooling config: no `pyproject.toml`, ruff, mypy,
  pre-commit or CI files. `ruff check` with defaults: 99 findings (43 in the package,
  none a bug; 18 are intentional `ISC004` in `guide.py`). `ruff format --check`: 90 of
  100 files would be reformatted.
- **Low, Verified.** Little dead code: vulture (≥60% confidence) lists 23 names, nearly
  all GTK vfuncs or `HTMLParser` callbacks. Real ones: `drawing.SCENE_KEYS`
  (`drawing.py:16`, unused) and `Window.notes_root_path` (`ui/window.py:379-381`, used
  only by `tests/ui/test_unknown.py:120`).
- **Good, Verified.** No calls to nonexistent or GTK 3 APIs. `mypy` with PyGObject-stubs
  2.20 found no missing attributes on GTK or libadwaita classes, and the UI suite fails on
  any GTK warning and passed.
- **Low, Inferred.** `style.css` uses libadwaita's named colours (`@accent_bg_color`,
  `ui/style.css:37`), which libadwaita 1.6+ supersedes with CSS variables
  (`var(--accent-bg-color)`).
- **Low, Verified.** Names are reused across types: `c` is a widget, then an int, in
  `ui/rows.py:226-231`. The style is otherwise readable, and the docstrings explain why,
  not what.

### 4.9 Testing (4/5)

- **Good, Verified.** `python3 -m unittest discover -s tests -t .`: 430 tests, OK, 35
  skipped, 6.0 s. `pytest --cov --cov-branch` on the unit tests: 430 passed, 63
  subtests; GTK-free modules at 81–99%. `scripts/ui-tests.sh`: 284 tests, OK, 7 skipped,
  180 s, run twice with identical results. Combined line and branch coverage: **89%**.
  The UI tests send real key and mouse events through Broadway (`tests/ui/broadway_input.py`)
  and fail on any callback exception or warning (`scripts/ui-tests.sh:103-119`, `PROJECT_CONTEXT.md:96`).
- **Medium, Verified.** The critical paths C1–C4 have no test. Coverage shows
  `ui/window_saving.py:76-77` (save failure), `:28-29`, `:85-86` and `:127-134` (backup
  and reload failures) never executed, and `files.py:33-35`, `:44-45` (cleanup on
  failure) uncovered.
- **Low, Verified.** `ui/drawing_web.py` is at 22% unless `NOTTERIZMUS_UI_WEBKIT=1`
  (7 tests skipped). The real-Excalidraw path is opt-in.
- **Low, Verified.** All UI tests share one app, one window and a notes folder that only
  grows (`PROJECT_CONTEXT.md:96`), so tests can couple through order.
- **Low, Verified.** Tests have lint debt: 19 B023 (closure over a loop variable) and
  F821 (name used after `del`) hits in 4 UI test files, e.g.
  `tests/ui/test_drawings.py:577-587` and `tests/ui/measure_drawings.py:395-457`. They work
  as written, but they're fragile.
- **Low, Verified (cause Inferred).** The UI harness can hang past its own timeouts.
  `pump_until` checks its deadline only when the main loop has nothing pending
  (`tests/ui/support.py:213-226`, inner loop at :221), and `settle()` measures every row
  after every frame (`:295-304`, `:317-320`). With a 2,000-item chapter,
  `settle(timeout=170)` never returned: the run hit the 10-minute watchdog inside that
  measuring (`point_in`, `:517-519`). The likely cause is that measuring 2,000 rows takes
  longer than a frame, so the loop never drains. A bounded loop timed the same chapter
  at 7.7 s (§4.4).

### 4.10 Packaging & distribution (4/5)

- **Good, Verified.** `dpkg-buildpackage -us -uc -b` builds `notterizmus_1.7.0_all.deb`
  (1.9 MB) in 11 s and runs the unit suite during the build. `lintian --pedantic`
  reports one pedantic tag (`repeated-path-segment`). `desktop-file-validate` is clean,
  and `appstreamcli validate` passes with 1 pedantic note. The package has a MIME type
  (`data/dev.simo.Notterizmus.mime.xml`), hicolor PNG icons from 16 to 512 px, and a man
  page. The PPA serves 1.7.0 (installed here).
- **Medium, Verified.** It isn't installable with pip and can't run from a plain venv.
  There's no `pyproject.toml` or `requirements.txt`, and
  `venv/bin/python -m notterizmus` fails with `ModuleNotFoundError: No module named 'gi'`.
  `pip install pygobject-stubs` (which pulls PyGObject) fails to build without the cairo
  dev headers. That's acceptable for a distro-packaged GNOME app, but the README's only
  dev route is the system `python3` (`notterizmus.sh`). The "no pip dependencies" design
  (`PROJECT_CONTEXT.md:10`) is honest about this.
- **Medium, Verified.** Reach is limited. The PPA builds only Ubuntu 26.04 (`README.md:31`).
  `snap/snapcraft.yaml` exists but has never been built (no snapcraft here, no CI;
  CODE_REVIEW CR30 says the same). There's no Flatpak manifest, and the icons have no
  scalable or symbolic variant.
- **Low, Verified.** The built Excalidraw page (5.6 MB, 77 chunks) is committed, because
  Launchpad builds have no network. Rebuilding it depends on the npm lockfile.

### 4.11 AI-generation smells (3/5)

- **Verified.** It is AI-generated: 88 of 90 commits carry `Co-Authored-By: Claude`, all
  made 2026-11-04 to 2026-11-20.
- **Medium, Verified.** The docs claim a fix the code doesn't have:
  `CODE_REVIEW.md:607-609` says CR27 made "a moved chapter that can't be read" give a
  toast, but the call is still unguarded (C5). Agents are told to trust this file
  (`PROJECT_CONTEXT.md`), so a wrong "done" spreads. One test-only hook of the kind CR44
  removed is still in the app: `Window.notes_root_path` (`ui/window.py:379-381`).
- **Low, Verified.** Comments double as a changelog: 89 references to review and roadmap
  IDs (`CR22`, `R29d`, …) inside the code. About 1,550 lines (171 KB) of process docs
  (`CODE_REVIEW.md`, `ROADMAP.md`, and `PROJECT_CONTEXT.md`, a 42 KB briefing for coding
  agents) sit beside 9.3k lines of code.
- **Low, Verified.** Contracts live in prose: who may mutate which attribute is a
  docstring (`ui/outline.py:1-33`), not types or ownership.
- **Not found.** No copy-pasted near-duplicate blocks stood out, no broad `except` that
  swallows errors (the four `except BaseException` clean up and re-raise: `files.py:33`,
  `:41`, `library.py:193`, `:231`), no nonexistent APIs, and no features wired up but
  unreachable (48 of the 50 commands are in Search Commands; the other two, Search
  Commands and Quit, have Ctrl+Shift+P and Ctrl+Q: `commands.py:139-140`).

### Product findings

- **Core loop (4/5), Verified.** On launch the last chapter reopens (`ui/window.py:60-62`)
  with the cursor in it, and typing autosaves 800 ms later. A new chapter is Ctrl+N, then
  Book, Number and Title, then Create (`ui/window_chapters.py:19-67`): two steps. To find
  an old note you open the sidebar (F9), expand the book and click the chapter. There's no
  search across chapters, so "where did I write X" means opening chapters one by one and
  pressing Ctrl+F (`ui/findbar.py:134-144` searches only the open chapter).
- **Feature set (2/5), Verified.** Compared with Joplin, Obsidian, Standard Notes,
  Simplenote and GNOME Text Editor:

  | Feature | Here |
  |---|---|
  | Search | Within the open chapter only (find and replace, case, whole word) |
  | Organization | Fixed Book → Chapter. No tags, pins or nested folders |
  | Markup | Bold and italic only. No Markdown, links, code blocks or checklists |
  | Rich blocks | Tables and Excalidraw drawings |
  | Attachments | None |
  | Sync | Delegated to external tools, with conflict detection |
  | Import / export | Paste in; "Copy for TopCoding" HTML and plain-text view out. No file export (Markdown/PDF/HTML) or import (Joplin/Obsidian) |
  | Trash / undo | Chapter → system Trash with Undo; 500-step session undo; Earlier Versions |

  The niche extras (multi-cursor, Ctrl+W scope selection, Search Commands, a paste parser
  for hand-written outlines) are polished but serve one workflow.
- **Desktop integration (3/5).**
  - Good, Verified: `Adw.Application`, `Adw.OverlaySplitView` with a breakpoint,
    `Adw.AlertDialog`, toasts, `Adw.AboutDialog`, `Adw.ShortcutsDialog`. Dark and light
    both render correctly (screenshots under forced light and dark schemes). Colours are
    theme-relative except the two find highlights. Files go to Trash through GIO, and
    `.notz` has a MIME type.
  - Medium, Verified: the window size and maximized state aren't remembered
    (`ui/window.py:36` constants; `state.py:14-15` keeps neither).
  - Medium, Verified: F10 doesn't open the primary menu (the `MenuButton` lacks
    `primary=True`, `ui/window.py:112`; probe P6: no popover), and F6 does nothing.
  - Low, Verified: Ctrl+W, which GNOME HIG reserves for close, expands the selection
    (`commands.py:128`).
  - Low, Inferred: Ctrl+Space can collide with input-method switching on some setups.
  - HiDPI and Wayland: see §7.
- **Edge cases & states (3/5).**
  - Good, Verified: the empty state is an `Adw.StatusPage` with New Chapter, Open… and
    Getting Started (`ui/window.py:157-174`).
  - Good, Verified: a 479-character Cyrillic title is cut to a 255-byte file name, and the
    full title is kept inside the file (probe P4).
  - Good, Verified: emoji, ZWJ sequences, combining marks and CJK render. Arabic and
    Hebrew words are spell-checked against English and all underlined
    (`spell.py:33-38` knows only Latin and Cyrillic).
  - No loading state while a big chapter opens (§4.4); read-only or full disk is C1/C2.
- **UX polish (4/5), Verified.** Native-looking and consistent in both schemes, with
  sensible spacing and a clear hierarchy. Weak spots: each table carries a permanently
  visible "+ Row / + Column / – Row / – Column / Header row / 🗑" toolbar. In dark mode the
  current-match highlight `rgba(255,120,0,0.75)` (`ui/richtext.py:41-42`) with white text
  is about 4.0:1, under the WCAG AA 4.5:1 (computed). Errors read as Python exceptions.
- **Accessibility (2/5).** AT-SPI dump on headless Weston, Verified:
  - Icon-only header buttons get names from their tooltips ("Chapters (F9)", "New chapter
    (Ctrl+N)", "Menu").
  - Each item's text view is `[text] name=''`. Its number is a separate
    `[label] name='└ Ⅰ.1) '` with the connector glyph inside it, and every spacer line is
    a `[label] name='│'`. An Orca user hears no structure when moving between items, and
    hears box-drawing characters when reading by object.
  - The item menu opens only by clicking the label (`ui/rows.py:112-118`, a `GestureClick`
    on a non-focusable `Gtk.Label`). There are keyboard equivalents (Ctrl+Shift+Space,
    Alt+Insert).
  - Ctrl+Tab does leave the editor for the chapter list (probe P6).
  - No program name is set (no `GLib.set_prgname`), and GTK reports the program name to
    AT-SPI as the application's name. In the harness, which never calls `run()`, that was
    `'Unnamed'`. A normal launch (`python3 -m notterizmus`, `ui/app.py:102-103`) would make
    it `__main__.py` (Inferred).
  - The package makes no accessibility API calls at all (`grep` finds no
    `update_property`, `update_relation` or `AccessibleRole`).
- **Localization (1/5), Verified.** No gettext (`grep`). Every string is an English
  literal, e.g. `ui/window.py:159-161`. English plural logic is hard-coded
  (`ui/versions.py:132`), and language names come from a hand-written English table
  (`spell.py:13-20`). Dates in Earlier Versions are ISO with "Today" and "Yesterday"
  (`ui/versions.py:116-122`). The main user's locale is `bg_BG` (`PROJECT_CONTEXT.md:6`),
  so GTK's own controls are Bulgarian ("Минимизиране") while the app is English.
- **Differentiation (2/5).** If your notes end up in TopCoding's Lexical editor, this is
  the only tool that generates the numbering and tree connectors and round-trips tables
  and drawings through TopCoding's clipboard format. That's a real reason, for one
  audience. For anyone else, Obsidian (an outliner plugin plus search, links and sync),
  Joplin (sync, E2EE, Markdown, web clipper) or Logseq (a native outliner) do more, on
  more platforms, with search across notes.

---

## 5. What's actually good

Each item is Verified, with its evidence:

1. **The save path is correct.** It's temp file, fsync, `os.replace`, then fsync of the
   folder, with the file's mode kept and cleanup on failure (`files.py:11-62`). Many
   commercial apps don't do this.
2. **It detects external changes** and asks instead of clobbering, keeping the other
   version in history (`model.py:478-496`, `ui/window_saving.py:57-141`,
   `tests/ui/test_disk.py`).
3. **Multi-file renames are rollback-safe**, and files stranded by a crash are recovered
   at start-up (`library.py:167-286`, `ui/window_chapters.py:300-319`).
4. **The file format is forward-compatible.** Unknown blocks and fields survive a
   load-edit-save cycle (`model.py:159-209`, `tests/test_unknown_blocks.py`).
5. **Version history works.** Copies are taken on open and every 10 minutes and thinned
   by age, with preview and one-step Restore (`backups.py`, `ui/versions.py`).
6. **Malformed input is handled.** Nine kinds of corrupt files never crash (probe P5);
   the clipboard and rules.toml parsers are guarded too (`tests/test_rules.py`,
   `tests/test_drawing.py`).
7. **The test suite is real.** 714 tests exercise real code with real input events, reach
   89% coverage, and fail on warnings.
8. **The core is layered.** GTK-free core modules are enforced by a test
   (`tests/test_without_gtk.py`).
9. **Packaging is clean.** The .deb builds in 11 s with tests and lints clean; the
   desktop file, metainfo and MIME definition are valid; there's a man page and a PPA.
10. **The embedded web page is contained.** Own scheme, path check, ephemeral session,
    navigation blocked, strict CSP (§4.6).
11. **libadwaita is used idiomatically**, with theme-relative CSS, so dark mode works
    without any special cases.

---

## 6. Top 10 actions

Ordered by impact per effort. S = under a day, M = a few days, L = a week or more.

| # | Action | Fixes | Size |
|---|---|---|---|
| 1 | Make close refuse to lose data: when `_on_close`'s save fails, keep the window and ask Retry / Save a Copy… / Quit Without Saving; write an emergency copy first. Add the missing UI test with a read-only folder. | C1 | S |
| 2 | Give save failures a persistent state: an `Adw.Banner` with the chapter path, the reason and Retry, a "•" title marker, retry with backoff. Error text should name the chapter, not `.xxxx.tmp`. | C2 | S |
| 3 | Flush on SIGTERM/SIGINT/SIGHUP (`GLib.unix_signal_add`) and on session `query-end` (`register_session=True`), and add a max-wait (5–10 s) to the 800 ms debounce. | C3 | S |
| 4 | Remove the O(n²) in `size_new_views`: measure the line height once from the editor itself (`self.create_pango_layout("Ag")` plus the views' margins) instead of hunting for a realized view per row. | §4.4 | S |
| 5 | Stop rescanning on every focus: watch the notes folder with `Gio.FileMonitor` (or compare folder mtimes), resolve the open chapter's path once, and compare `(st_dev, st_ino)` in `library.find`. | §4.4 | S |
| 6 | Add `logging` (stderr, which reaches journald), replace the silent backup `except OSError: pass` with a logged warning plus a one-time toast, refuse "Keep Mine" when the other version can't be kept, and guard `_after_move`. | C4, C5, §4.5 | S |
| 7 | Desktop basics: remember window size and maximized state, `primary=True` on the main menu (F10), and give Ctrl+W back to close or leave it unbound; move `state.json` to `$XDG_STATE_HOME` with a fallback read. | §Product | S |
| 8 | Accessibility pass: name each item's text view with its number (`update_relation(LABELLED_BY, …)` or `update_property(LABEL, "Ⅱ.1.a")`), hide connector and spacer labels from AT, make the item menu reachable by the Menu key or Shift+F10, set a program name (`GLib.set_prgname`), and check with Orca and Accerciser. | §Accessibility | M |
| 9 | Search across chapters: scan `.notz` files in a `Gio.Task` worker, list hits by book and chapter, and open at the match. It's the biggest product gap for finding old notes. | §Feature set | M |
| 10 | Cheaper undo: snapshot only at group boundaries (mark dirty per keystroke), share unchanged subtrees between snapshots, and cap history by bytes as well as steps. | §4.7 | M |

Next tier: gettext with a Bulgarian translation (M); `pyproject.toml` with ruff format
and lint plus mypy on the GTK-free core, replacing mixin shared state with explicit
collaborators (L); a lazily built or `Gtk.ListView`-based editor for chapters of
1,000+ items (L); a Flatpak manifest (M); deleting a trashed chapter's versions (S, C6).

---

## 7. Unverified / couldn't check

- **Your real desktop session and real notes.** I didn't launch the app on your GNOME
  Wayland session or open your chapters, to keep your data and running instance
  untouched. Every UI observation comes from Broadway, or Weston for AT-SPI, so
  **Wayland versus X11 behaviour, HiDPI and fractional scaling** weren't tested (Broadway
  doesn't scale). GTK 4 handles scaling itself, and the app sets few pixel sizes
  (`ui/rows.py:234` `set_size_request(150, -1)`), so problems there are unlikely
  (Inferred).
- **Logout and SIGTERM loss (C3)** is inferred from the missing handlers, not reproduced.
- **A real full disk (ENOSPC).** Simulated with a read-only folder (EACCES), which takes
  the same `OSError` path.
- **Orca speech.** I dumped the AT-SPI tree but didn't run Orca, so what it actually says
  is inferred from that tree.
- **The real Excalidraw window** (`NOTTERIZMUS_UI_WEBKIT=1`): not run; 7 tests skipped,
  and `ui/drawing_web.py` coverage is 22%. Real pastes to and from TopCoding weren't
  attempted (that would touch an external site).
- **Snap build:** `snapcraft` isn't installed, and the manifest has never been built.
- **Chapters above 4,000 items.** Not measured in the app. The first 2,000-item run hung
  in the test harness's own wait (§4.9), so 2,000 and 4,000 items were re-measured with a
  bounded loop, and 5,000 was dropped. Times on Broadway's software rendering may differ
  from your desktop's; the O(n²) Python part doesn't depend on the display.
- **pip-audit** has nothing to audit: the app's only Python runtime packages are the
  distro's PyGObject 3.56.2 and pycairo 1.27.0, which `pip-audit --no-deps` reports
  clean. The system GTK, libadwaita, WebKitGTK and Enchant libraries are Ubuntu's to
  patch and weren't audited.
- **Memory over a long session** was sampled (100 edits), not measured over hours.

---

## Appendix A. Discovery

**Stack (Verified).**

| Component | Version |
|---|---|
| Python | 3.14.4 (needs ≥ 3.11: `debian/control:12`) |
| PyGObject | 3.56.2 |
| Toolkit | GTK 4.22.4 + libadwaita 1.9.1 (needs ≥ 1.8) |
| Drawings | WebKitGTK 6.0 (2.52) running Excalidraw 0.18.1 + React 19.2.0, bundled with esbuild 0.25.12 |
| Spelling | Enchant 2 via `ctypes` (`spell.py:64-80`); the bindings set `argtypes` on every pointer-taking call |

There are no PyPI dependencies. The app is launched as `/usr/bin/notterizmus` →
`python3 -m notterizmus` with `PYTHONPATH=/usr/share/notterizmus` (`bin/notterizmus`), or
from a checkout with `./notterizmus.sh`.

**Structure (Verified).**

- `notterizmus/*.py` (3,329 lines) is the GTK-free core: model, rules, layout, export,
  importer, lexical, library, backups, files, state, paths, spell, completion, find,
  commands, guide, drawing and gpu.
- `notterizmus/ui/*.py` (6,015 lines) is the GTK layer: app, window plus 5 mixins, editor
  plus 8 mixins, rows, richtext, sidebar, findbar, versions, command_search and
  drawing_web.
- Storage is one JSON file per chapter: `<XDG Documents>/Notterizmus/<Book>/<NN>
  <Title>.notz`. Settings are in `$XDG_CONFIG_HOME/notterizmus/{rules.toml,state.json}`,
  versions and the guide in `$XDG_DATA_HOME/notterizmus/`, and drawing previews in
  `$XDG_CACHE_HOME/notterizmus/drawings/`.
- No networking or sync. The drawing page's CSP blocks the network.

**User-facing features (Verified).**

- **Windows and dialogs:** the main window, with header bar, chapter sidebar, find and
  replace bar, and editor. Also New Chapter, Chapter Properties, Rename Book, Changed on
  Disk, Earlier Versions, Search Commands, Plain Text, Keyboard Shortcuts, About, Open
  (file chooser), the Excalidraw drawing window, and Discard Changes for drawings.
- **Popovers:** Alt+Insert add menu, item menu, Ctrl+Space spelling and completion, and
  the right-click menu extension.
- **Commands:** 50 commands in one table (`commands.py:90-140`), all searchable. Keys:
  Ctrl+N/O/S/Q, Ctrl+Shift+C (Copy for TopCoding), Ctrl+F/H/R/G/Shift+G,
  Ctrl+Z/Shift+Z/Y, Ctrl+B/I, Ctrl+W/Shift+W, Ctrl+A, Ctrl+T, Ctrl+D, Ctrl+Space,
  Ctrl+Shift+Space, Alt+Insert, Alt+↑/↓, Tab/Shift+Tab, Ctrl+PgUp/PgDn, F1, F2, F9,
  Ctrl+Shift+P, Ctrl+?, Ctrl+=/−/0, and double-tap Ctrl for multiple cursors.
- **Settings:** `rules.toml` (numbering per level, connectors, spacing, markers, export
  options) through the menu's Edit and Reload Formatting Rules; spell-check on/off and
  language; text size 60–250%; sidebar visibility and width.

## Appendix B. Tool results

| Command | Result |
|---|---|
| `ruff check .` (0.17.6, defaults) | 99 findings (40 auto-fixable). 43 in the package: 18 ISC004 in `guide.py`, 9 I001, 5 RUF100, 3 RUF012, … No bugs. |
| `ruff format --check .` | 90 files would be reformatted, 10 already formatted |
| `mypy notterizmus` (2.4.1, PyGObject-stubs 2.20) | 4 errors |
| `mypy --check-untyped-defs` | 547 errors in 33 files: 390 attr-defined, 67 union-attr, 23 var-annotated, 17 arg-type, … |
| `bandit -r notterizmus` | 4: 2 High B324 (SHA-1 for cache keys), 1 Medium B314 and 1 Low B405 (`xml.etree` on own metainfo). All false positives in context. |
| `vulture notterizmus --min-confidence 60` | 23 candidates, 2 real (§4.8). None at ≥80%. |
| `pip-audit -r {PyGObject==3.56.2, pycairo==1.27.0} --no-deps` | No known vulnerabilities |
| `npm audit --package-lock-only --omit=dev` (anonymized copy) | 12 advisories (9 high, 1 moderate, 2 low), none in the shipped bundle (§4.6) |
| `python3 -m unittest discover -s tests -t .` | 430 tests OK, 35 skipped, 6.0 s |
| `pytest tests --ignore=tests/ui --cov --cov-branch` | 430 passed, 63 subtests. Package total 31% (UI not exercised); GTK-free modules 81–99%. |
| `scripts/ui-tests.sh` (Broadway) | 284 tests OK, 7 skipped, 180 s (two runs) |
| Coverage, unit + UI combined | 89% (6,634 statements, 2,142 branches) |
| `dpkg-buildpackage -us -uc -b` | OK in 11 s; tests ran in the build |
| `lintian --pedantic` | 1 pedantic tag |
| `desktop-file-validate`, `appstreamcli validate` | Clean; 1 pedantic |
| Clean venv, `python -m notterizmus` | `ModuleNotFoundError: No module named 'gi'` (by design: system PyGObject) |
| App launch | Not on the real display (§7). On Broadway the app starts with no GTK or Python warnings (the UI suite fails on any). |
