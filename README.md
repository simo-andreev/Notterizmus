<img src="data/icons/hicolor/256x256/apps/dev.simo.Notterizmus.png" width="96" align="right" alt="">

# Notterizmus 1.1

A GNOME outline editor for book chapter notes. Numbering (`Ⅱ.1.a)`) and tree
connectors (`├ └ │`) are generated as you type, and **Copy for TopCoding** puts
the outline on the clipboard as HTML that pastes cleanly into the chapter notes
editor at `app.topcoding.bg/assignments`. Made for personal book notes in
English and Bulgarian; it is not a general word processor or Markdown editor.

Updated 2026-11-05 · Python 3 + GTK 4 + libadwaita · GPL-3.0-or-later ·
[FEATURES.md](FEATURES.md) · [CHANGELOG.md](CHANGELOG.md) ·
[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) (briefing for coding agents)

## Install

From the PPA (updates arrive through Software Updater; uninstall from App Center
or with `sudo apt remove notterizmus`):

```bash
sudo add-apt-repository ppa:simeonandreev/ppa-library
```

```bash
sudo apt install notterizmus
```

Requires Ubuntu 25.10 or newer (libadwaita 1.8+); the package is currently built
for 26.04 (`resolute`) only. Notes and settings are kept when the app is removed.

## Using it

New here? Press F1 (or menu → **Getting Started**) for a practice chapter that
walks through the controls; each time you open it, it starts fresh.

1. **New Chapter** (Ctrl+N): enter book, chapter number and optional title.
2. Type the outline. Start an item with `# ` for a numbered item, `* ` `+ ` `- `
   for a note, pro or con bullet. Tab / Shift+Tab change the level.
3. **Copy for TopCoding** (Ctrl+Shift+C), then Ctrl+V in TopCoding's notes editor.
   Bold, italic, spacing and tables come through; keep the app open while pasting.

| Do this | Key |
|---|---|
| New item (splits at the cursor) | Enter |
| Next numbered item at this level (e.g. Ⅰ.1.b after Ⅰ.1.a and its bullets) | Ctrl+Enter, or Enter on an empty bullet |
| Add-component menu (next / sub / parent item, bullets, table) | Alt+Insert |
| Context menu (spelling, formatting, item type, add, selection, undo) | right-click |
| Make it a sub-item / move it back out | Tab / Shift+Tab |
| Move the item up or down | Alt+↑ / Alt+↓ |
| Spelling fixes and word completion at the cursor (keep typing to filter, Enter or Tab picks) | Ctrl+Space |
| Change item type | Ctrl+Shift+Space, or click its prefix |
| Pick a choice in the Alt+Insert, item or Ctrl+Space popup | its number, 1–9 then 0 (keypad too) |
| Bold / italic | Ctrl+B / Ctrl+I |
| Undo / redo (one word, deletion run, or structural change per step) | Ctrl+Z / Ctrl+Shift+Z (or Ctrl+Y) |
| Expand / shrink selection: word → item text → item → section → all | Ctrl+W / Ctrl+Shift+W |
| Select all items | Ctrl+A |
| Extend item selection | Shift+↑ / Shift+↓ at the first/last line, or Shift+click |
| Selected items: copy, cut, delete, indent, bold | Ctrl+C, Ctrl+X, Delete, Tab, Ctrl+B |
| Add cursors above/below | tap Ctrl twice, keep it held, then ↑ / ↓ (Esc to leave) |
| Paste, detecting outline structure | Ctrl+V |
| Paste as plain text, joined into the current item | Ctrl+Shift+V |
| Insert table | Ctrl+T (in a cell: Tab moves to the next one and adds a row at the end) |
| Delete an empty item / join with the line above | Backspace at the start |
| New chapter / open a chapter | Ctrl+N / Ctrl+O |
| Previous / next chapter of the book | Ctrl+PgUp / Ctrl+PgDn |
| Show or hide the chapter list (books and their chapters, on the left) | F9 |
| Chapter properties: rename, change the number, move to another book (on a book in the list: rename the book) | F2 |
| In the chapter list: reorder, move to Trash, more | drag, or Alt+↑ / Alt+↓; Delete; right-click |
| Resize the chapter list (double-click the edge for the default width) | drag the edge between the list and the text |
| Getting Started: a practice chapter that shows the controls | F1 |
| All shortcuts | Ctrl+? |

Enter on an empty sub-item moves it out one level; on an empty bullet under a
numbered item it becomes that item's next sibling. Top-level items are always
numbered.

**Pasting in.** Ctrl+V recognises the app's own output, TopCoding's HTML and
hand-written notes (`Ⅱ.1)`, `II.1)`, `2.1)`, `•`/`+`/`-`/`*` bullets nested by
indentation) and renumbers everything; the notification offers **Paste as Plain
Text** to undo that. Text without outline markers, such as paragraphs from a PDF,
goes into the current item as one paragraph with line-break hyphenation removed;
the notification offers **One Item per Paragraph**.

**Spelling.** The language button in the header bar (e.g. `EN-US`) switches
language or turns checking off. A new chapter picks its language from its text,
and the choice is saved in the chapter file. Words in the other alphabet use a
matching dictionary automatically (English for Latin, Bulgarian for Cyrillic).
"Add to Dictionary" writes to your personal Enchant word list. Ctrl+Space
completes the word you're typing from this chapter, the book's other chapters,
then the dictionary; on a misspelled word it lists fixes.

