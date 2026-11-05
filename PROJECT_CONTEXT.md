# Notterizmus — context for coding agents

## Purpose
- GNOME desktop outline editor for book chapter notes; output is pasted into TopCoding's notes editor (`app.topcoding.bg/assignments`). Snapshot: v1.0.0, 2026-11-04.
- Single main user: Ubuntu 26.04 (`resolute`), GNOME 50, Wayland, locale `bg_BG.UTF-8`, notes in English and Bulgarian.
- Distributed as a Debian package via `ppa:simeonandreev/ppa-library`; GPL-3.0-or-later.

## Rules
- Use the platform's native stack: Python 3.11+, PyGObject, GTK 4, libadwaita (≥1.8), Enchant via ctypes. No pip dependencies.
- Keep `model.py`, `rules.py`, `layout.py`, `export.py`, `importer.py`, `spell.py`, `completion.py`, `paths.py` free of GTK so they stay unit-testable.
- Every document mutation in the editor goes through `with self._op():` or `self._commit(group)` in `ui/outline.py`; otherwise it is neither undoable nor autosaved.
- Never remove and re-append row widgets: `refresh()` reorders children in place (`reorder_child_after`) and reuses rows by node id and spacer labels. Re-adding rows makes the text jump (bug reported and fixed).
- New text views: call `size_new_views()` (min height = one line) and let `_requeue_views()` re-measure after 20 ms; GtkTextView measures its height before it knows its width.
- Don't use `Gtk.PopoverMenu` for app menus (it mis-measures and scrolls); use `OutlineEditor._popup()` (ListBox popover). The right-click menu is GtkTextView's own, extended via `set_extra_menu` in `_prepare_context()`.
- Roman numerals are the single Unicode characters `Ⅰ`–`Ⅻ` (user requirement), composed beyond 12 (`ⅩⅢ`).
- When a version changes, update all four: `notterizmus/__init__.py` `VERSION`, `data/*.metainfo.xml` `<release>`, `CHANGELOG.md`, `debian/changelog`.
- `APP_ID = dev.simo.Notterizmus` is also the icon name, desktop-file name, metainfo id and Wayland app id; keep them identical.
- Ask before pushing, uploading to the PPA, or publishing anything; commit only when asked.

## Facts and decisions
- Tree: `Node` kinds `root`, `heading` (numbered), `bullet` (marker `dot`/`plus`/`minus` or user-defined), `table` (`data.rows` = rows × cells × runs, `data.header`). Text is a list of `Run(text, bold, italic)`.
- `can_contain`: headings only under root or headings; bullets/tables under headings or bullets. Outdenting a bullet to root turns it into a heading.
- Layout defaults reproduce the user's sample exactly for tree sections: bullet column = label column + 5; spacer `│` line before each numbered child unless the previous sibling is a bullet; blank line between top-level items.
- File format: JSON `{"format": "notterizmus/1", book, chapter{number,title}, lang?, content[]}`, `.notz`, saved atomically, autosaved 800 ms after changes. Path: `<XDG Documents>/Notterizmus/<Book>/<NN> <Title>.notz` (localized folder, e.g. `~/Документи`).
- `~/.config/notterizmus/state.json`: `last_file`, `last_book`, `spell`, `spell_lang`. `rules.toml` overrides `rules.DEFAULTS`.
- Undo: whole-document JSON snapshots; typing groups per word (`RichText.last_edit` → `_text_group`); GtkTextBuffer's own undo is disabled. History resets on load.
- Enter on an empty bullet under a heading converts it to the heading's next sibling (Ⅰ.1.a + bullets → Ⅰ.1.b); Ctrl+Enter does the same from anywhere.
- Multi-cursor: Ctrl tapped twice within 0.4 s and held, then ↑/↓; extra carets are GtkTextMarks drawn in `do_snapshot_layer`.
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
- Unit tests: `python3 -m unittest discover -s tests -t .` (also run during the Debian build). They cover only the non-GTK modules.
- UI: drive real widgets from a script. Construct `App()`, call `editor.on_key(row, row.view, Gdk.keyval_from_name(...), modifiers)`, type with `buffer.insert_interactive_at_cursor`, pump `GLib.MainContext` between steps.
- Run scripts with `XDG_CONFIG_HOME=<scratch dir>` so the user's `state.json` and rules are untouched, and add `Gio.ApplicationFlags.NON_UNIQUE` to the `App` flags: if the user's app is open, a unique second instance just activates theirs and exits silently.
- Drive popovers by emitting `key-pressed` on their `Gtk.EventControllerKey` (from `observe_controllers()`) and `row-activated` on their ListBox.
- `NOTTERIZMUS_SNAPSHOT=out.png` renders the window to a PNG and quits; popovers need their own `Gtk.WidgetPaintable` render.
- Layout jumps: record child y-positions in a `add_tick_callback` for ~12 frames after an action; all frames must match the final layout.
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
