# Changelog

## Unreleased

- Bullets that come after a numbered sub-item but belong to the item above it get a `│` spacer line before and after them, so they no longer read as that sub-item's. Turn it off with `spacer_around_parent_leaves = false` in `rules.toml`.

## 1.7.0 — 2026-11-19

- A top-level item can be a bullet: type `* ` (or another bullet's trigger) at its start, use Ctrl+Shift+Space or the item-type menu, or paste bullets there. A bullet after a numbered item is set apart by a blank line. Shift+Tab still turns a bullet into the next numbered item.
- Menus and the Ctrl+Space popup are let go once they close; each one used to stay in memory until the app quit, the Ctrl+Space popup with the text it was opened on.
- **Earlier Versions** opens at once on big chapters: 0.07 s instead of 0.9 s for 54 copies of a 4 MB chapter. Each copy's item count and "same as now" are filled in a moment later.
- Long chapters are lighter to edit: Enter, Tab and undo in a chapter of 500 items re-measure the few rows they change instead of every row. Ctrl+Space in a book of 30 chapters keeps up with typing (0.09 ms a key instead of 2.8 ms), and pasting 5,000 lines takes 0.1 s instead of 17 s.
- **Copy for TopCoding** with a drawing gives tables the same header cells TopCoding makes itself: the first cell of a header row is both a row and a column header.

## 1.6.0 — 2026-11-19

- **Changed on disk**: if another program changes the open chapter's file (a sync tool, a second machine), the app asks before saving over it. **Reload** takes that version, and Ctrl+Z brings yours back; **Keep Mine** saves yours. The other version stays in Earlier Versions either way.
- **`!` and `?` bullets** for important and uncertain points: type `! ` or `? ` at the start of an item, or choose them from its menu.
- With NVIDIA's driver, drawing uses the GPU: a stroke in the drawing window draws at 60 frames a second instead of 8. Drawings stay sharp in wide windows.
- Nothing typed is lost when another chapter opens (from Files, Undo after a move to the Trash, New Chapter); the last second of typing used to go.
- Saves reach the disk before they replace the chapter, and keep its permissions; every save used to make a chapter readable by you alone.
- Renumbering or reordering chapters puts everything back if it fails halfway, and a chapter left hidden by a crash in the middle of one is offered back at start-up. Earlier Versions follow chapters that swap places, untitled ones too, and keep their order in the hour that comes twice when daylight saving ends.
- **Paste as Plain Text** and **One Item per Paragraph** no longer undo what you typed after the paste. Pasted "Yes) …" stays text, Bulgarian letter labels ("а)", "б)") become numbered items, and clipboard data that can't be read falls back to its text.
- **New Chapter** takes long titles (the file name is shortened), makes chapter 10 when there is a chapter 100, says when it can't write the file, and a book whose name starts with a dot is listed.
- Top-level items stay numbered when `* ` is typed at their start or bullets are pasted there, and an item type that can't apply leaves what you typed.
- The drawing window asks before Cancel throws away any change, a new background included; a file opened while it is open waits; and its menu no longer offers Mermaid to Excalidraw or Web Embed, which can't work offline.
- Fixed: Shift+click after Ctrl+W or after clicking a drawing; toasts with “&” or “<” in a title; Delete Block on a block from a newer version; Getting Started's own words going unflagged in other chapters; Ctrl+B or Ctrl+I before typing with some input methods.
- A broken `state.json` can't keep the app from starting, and a `rules.toml` whose triggers clash or that names an unknown number format is reported.
- The package builds on Launchpad again (1.4.2 and 1.5.0 never did: their tests needed PyGObject), and it recommends the Bulgarian spelling dictionary.

## 1.5.0 — 2026-11-18

- **Paste** a copy of TopCoding's notes that includes a drawing, and the drawing arrives too, where it was among the items (Chrome and Firefox); before, only the text and tables did. Built from TopCoding's clipboard format and not yet tried with a real copy from TopCoding.
- **Delete** and **Ctrl+X** remove only the items selected. A selection that ended on a section heading used to take the items under that heading along, though it never reached them. Sub-items that weren't selected move up into the deleted item's place, and Copy takes only the selected items. Ctrl+W gains a step: the item, then the item with its sub-items, then the section.
- Drawings use far less memory: a closed drawing window ends its web process (about 85 MB each), a chapter's rows are freed when another chapter opens, previews are made no larger than they are shown (31 MB instead of 237 MB for 8 drawings), and undo steps share drawings instead of copying them (about 32 KB a step instead of up to 8 MB).
- **Done** in the drawing window takes about 0.15 s instead of 0.9–3.2 s, and a chapter with drawings opens faster.
- Quitting no longer crashes when drawing previews were made and no drawing window was opened; 1.4.0 to 1.4.2 did.
- Development: `tests/ui/measure_drawings.py` measures how fast drawings are; UI tests check that drawing windows and rows are freed.

## 1.4.2 — 2026-11-17

- **Ctrl+A** selects all items again while the Bulgarian (or another non-Latin) keyboard layout is on; before, it selected only the current item's text. The editor's other Ctrl and Alt shortcuts (Ctrl+B, Ctrl+I, Ctrl+W, Ctrl+Z and the rest) work on such layouts too.

## 1.4.1 — 2026-11-17

- **Copy for TopCoding** takes drawings along when TopCoding is open in Firefox too; before, only the text and tables arrived there.

## 1.4.0 — 2026-11-17

- **Drawings** (Ctrl+D, the menu, Alt+Insert or Search Commands): [Excalidraw](https://excalidraw.com) opens inside the app, offline. **Done** puts the drawing under the item as a picture; double-click it or use **Edit Drawing** to change it. Adding, changing and deleting a drawing are undo steps.
- **Copy** above a drawing, or a click on it and Ctrl+C, copies that drawing alone.
- **Copy for TopCoding** takes drawings along: a copy with a drawing also carries the TopCoding editor's own format, which is the only way it accepts drawings. Copies without drawings are unchanged.
- Needs WebKitGTK (`gir1.2-webkit-6.0`), installed with the package. The package is about 6 MB larger for the bundled Excalidraw.

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
