# Notterizmus 1.0 — Features

A GNOME desktop outline editor for book chapter notes, made to paste cleanly into
TopCoding (`app.topcoding.bg/assignments`).

## Outline and formatting
- Numbered items generated automatically: `Ⅰ)`, `Ⅰ.1)`, `Ⅰ.1.a)`, `Ⅰ.1.a.ⅰ)`, using single-character Unicode Roman numerals.
- Tree connectors (`├ └ │`), with spacer lines drawn automatically.
- Bullets: `•` note, `+` pro, `-` con. Bullets nest by indentation.
- Typing triggers at the start of an item: `# ` numbered, `* ` bullet, `+ ` pro, `- ` con.
- Bold and italic (Ctrl+B / Ctrl+I), on a selection or for text you are about to type.
- Tables with row and column controls, an optional header row, and Tab to move between cells.
- Configurable rules in `~/.config/notterizmus/rules.toml`:
  - numbering format per level
  - connector characters and spacing
  - spacer and blank lines
  - your own bullet markers

## Editing
- Enter adds an item. Tab / Shift+Tab indent and outdent. Alt+↑/↓ moves an item.
- Enter on an empty bullet under `Ⅰ.1.a)` turns it into `Ⅰ.1.b)`. Ctrl+Enter adds the next numbered item at the current level.
- Alt+Insert opens an "add" menu that previews the labels new items will get: next, sub-level, parent-level, bullets, table.
- Clicking an item's prefix opens a menu to change its type, add items next to it, or delete it.
- Right-click menu: spelling suggestions, formatting, item type, add, selection, plain paste, undo/redo.
- Undo/redo across the whole chapter, covering text and structure. Each step is one word, one run of deletions, or one structural change.
- Ctrl+W / Ctrl+Shift+W expands and shrinks the selection: word → item text → item → section → everything.
- Ctrl+A selects all items. Shift+↑/↓ at the first or last line, or Shift+click, extends an item selection.
- Selected items can be copied, cut, deleted, indented or formatted together.
- Multiple cursors: tap Ctrl twice, keep it held, then press ↑/↓. Typing, Backspace, Delete and cursor keys apply at every cursor.

## Clipboard
- **Copy for TopCoding** (Ctrl+Shift+C) copies HTML that TopCoding's editor keeps as-is: spacing, bold, italic and real tables, with plain text as a fallback.
- Ctrl+V works out the outline structure when pasting:
  - from the app's own output
  - from TopCoding's HTML
  - from hand-written notes (`Ⅱ.1)`, `II.1)`, `2.1)`, bullets)

  Pasted items are renumbered to fit where they land.
- Text with no outline markers, such as paragraphs from a PDF, goes into the current item as one paragraph. Words hyphenated across lines are re-joined. A notification offers **One Item per Paragraph**.
- Ctrl+Shift+V pastes as plain text, joined into the current item.
- Items copied inside the app paste back with their exact structure.

## Spelling
- Uses Enchant/Hunspell, the engine GNOME apps use.
- A language button in the header bar. The language is remembered per chapter, and new chapters pick theirs from their text.
- Mixed alphabets: Latin words are checked with an English dictionary and Cyrillic words with a Bulgarian one.
- Suggestions, "Add to Dictionary" (your personal Enchant word list) and "Ignore".

## Files and desktop
- One autosaved `.notz` file (JSON) per book and chapter, under `~/Documents/Notterizmus/<Book>/`.
- The last chapter you had open reopens on start.
- Native GTK 4 / libadwaita app: dark and light themes, keyboard shortcuts dialog (Ctrl+?), About dialog (F1).
- `install.sh` adds the app and its icon to the GNOME app grid. No root needed.

## Planned
- Excalidraw drawings as a block type. The block-type extension points are in place (see README → Adding a block type).
