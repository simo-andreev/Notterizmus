# Notterizmus — context for coding agents

## Purpose
- GNOME desktop outline editor for book chapter notes; output is pasted into TopCoding's notes editor (`app.topcoding.bg/assignments`). Snapshot: v1.3.0, 2026-11-07.
- Single main user: Ubuntu 26.04 (`resolute`), GNOME 50, Wayland, locale `bg_BG.UTF-8`, notes in English and Bulgarian.
- Distributed as a Debian package via `ppa:simeonandreev/ppa-library`; GPL-3.0-or-later.

## Rules
- Use the platform's native stack: Python 3.11+, PyGObject, GTK 4, libadwaita (≥1.8), Enchant via ctypes. No pip dependencies.
- Keep `model.py`, `rules.py`, `layout.py`, `export.py`, `importer.py`, `spell.py`, `completion.py`, `paths.py`, `guide.py`, `library.py`, `backups.py`, `commands.py`, `find.py` free of GTK so they stay unit-testable.
- When a control or shortcut changes, update the Getting Started chapter (`guide.py`) as well as README.md, FEATURES.md and the shortcuts dialog. `tests/test_guide.py` fails if the guide teaches a key that README.md doesn't mention, or if the guide gains a word the English dictionary flags (add it to `guide.SPELL_IGNORE`).
- To ask whether a node holds text, use `model.is_text(node)` (heading or bullet), never `kind != "table"`: kinds from a newer version are neither.
- Never drop data the code doesn't understand: `Node.extra` carries unknown fields of known kinds, and unknown kinds keep their whole JSON; both are saved back unchanged.
- The editor is `ui/outline.py` (the widget: rows, refresh, focus, scrolling) plus mixins `ui/outline_*.py`, one theme each (`undo`, `keys`, `items`, `selection`, `clipboard`, `menus`, `assist`, `carets`). They share `self`; put new editor methods in the matching mixin, and key handling in `outline_keys.on_key` / `common_key`.
- Every document mutation in the editor goes through `with self._op():` or `self._commit(group)` (`ui/outline_undo.py`); otherwise it is neither undoable nor autosaved.
- Never remove and re-append row widgets: `refresh()` reorders children in place (`reorder_child_after`) and reuses rows by node id and spacer labels. Re-adding rows makes the text jump (bug reported and fixed).
- Scrolling follows the cursor via `ensure_visible()` (tick callback, retried until new rows are laid out); the viewport's own `scroll_to_focus` is off. Every new text view must be registered with `track_cursor()`.
- New text views: call `size_new_views()` (min height = one line) and let `_requeue_views()` re-measure after 20 ms; GtkTextView measures its height before it knows its width.
- Don't use `Gtk.PopoverMenu` for app menus (it mis-measures and scrolls); use `OutlineEditor._popup()` / `popup_menu()` (ListBox popover, `ui/outline_menus.py`). Rows flagged `_choice = True` get number hotkeys 1–9, 0 from `_number_rows()`; keep that for any new popup. Exception: Search Commands, where digits are typed into the search. The right-click menu is GtkTextView's own, extended via `set_extra_menu` in `_prepare_context()`.
- Roman numerals are the single Unicode characters `Ⅰ`–`Ⅻ` (user requirement), composed beyond 12 (`ⅩⅢ`).
- When a version changes, update: `notterizmus/__init__.py` `VERSION`, `data/*.metainfo.xml` `<release>` (also the About dialog's release notes), `CHANGELOG.md`, `debian/notterizmus.1` header, `debian/changelog` (via `dch` with `DEBEMAIL` = maintainer email). `tests/test_release.py` enforces it.
- `APP_ID = dev.simo.Notterizmus` is also the icon name, desktop-file name, metainfo id and Wayland app id; keep them identical.
- Ask before pushing, uploading to the PPA, or publishing anything; commit only when asked.

## Facts and decisions
- Tree: `Node` kinds `root`, `heading` (numbered), `bullet` (marker `dot`/`plus`/`minus` or user-defined), `table` (`data.rows` = rows × cells × runs, `data.header`). Text is a list of `Run(text, bold, italic)`.
- `can_contain`: headings only under root or headings; bullets/tables under headings or bullets. Outdenting a bullet to root turns it into a heading.
- Layout defaults reproduce the user's sample exactly for tree sections: bullet column = label column + 5; spacer `│` line before each numbered child unless the previous sibling is a bullet; blank line between top-level items.
- File format: JSON `{"format": "notterizmus/1", book, chapter{number,title}, lang?, content[]}`, `.notz`, saved atomically, autosaved 800 ms after changes. Path: `<XDG Documents>/Notterizmus/<Book>/<NN> <Title>.notz` (localized folder, e.g. `~/Документи`).
- `~/.config/notterizmus/state.json`: `last_file`, `last_book`, `spell`, `spell_lang`, `sidebar`, `sidebar_width`, `zoom`. `rules.toml` overrides `rules.DEFAULTS`.
- Undo: whole-document JSON snapshots; typing groups per word (`RichText.last_edit` → `_text_group`); GtkTextBuffer's own undo is disabled. History resets on load.
- Enter on an empty bullet under a heading converts it to the heading's next sibling (Ⅰ.1.a + bullets → Ⅰ.1.b); Ctrl+Enter does the same from anywhere.
- Multi-cursor: Ctrl tapped twice within 0.4 s and held, then ↑/↓; extra carets are GtkTextMarks drawn in `do_snapshot_layer`.
- Chapter sidebar (R1): `Adw.OverlaySplitView` with `ui/sidebar.ChapterSidebar`; `library.scan(notes_root())` reads book folders and `<NN> <Title>.notz` names (not the JSON). It rescans when a chapter opens, when the sidebar is shown and when the window becomes active. Its width is fixed (`min = max = state["sidebar_width"]`, default 260, 180-520) and set by `Window.set_sidebar_width()`, which also moves the collapse breakpoint to "list + text column minimum + 20 px"; collapsing into an overlay doesn't change the saved `sidebar` choice. The split view has no resize handle, so `Window.handle` is an overlay strip over the edge; the drag gesture sits on the overlay (stationary, so offsets don't jitter) and claims only after 3 px of movement, so the handle's double-click (reset) isn't cancelled. `win.prev-chapter`/`win.next-chapter` (Ctrl+PgUp/PgDn) are app accels and also handled in `OutlineEditor.common_key`, so GtkTextView can't take them.
- Renaming and reordering (R2, R28): `library.set_chapter` / `renumber` / `reorder` / `rename_book` change files and return `{old path: new path}`. Call `Window._flush_save()` before and `_after_move(moved)` after, which re-points the open `Document` (path, book, number, title) and `last_file`; otherwise autosave recreates the old file. Chapter numbers are the real book's, so reordering permutes the existing numbers and a taken number is swapped, never invented. Renumbering stages files under hidden `.moving-*.notz` names, which `scan()` skips. Trash goes through `window._trash_file` / `_restore_from_trash` (UI tests swap in a scratch Trash: `/tmp` is tmpfs, so the real Trash would collect test files in `/tmp/.Trash-1000`).
- Text size (R5): `Window.set_zoom()` writes `font-size` for `.outline .prefix, .outline textview.rt` into one app-wide CSS provider above style.css (one per window would pile up on the display; a closed window's would win). It calls `OutlineEditor.text_size_changed()`, which drops the rows' one-line minimum height and forgets `_line_h`; don't re-measure in the same frame, because the new font only takes effect in the layout phase. Ctrl + scroll goes through `Window.scroll_zoom(ctrl, dy)`.
- Find and replace (R3): `ui/findbar.FindBar` (a `Gtk.SearchBar` under the header) matches with `find.find_all` in every text view in outline order (`display_order` → `row.views()`), highlights with each RichText's `tag_found` / `tag_found_current`, and selects the current match in its view (so Esc leaves the cursor there). Replacing uses `RichText.replace_range` (keeps the first replaced character's bold/italic) inside `editor._op()`, so Replace All is one undo step. It refinds 200 ms after the editor's `changed` signal. Escape: a capture controller on the bar closes it from any of its widgets; in the text, `OutlineEditor.on_escape` (set by the window) closes it after multi-cursor and item selection have had their Escape.
- Primary selection: a search field that selects its own text takes the primary selection, which collapses the chapter's text selection to its end. Capture the cursor/selection before focusing such a field (`FindBar._anchor`, the `before_run` restore in Search Commands). Search fields use `search_delay=0`, and Enter catches up if it arrives before the list or the matches did, so Enter right after typing acts on what was typed.
- Search Commands (R24, Ctrl+Shift+P): `ui/command_search.build(win)` lists what's available now (window actions that are enabled; editor commands only while the window has a chapter open, since the editor keeps its last chapter after one closes), `commands.search()` ranks them. Key-only editor behaviours are replayed with `OutlineEditor.on_key(row, view, keyval, state)` using GTK's key names (Shift+w → `W`, Shift+Tab → `ISO_Left_Tab`). The chosen command runs on the dialog's `closed` signal, after focus is back in the editor. New commands go into `build()`.
- Earlier versions (R4): `backups.py`; copies in `paths.backups_dir()/<Book>/<chapter stem>/<YYYY-MM-DDTHH-MM-SS>.notz`. `Window.set_doc` takes a forced copy on open; `Window.save` copies the on-disk file before overwriting it at most every `backups.BACKUP_EVERY` (600 s), skipping identical copies, keeping `KEEP` (20). Not for the guide. `_after_move` moves the copies with renamed chapters. Restore = `OutlineEditor.replace_content(root)`, one undo step.
- Getting Started (F1, `win.guide`): `guide.document()` writes a fresh copy to `paths.guide_path()` (`$XDG_DATA_HOME/notterizmus/`, outside the notes folder) each time it's opened; `Window._is_guide()` gives it its own title, keeps `last_book` unchanged and session-ignores `guide.SPELL_IGNORE`. F1 used to open About.
- Unknown kinds (R6): `layout` emits a `Line("unknown")` and skips their children, the exporters drop those lines, spacer decisions ignore them, the editor shows `rows.UnknownRow` (read-only note with a delete button, no text view, skipped by the cursor).
- Ctrl+Space (`OutlineEditor.show_assist`): completions from `completion.py` (chapter words, then other `.notz` in the book folder via `BookWords`, then the Hunspell `.dic` stems for the word's alphabet), plus spelling fixes. Spelling fixes are hidden while the cursor is at the end of a word that has completions (an unfinished word always looks misspelled). Ctrl+Shift+Space cycles item type.
- Clipboard MIME types: internal `application/x-notterizmus-nodes+json` and `-runs+json`, plus `text/html` and `text/plain`.
- Paste: `importer.parse()` returns `None` for text without outline markers → it is joined into the current item (user wants long text in one item); Ctrl+Shift+V always joins.
- Spelling: Enchant/Hunspell via ctypes because the `gir1.2-spelling-1` typelib isn't installed. Primary language comes from the chapter text, not the locale (the `bg_BG` locale once marked all English red). Words in the other alphabet use a matching dictionary.

## TopCoding target
- The editor is Lexical (namespace `SummaryEditor`) rendered in proportional Roboto; it has native table and `excalidraw` nodes.
- Pasted HTML keeps whitespace only inside `white-space: pre-wrap` spans; `<strong>`, `<em>`, `<br>`, `<table>`, `<th>` survive; `font-family` styles are stripped; `<code>` survives as inline code with a background (rule `export.code_prefix`).
- `export.to_html` writes one `<p>` with `<br>` per line, breaking only for tables; real pastes of this format are confirmed good by the user.
- Testing paste in the browser: dispatch a synthetic `ClipboardEvent('paste')` with a `DataTransfer` on `[data-lexical-editor]`; never click Save/Submit there; restore with `editor.setEditorState(...)`. Chapter 12 of assignment 2522 is the user's scratch chapter.
- Drawings (planned) would need Lexical's own clipboard JSON (`application/x-lexical-editor`); untested whether Chrome on Linux accepts that from a native app.

## Verifying changes
- Unit tests: `python3 -m unittest discover -s tests -t .` (also run during the Debian build). They cover the non-GTK modules; the UI suites skip themselves there.
- UI tests: `scripts/ui-tests.sh` runs `tests/ui` on a private display (headless Weston if installed, else Broadway), with config, data and Documents in a scratch folder, and fails if GTK prints a warning. Add a UI test for every UI bug fixed. Helpers are in `tests/ui/support.py`: `open_chapter`, `focus`, `press` (emits `key-pressed` on the widget's own controller with GTK's key names, e.g. Shift+z → `Z`), `type_text`, `record_frames`, `menu_choices`, `clipboard`.
- Broadway without a browser draws about one frame per second, so frame-by-frame checks (`record_frames`) only run on Weston (`NOTTERIZMUS_UI_FRAMES=1`).
- Adw dialogs keep counting as visible while they animate closed and give focus back when they finish: wait for `get_visible_dialog()` to be None before the next step.
- Never read the app's own clipboard synchronously from the main thread: the app supplies the data from the main loop, so it deadlocks (use `support.clipboard`).
- Ad-hoc scripts outside the runner: set `XDG_CONFIG_HOME`/`XDG_DATA_HOME` to a scratch dir and add `Gio.ApplicationFlags.NON_UNIQUE`; otherwise a running copy of the app just gets activated and the script exits silently.
- `NOTTERIZMUS_SNAPSHOT=out.png` renders the window to a PNG and quits; popovers need their own `Gtk.WidgetPaintable` render.
- Wayland: a window without keyboard focus can't own the clipboard, so system-clipboard tests from background windows fail; same-process clipboard reads work.

## Packaging and release
- Native source format `3.0 (native)`: versions have no `-revision`; rebuilds for another series use `1.0.0~<series>1`.
- `scripts/release.sh deb|source|ppa` builds from `git archive HEAD` (refuses a dirty tree) into `dist/` (git-ignored); signing uses the GPG key matching the `debian/changelog` maintainer email.
- Installed layout: code in `/usr/share/notterizmus/notterizmus/`, launcher `/usr/bin/notterizmus`, icons in hicolor PNG 16–512.
- lintian baseline: only pedantic `repeated-path-segment`. Man pages must stay ASCII (groff warns on Cyrillic or Roman-numeral characters).
- `install.sh` is a per-user developer launcher; remove it (`--uninstall`) before installing the package.

## Open questions
- Whether to support Ubuntu releases other than `resolute`.
- Excalidraw block: data format and paste path not decided.
