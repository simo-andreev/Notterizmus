<img src="data/icons/hicolor/256x256/apps/dev.simo.Notterizmus.png" width="96" align="right" alt="">

# Notterizmus 1.0

A GNOME outline editor for book chapter notes. Numbering (`Ⅱ.1.a)`) and tree
connectors (`├ └ │`) are generated automatically; **Copy for TopCoding** puts the
result on the clipboard as HTML, ready to paste into `app.topcoding.bg/assignments`.

Stack: Python 3 + GTK 4 + libadwaita (PyGObject). No other dependencies.

Feature list: [FEATURES.md](FEATURES.md) · Changes: [CHANGELOG.md](CHANGELOG.md)

## Run

```bash
./notterizmus.sh
```

Add it to the GNOME app grid (per-user):

```bash
./install.sh
```

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
| `data/icons/` | App icon (installed by `install.sh`) |

### Adding a block type (e.g. Excalidraw drawings, planned)

1. `model.py`: add a codec to `DATA_CODECS` for the node's `data`.
2. `layout.py`: emit a `Line` for it (like `table`).
3. `export.py`: HTML/plain output for that line kind.
4. `ui/rows.py`: a row widget, registered in `ROW_TYPES`.

## Tests

```bash
python3 -m unittest tests.test_layout tests.test_importer
```
