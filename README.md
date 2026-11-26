<img src="data/icons/hicolor/256x256/apps/dev.simo.Notterizmus.png" width="96" align="right" alt="app logo - a devilish face whit the letter N on its forehead">

&nbsp;

# Notterizmus 1.8

A GNOME outline editor for book chapter notes. Numbering (`Ⅱ.1.a)`) and tree
connectors (`├ └ │`) are generated as you type, and **Copy for TopCoding** puts
the outline on the clipboard as HTML that pastes cleanly into the chapter notes
editor at `app.topcoding.bg/assignments`. Made for personal book notes in
English and Bulgarian; it is not a general word processor or Markdown editor.

Updated 2026-11-17 · Python 3 + GTK 4 + libadwaita · GPL-3.0-or-later ·
[FEATURES.md](FEATURES.md) · [CHANGELOG.md](CHANGELOG.md) ·
[ROADMAP.md](ROADMAP.md) · [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) (briefing for
coding agents)

## Install

From the PPA (updates arrive through Software Updater; uninstall from App Center
or with `sudo apt remove notterizmus`):

```bash
sudo add-apt-repository ppa:simeonandreev/ppa-library
```

```bash
sudo apt install notterizmus
```

The package is built for Ubuntu 26.04 (`resolute`) only for now; 26.10, and a
snap for older releases, are planned (ROADMAP R19, R17). Notes and settings are
kept when the app is removed.

## Using it

New here? Press F1 (or menu → **Getting Started**) for a practice chapter that
walks through the controls; each time you open it, it starts fresh.

1. **New Chapter** (Ctrl+N): enter book, chapter number and optional title.
2. Type the outline. Start an item with `# ` for a numbered item, `* ` `+ ` `- ` `! ` `? `
   for a note, pro, con, important or question bullet. Tab / Shift+Tab change the level.
3. **Copy for TopCoding** (Ctrl+Shift+C), then Ctrl+V in TopCoding's notes editor.
   Bold, italic, spacing and tables come through; keep the app open while pasting.

| Do this | Key |
|---|---|
| New item (splits at the cursor) | Enter |
| Next numbered item at this level (e.g. Ⅰ.1.b after Ⅰ.1.a and its bullets) | Ctrl+Enter, or Enter on an empty bullet |
| Add-component menu (next / sub / parent item, bullets, table, drawing) | Alt+Insert |
| Context menu (spelling, formatting, item type, add, selection, undo) | right-click |
| Make it a sub-item / move it back out | Tab / Shift+Tab |
| Move the item up or down | Alt+↑ / Alt+↓ |
| Spelling fixes and word completion at the cursor (keep typing to filter, Enter or Tab picks) | Ctrl+Space |
| Change item type | Ctrl+Shift+Space, or click its prefix |
| Pick a choice in the Alt+Insert, item or Ctrl+Space popup | its number, 1–9 then 0 (keypad too) |
| Bold / italic | Ctrl+B / Ctrl+I |
| Larger / smaller / normal text (chapter text only; also Ctrl + scroll wheel) | Ctrl+= / Ctrl+- / Ctrl+0 |
| Undo / redo (one word, deletion run, or structural change per step) | Ctrl+Z / Ctrl+Shift+Z (or Ctrl+Y) |
| Expand / shrink selection: word → item text → item → section → all | Ctrl+W / Ctrl+Shift+W |
| Select all items | Ctrl+A |
| Find in the chapter, tables included (Enter / Shift+Enter or Ctrl+G / Ctrl+Shift+G: next / previous match) | Ctrl+F |
| Find and replace (Replace, or Replace All as one undo step) | Ctrl+H or Ctrl+R |
| Select items with the mouse | drag from one item to another |
| Extend item selection | Shift+↑ / Shift+↓ at the first/last line, or Shift+click |
| Selected items: copy, cut, delete, indent, bold | Ctrl+C, Ctrl+X, Delete, Tab, Ctrl+B |
| Add cursors above/below | tap Ctrl twice, keep it held, then ↑ / ↓ (Esc to leave) |
| Paste, detecting outline structure | Ctrl+V |
| Paste as plain text, joined into the current item | Ctrl+Shift+V |
| Insert table | Ctrl+T (in a cell: Tab moves to the next one and adds a row at the end) |
| Insert drawing (Excalidraw; **Done** keeps it, double-click its picture to edit it again) | Ctrl+D |
| Copy one drawing by itself | **Copy** above it, or click it and press Ctrl+C |
| Delete an empty item / join with the line above | Backspace at the start |
| New chapter / open a chapter | Ctrl+N / Ctrl+O |
| Save now (chapters also save by themselves as you type) | Ctrl+S |
| Quit | Ctrl+Q |
| Previous / next chapter of the book | Ctrl+PgUp / Ctrl+PgDn |
| Show or hide the chapter list (books and their chapters, on the left) | F9 |
| Chapter properties: rename, change the number, move to another book (on a book in the list: rename the book) | F2 |
| In the chapter list: reorder, move to Trash, more | drag, or Alt+↑ / Alt+↓; Delete; right-click |
| Resize the chapter list (double-click the edge for the default width) | drag the edge between the list and the text |
| Getting Started: a practice chapter that shows the controls | F1 |
| Practice a TopCoding assessment: import its report, answer from memory, then reveal | menu → **Assessments…** (see below) |
| In the Assessments window: previous / next question; show or hide the question list | Ctrl+PgUp / Ctrl+PgDn; F9 |
| Search every command by name (each shows its key) | Ctrl+Shift+P |
| All shortcuts | Ctrl+? |