**Known limits.**
- TopCoding shows notes in a proportional font, so tree connectors drift a few
  pixels there. Rule `export.code_prefix = true` aligns them perfectly but
  TopCoding then draws a code background behind them.
- An item is one paragraph; line breaks inside an item are not supported.
- No drawings yet (TopCoding supports Excalidraw; see "Adding a block type").
- Undo history lasts until the chapter is closed.

## Files

| What | Where |
|---|---|
| Chapter notes, one autosaved JSON file per book + chapter | `<Documents>/Notterizmus/<Book>/<NN> <Title>.notz` — `<Documents>` is the localized XDG folder, e.g. `~/Документи` |
| Formatting rules (optional) | `~/.config/notterizmus/rules.toml`, created from [`rules.example.toml`](notterizmus/rules.example.toml) by menu → **Edit Formatting Rules**; apply with **Reload Formatting Rules** |
| Last open chapter, spelling choices | `~/.config/notterizmus/state.json` |
| Getting Started practice copy, rewritten each time it's opened | `~/.local/share/notterizmus/Getting Started.notz` |

Rules cover numbering format per level, connector characters, spacing, spacer
and blank lines, and your own bullet markers.

## Development

```bash
./notterizmus.sh
```

```bash
python3 -m unittest discover -s tests -t .
```

The UI tests in `tests/ui` drive the real editor on a private display, so no
window appears and your own settings and notes aren't touched. They need Weston
for the frame-by-frame checks (`sudo apt install weston`); without it they run on
GTK's Broadway server and skip those checks.

```bash
scripts/ui-tests.sh
```

`./install.sh` adds this checkout to the app grid for your user (`--uninstall`
removes it); don't keep it alongside the packaged app or it appears twice.
`NOTTERIZMUS_SNAPSHOT=/path/out.png ./notterizmus.sh <file.notz>` renders the
window to a PNG and quits. How the code fits together, its invariants and how UI
changes are verified are in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

| File | Role |
|---|---|
| `notterizmus/model.py` | Node tree, tree operations, `.notz` load/save (no GTK) |
| `notterizmus/rules.py` | Formatting defaults, user overrides, numbering formats |
| `notterizmus/layout.py` | Tree → lines with labels and connectors |
| `notterizmus/export.py` | Lines → HTML for TopCoding, and plain text |
| `notterizmus/importer.py` | Pasted HTML/text → outline nodes |
| `notterizmus/spell.py` | Enchant spell checker (ctypes) |
| `notterizmus/completion.py` | Ctrl+Space word completion (chapter, book, dictionary) |
| `notterizmus/guide.py` | The Getting Started chapter; update it when a control changes |
| `notterizmus/paths.py` | Documents folder (also inside a snap), guide and metainfo paths |
| `notterizmus/library.py`, `notterizmus/ui/sidebar.py` | Books and chapters in the notes folder; the chapter list |
| `tests/`, `tests/ui/`, `scripts/ui-tests.sh` | Unit tests (no GTK); UI tests and their runner |
| `notterizmus/ui/outline.py` | Editor: rendering, keys, undo, selection, clipboard, menus, multi-cursor |
| `notterizmus/ui/rows.py`, `richtext.py` | Row widgets (text, table) and the rich-text view |
| `notterizmus/ui/window.py`, `app.py` | Window, header bar, dialogs, file handling, spelling menu |
| `data/` | Icons, desktop entry, AppStream metadata, `.notz` MIME type |
| `debian/`, `scripts/release.sh` | Ubuntu packaging and the PPA release script |

### Adding a block type (e.g. Excalidraw drawings, planned)

1. `model.py`: add a codec to `DATA_CODECS` for the node's `data`.
2. `layout.py`: emit a `Line` for it (like `table`).
3. `export.py`: HTML and plain-text output for that line kind.
4. `ui/rows.py`: a row widget, registered in `ROW_TYPES`.

## Releasing to the PPA

One-time setup: `sudo apt install debhelper dh-python devscripts dput lintian`,
and a GPG key for the maintainer identity in `debian/changelog`, published to
`keyserver.ubuntu.com` and confirmed on Launchpad (profile → OpenPGP keys). The
key needs an encryption subkey, because Launchpad confirms keys by encrypted
email.

Each release:

1. Bump the version: `VERSION` in `notterizmus/__init__.py`, a `<release>` with
   notes in `data/dev.simo.Notterizmus.metainfo.xml` (App Center and the About
   dialog show them), a section in `CHANGELOG.md`, the man page header in
   `debian/notterizmus.1`, and `debian/changelog`:
   `DEBFULLNAME="Simo Andreev" DEBEMAIL="simeon.zlatanov.andreev@pm.me" dch -v 1.2.0 "What changed"`,
   then the same with `dch -r -D resolute ""`. Update `FEATURES.md` if features
   changed. `tests/test_release.py` fails the build if these disagree.
2. Commit, run `scripts/ui-tests.sh`, then `scripts/release.sh deb`, install
   `dist/notterizmus_<version>_all.deb` and try it; `lintian dist/*.deb` should show
   nothing above pedantic.
3. `scripts/release.sh ppa` signs and uploads (a passphrase prompt appears).
   Launchpad emails on acceptance and build result; tag the commit `v<version>`.

The script refuses uncommitted changes and a `VERSION`/`debian/changelog`
mismatch. A PPA accepts each
version once per Ubuntu series; for another series add an entry like
`1.0.0~questing1` targeting it.
