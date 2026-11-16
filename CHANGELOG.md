# Changelog

## 1.3.2 — 2026-11-16

- Dragging the mouse from one item to another selects whole items (within one item it still selects text); near the top or bottom edge the outline scrolls and the selection keeps growing.
- A table copied on its own (from a web page, say), or together with plain text, is pasted after the current item instead of being lost.
- A chapter file that is damaged or isn't a chapter, or a `rules.toml` with a value of the wrong kind, is reported instead of keeping the app from starting; the defaults apply for the rules.
- Fields and a format name written by a newer version are kept when a chapter is saved; a save that fails leaves no temporary file behind.
- Renumbering or reordering chapters stops before moving anything if one of them can't be read; renaming a book carries on past a chapter it can't rewrite and says which.
- Deleting a top-level item turns its bullets into numbered items, as outdenting them would.
- After an undo, typing and shortcuts go to the item that has the cursor.
- Development: each UI test run is isolated in its own runtime folder, so runs can go in parallel; a hung test is stopped with a traceback, and Python warnings fail the run.

## 1.3.1 — 2026-11-14

- Text is drawn hinted (GTK's manual font rendering when the desktop is on automatic), so thin strokes stay visible: the top bar of "=" faded until it looked like "-".
- Escape closes the find bar from anywhere in it (the replace field and buttons too) and from the text, after extra cursors and item selection.
- Ctrl+F on a selected word starts at that word; Search Commands keeps the text selection for Bold and Italic; Enter right after typing in either search acts on what was typed.
- Earlier Versions keeps a long history: all of the last day, then one copy per hour for a week, per day for three months and per week after that, grouped by day in the dialog.
- Indenting or outdenting an item whose text wraps no longer makes the rows below jump for a frame.
- Development: the editor is split into themed modules (`ui/outline_*.py`); UI tests press real keys through GTK's Broadway server (100 tests).

## 1.3.0 — 2026-11-07

- Find (Ctrl+F) and replace (Ctrl+H or Ctrl+R) across the chapter, table cells included: every match highlighted, “3 of 12”, Enter / Shift+Enter or Ctrl+G / Ctrl+Shift+G, Match Case and Whole Words (Cyrillic too). Replacing keeps bold/italic; Replace All is one undo step.
- Earlier Versions (menu): a copy of each chapter is kept when it's opened and every 10 minutes while editing (newest 20, in `~/.local/share/notterizmus/backups`); preview and restore, undoable. Copies follow renamed chapters.
- Search Commands (Ctrl+Shift+P): find any command by name or keyword, run it with Enter; each shows its key. Key-only editor actions run by replaying their key.
- Text size: Ctrl+= / Ctrl+- / Ctrl+0, Ctrl + scroll wheel, or the “− 100% +” row in the menu (60–250%, remembered); only the chapter text changes.

## 1.2.0 — 2026-11-06

- Chapter list on the left (F9): books from the notes folder with their chapters in order; click to open, click a book to fold it. Ctrl+PgUp / Ctrl+PgDn open the previous or next chapter. Drag its edge to resize it (remembered; double-click for the default). In a narrow window it slides over the text.
- Chapter Properties (F2): rename a chapter, change its number (a number another chapter has is swapped) or move it to another book. F2 on a book renames it, folder and stored name.
- Reorder chapters by dragging them in the list or with Alt+↑ / Alt+↓; the book's existing numbers are handed out in the new order. Delete moves a chapter to the Trash, with Undo.
- Getting Started (F1): a fresh practice chapter that explains each control. F1 used to open About, which is now in the menu only.
- Chapters saved by a newer version open safely: unknown block types are shown read-only and left out of Copy for TopCoding, and unknown blocks and fields are saved back unchanged.
- Fix: no more GTK size warnings for table cells; the Hunspell `.aff` file is closed after reading.
- Development: UI tests that run off-screen (`scripts/ui-tests.sh`, on Weston or Broadway).

## 1.1.0 — 2026-11-05

- Ctrl+Space: spelling fixes and word completion (chapter, book, dictionary). Item type cycling moved to Ctrl+Shift+Space.
- Number hotkeys (1–9, 0) in the Alt+Insert, item and Ctrl+Space popups.
- Fix: the view now follows the cursor; Enter at the bottom of a full window no longer hides it.
- Notes stay in the real Documents folder when running as a snap.
- Snap recipe added (`snap/snapcraft.yaml`); not yet published.
- The About dialog takes its release notes from the AppStream metadata.

## 1.0.0 — 2026-11-04

First release. See [FEATURES.md](FEATURES.md) for the full feature list.

Packaged for Ubuntu and distributed through `ppa:simeonandreev/ppa-library`;
licensed GPL-3.0-or-later.