Enter on an empty sub-item moves it out one level; on an empty bullet under a
numbered item it becomes that item's next sibling. A top-level item can be a
numbered item or a bullet (`* ` at its start); a bullet that moves up to the top level,
by Shift+Tab or when the item above it is deleted, becomes the next numbered item.

**Pasting in.** Ctrl+V recognises the app's own output, TopCoding's HTML and
hand-written notes (`Ⅱ.1)`, `II.1)`, `2.1)`, `•`/`+`/`-`/`*` bullets nested by
indentation) and renumbers everything; the notification offers **Paste as Plain
Text** to undo that. Text without outline markers, such as paragraphs from a PDF,
goes into the current item as one paragraph with line-break hyphenation removed;
the notification offers **One Item per Paragraph**. A table copied on its own, or
with such text, is added after the item. A copy from TopCoding's notes brings its
drawings along, in their places; a drawing copied by itself is added after the item.

**Practicing assessments.** On a TopCoding assessment report, choose **Download
.txt**, then menu → **Import Assessment Report…** (or drop the file on the
Assessments window). The app suggests the chapter whose title matches the report;
confirm it or pick another (or none). The button at the end of each chapter in the
chapter list opens its assessment, or imports one for that chapter without asking.
Each question starts with a blank answer, to write from memory; **Reveal** shows the
answer you gave, its score, the sample answer and the feedback, and **Load My
Original Answer** puts your answer in the editor (Ctrl+Z takes it back). A revealed
score also shows in the question list, in TopCoding's colors (green from 0.8, amber
from 0.5, red below, an unanswered question included), and the original score at the
top by its percentage (green from 80%, amber from 65%); the color button in the
header bar turns the colors off, and the scores stay. Drag the list's edge to make
it wider. Answers are saved as you type. **Finish Attempt** keeps them in **Earlier
Attempts**, where **Compare with Sample Answer** shows one beside the sample, and
starts a blank attempt. A report downloaded before TopCoding graded it has no scores
or feedback; import the graded download later and choose **Replace**: your drafts
and attempts stay. Right-click a chapter in the list for **Practice Assessment** and
**Import Assessment Report…**. The app reads only the downloaded file; it never
contacts TopCoding and doesn't grade your practice answers.

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
- Drawings are made in [Excalidraw](https://excalidraw.com), which runs inside the app
  (offline) and needs WebKitGTK (`gir1.2-webkit-6.0`, installed with the package).
  **Copy for TopCoding** sends a chapter that has a drawing as the editor's own
  clipboard format (TopCoding takes drawings in no other), packed both the way
  Chrome and the way Firefox read it; TopCoding's editor was checked to accept it,
  but a real Ctrl+V from the app into TopCoding has not been confirmed yet. If the
  drawing doesn't arrive, the text and tables still do. The other way, Ctrl+V
  reads the drawings of a copy from TopCoding out of that same format; that hasn't
  been tried with a real copy either, and if it fails, the text and tables paste
  from the HTML as before.
  Excalidraw's shape library, Mermaid import and CJK hand-drawn font are left out.
- Undo history lasts until the chapter is closed. For older states, **Earlier
  Versions** in the menu has copies kept when the chapter was opened and every
  10 minutes while it was edited: all from the last day, then one per hour for a
  week, one per day for three months and one per week after that.

## Files

| What | Where |
|---|---|
| Chapter notes, one autosaved JSON file per book + chapter | `<Documents>/Notterizmus/<Book>/<NN> <Title>.notz` — `<Documents>` is the localized XDG folder, e.g. `~/Документи` |
| Formatting rules (optional) | `~/.config/notterizmus/rules.toml`, created from [`rules.example.toml`](notterizmus/rules.example.toml) by menu → **Edit Formatting Rules**; apply with **Reload Formatting Rules** |
| Last open chapter, spelling choices | `~/.config/notterizmus/state.json` |
| Getting Started practice copy, rewritten each time it's opened | `~/.local/share/notterizmus/Getting Started.notz` |
| Earlier versions of each chapter (thinned with age, kept for good) | `~/.local/share/notterizmus/backups/<Book>/<NN> <Title>/` |
| Imported assessment reports and your practice on them: each report's `.txt` as downloaded, what was read from it and its chapter (`report.json`), the attempt in progress (`draft.json`) and finished attempts (`attempts/<UTC time>Z.json`) | `<Documents>/Notterizmus/.assessments/<title>_<completed>/` (hidden, so it isn't listed as a book; to remove an assessment, delete its folder) |

