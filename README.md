<img src="data/icons/hicolor/256x256/apps/dev.simo.Notterizmus.png" width="96" align="right" alt="">

# Notterizmus 1.0

A GNOME outline editor for book chapter notes. Numbering (`Ⅱ.1.a)`) and tree
connectors (`├ └ │`) are generated automatically; **Copy for TopCoding** puts the
result on the clipboard as HTML, ready to paste into `app.topcoding.bg/assignments`.

Stack: Python 3 + GTK 4 + libadwaita (PyGObject). No other dependencies.

Feature list: [FEATURES.md](FEATURES.md) · Changes: [CHANGELOG.md](CHANGELOG.md)

## Install

From the PPA (updates arrive through Software Updater; uninstall from App Center
or with `sudo apt remove notterizmus`):

```bash
sudo add-apt-repository ppa:simeonandreev/ppa-library
```

```bash
sudo apt install notterizmus
```

Requires Ubuntu 25.10 or newer (libadwaita 1.8+). Your notes in
`~/Documents/Notterizmus` and settings in `~/.config/notterizmus` are kept when
the app is removed.

## Run from the source folder (development)

```bash
./notterizmus.sh
```

`./install.sh` adds this checkout to the app grid for your user only, and
`./install.sh --uninstall` removes it. Don't keep it alongside the packaged
app, or the app appears twice.

## Writing notes

| Do this | Key |
|---|---|
| New item (splits at the cursor) | Enter |
| Next numbered item at this level (e.g. Ⅰ.1.b after Ⅰ.1.a and its bullets) | Ctrl+Enter, or Enter on an empty bullet |
| Add-component menu (next / sub / parent item, bullets, table) | Alt+Insert |
| Context menu (spelling, formatting, item type, add, selection, undo) | right-click |
| Make it a sub-item / move it back out | Tab / Shift+Tab |
| Move the item up or down | Alt+↑ / Alt+↓ |
| Change item type | Ctrl+Space, or click its prefix |
| Numbered item | type `# ` at the start |
| Bullet `•`, pro `+`, con `-` | type `* `, `+ `, `- ` at the start |
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
| Copy for TopCoding | Ctrl+Shift+C, then Ctrl+V in TopCoding |

Enter on an empty sub-item moves it out one level; on an empty bullet under a
numbered item it becomes that item's next sibling. Items at the top level are
always numbered.

Pasting recognises the app's own output, TopCoding's HTML and hand-written notes
(`Ⅱ.1)`, `II.1)`, `2.1)`, `•`/`+`/`-`/`*` bullets nested by indentation), and
renumbers everything. After a structured paste, the notification offers
**Paste as Plain Text** to undo it and paste the text into one item instead.
Text without any outline markers (e.g. paragraphs from a PDF) goes into the
current item as one paragraph, re-joining words hyphenated across lines; the
notification offers **One Item per Paragraph** to split it at blank lines.

Spell checking uses Enchant/Hunspell, the engine GNOME apps use. The language
button in the header bar (e.g. `EN-US`) switches language or turns checking off;
the same list is in the right-click menu under Spelling. A new chapter picks its
language from its text, and the choice is saved in the chapter file. Words in the
other alphabet are checked automatically with a matching dictionary (English for
Latin words, Bulgarian for Cyrillic), so mixed notes work. "Add to Dictionary"
goes to your personal Enchant word list.

## Files

One file per book + chapter:
`~/Documents/Notterizmus/<Book>/<NN> <Chapter title>.notz` (JSON). Changes
autosave. The last chapter you had open reopens on start.

## Formatting rules

Menu → **Edit Formatting Rules** creates `~/.config/notterizmus/rules.toml` from
[`notterizmus/rules.example.toml`](notterizmus/rules.example.toml). There you can
change numbering formats per level, connector characters, spacing, and blank or
spacer lines, and add your own bullet markers. Then use **Reload Formatting Rules**.

## Code layout

| File | Role |
|---|---|
| `notterizmus/model.py` | Node tree, tree operations, `.notz` load/save (no GTK) |
| `notterizmus/rules.py` | Defaults, user overrides, numbering formats |
| `notterizmus/layout.py` | Tree → lines with labels and connectors |
| `notterizmus/export.py` | Lines → HTML (for TopCoding's Lexical editor) and plain text |
| `notterizmus/importer.py` | Pasted HTML/text → outline nodes |
| `notterizmus/spell.py` | Enchant spell checker (ctypes) |
| `notterizmus/ui/` | GTK widgets: outline editor, row types, window |
| `data/` | Icons, desktop entry, AppStream metadata, `.notz` file type |
| `debian/` | Debian packaging for the Launchpad PPA |
| `scripts/release.sh` | Builds the `.deb` / signed source package and uploads to the PPA |

### Adding a block type (e.g. Excalidraw drawings, planned)

1. `model.py`: add a codec to `DATA_CODECS` for the node's `data`.
2. `layout.py`: emit a `Line` for it (like `table`).
3. `export.py`: HTML/plain output for that line kind.
4. `ui/rows.py`: a row widget, registered in `ROW_TYPES`.

## Releasing to the PPA

One-time setup:

1. Install the packaging tools:
   `sudo apt install debhelper dh-python devscripts dput`
2. Create a signing key for the maintainer identity in `debian/changelog`, with
   an encryption subkey (Launchpad confirms keys by sending an encrypted email):
   `gpg --quick-generate-key "Simo Andreev <simeon.zlatanov.andreev@pm.me>" rsa4096 sign 3y`
   then `gpg --quick-add-key <FINGERPRINT> rsa4096 encr 3y`
3. Publish it: `gpg --keyserver keyserver.ubuntu.com --send-keys <FINGERPRINT>`,
   add the fingerprint at Launchpad → your profile → OpenPGP keys, and confirm
   the encrypted email Launchpad sends.

Each release:

1. Bump `VERSION` in `notterizmus/__init__.py`, add a `<release>` to
   `data/dev.simo.Notterizmus.metainfo.xml`, a section to `CHANGELOG.md`, and a
   `debian/changelog` entry (`dch -v 1.0.1 "What changed"`, then
   `dch -r -D resolute`).
2. Commit, then try it locally: `scripts/release.sh deb` and install
   `dist/notterizmus_<version>_all.deb`.
3. Upload: `scripts/release.sh ppa`. Launchpad builds it within minutes to an
   hour and emails you; users then get the update in Software Updater.

A PPA only accepts each version once per Ubuntu series. To build the same
release for another series (e.g. `questing`), add a changelog entry with a
suffixed version such as `1.0.0~questing1` targeting that series.

## Tests

```bash
python3 -m unittest tests.test_layout tests.test_importer
```