Rules cover numbering format per level, connector characters, spacing, spacer
and blank lines, and your own bullet markers.

## Development

```bash
./notterizmus.sh
```

```bash
python3 -m unittest discover -s tests -t .
```

The UI tests in `tests/ui` drive the real editor on a private GTK Broadway display
(package `libgtk-4-bin`), so no window appears and your own settings and notes aren't
touched. A small client presses real keys and drags the mouse through it, so
shortcuts, Escape, focus and mouse selection are tested as you'd use them, and paces
frames like a 60 Hz screen for the frame-by-frame checks. A run fails if a test fails,
if the app raises an exception in a callback, or if GTK or Python prints a warning.
Each run has its own display in a scratch folder, so several can go at once.
`NOTTERIZMUS_UI_BACKEND=weston` runs them on a headless Weston instead
(`sudo apt install weston`), without the real keyboard and mouse input.

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
| `notterizmus/export.py`, `notterizmus/lexical.py` | Lines → HTML for TopCoding, and plain text; lines → the editor's own clipboard nodes (used when there is a drawing), and those nodes back into pasted items |
| `notterizmus/importer.py` | Pasted HTML/text → outline nodes |
| `notterizmus/spell.py` | Enchant spell checker (ctypes) |
| `notterizmus/completion.py` | Ctrl+Space word completion (chapter, book, dictionary) |
| `notterizmus/guide.py` | The Getting Started chapter; update it when a control changes |
| `notterizmus/paths.py` | Documents folder (also inside a snap), guide and metainfo paths |
| `notterizmus/gpu.py` | Drawing with the GPU on NVIDIA's driver: what WebKit and GTK are told before they start |
| `notterizmus/files.py` | Writing a file in one step: on the disk before it replaces the old one, with its permissions kept |
| `notterizmus/state.py` | What the window remembers between runs (`state.json`); a broken file can't stop the app |
| `notterizmus/library.py`, `notterizmus/ui/sidebar.py` | Books and chapters in the notes folder; the chapter list |
| `notterizmus/backups.py` | Earlier versions of chapters: when copies are kept, where, and how many |
| `notterizmus/commands.py`, `notterizmus/ui/command_search.py` | The commands and their keys (used by the accelerators, Search Commands and the Shortcuts dialog) and command matching; the Search Commands dialog |
| `notterizmus/find.py`, `notterizmus/ui/findbar.py` | Find and replace: matching, and the find bar |
| `notterizmus/assessment_txt.py` | Reading TopCoding's assessment report `.txt` (graded or not); errors name the line and question (no GTK) |
| `notterizmus/assessments.py` | Imported reports and practice attempts in the notes folder: imports, duplicates, drafts, attempts, chapter links, crash recovery (no GTK) |
| `notterizmus/ui/assessments_window.py`, `assessment_page.py`, `attempts.py` | The Assessments window: the list and importing; practicing one; Earlier Attempts |
| `tests/`, `tests/ui/`, `scripts/ui-tests.sh` | Unit tests (no GTK); UI tests and their runner |
| `scripts/measure-drawing-stroke.py` | Times a pen stroke in the drawing window on your own display |
| `notterizmus/ui/outline.py` | Editor widget: building and refreshing rows, focus, scrolling |
| `notterizmus/ui/outline_*.py` | The editor's mixins, one theme each: `undo`, `keys`, `items`, `selection`, `clipboard`, `menus`, `assist` (spelling, Ctrl+Space), `carets` (multi-cursor) |
| `notterizmus/ui/rows.py`, `richtext.py` | Row widgets (text, table, drawing) and the rich-text view |
| `notterizmus/drawing.py`, `notterizmus/ui/drawing_web.py` | Drawing blocks: the scene, its export and the preview cache (no GTK); the Excalidraw window and preview renderer (WebKitGTK) |
| `web/drawing/`, `scripts/build-drawing-editor.sh`, `notterizmus/drawing_web/` | Source of the embedded Excalidraw page, its build script (Node.js), and the built page that ships with the app |
| `notterizmus/ui/window.py`, `app.py` | Window: building it, the open chapter, spelling, copy and find, opening the Assessments window; the app and its accelerators |
| `notterizmus/ui/helpers.py` | Small shared UI helpers, and `WORKER`: the thread that reads and writes assessments' files |
| `notterizmus/ui/window_*.py` | The window's mixins: `saving` (autosave, changes on disk), `chapters` (new, open, rename, reorder, Trash), `dialogs`, `zoom`, `sizing` (the chapter list's width) |
| `data/` | Icons, desktop entry, AppStream metadata, `.notz` MIME type |
| `debian/`, `scripts/release.sh` | Ubuntu packaging and the PPA release script |

### Adding a block type (as tables and drawings are)

1. `model.py`: add a codec to `DATA_CODECS` for the node's `data`.
2. `layout.py`: emit a `Line` for it (like `table` and `drawing`).
3. `export.py`: HTML and plain-text output for that line kind (`lexical.py` too, if TopCoding's editor has a node for it).
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
   dialog show them), a section in `CHANGELOG.md` (an `## Unreleased` section
   collects changes between releases and becomes it; `scripts/release.sh` refuses
   to build while one is there), the man page header in
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
mismatch. A PPA accepts each version once per Ubuntu series. To offer a release
on another series, copy it there on Launchpad (the PPA's **Copy packages**,
keeping the existing binaries), as ROADMAP R19 plans; an upload built for that
series instead needs a version like `1.4.2~stonking1` targeting it.
