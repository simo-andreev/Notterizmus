# Notterizmus 1.8 — Features

A GNOME desktop outline editor for book chapter notes, made to paste cleanly into
TopCoding (`app.topcoding.bg/assignments`).

## Outline and formatting
- Numbered items generated automatically: `Ⅰ)`, `Ⅰ.1)`, `Ⅰ.1.a)`, `Ⅰ.1.a.ⅰ)`, using single-character Unicode Roman numerals.
- Tree connectors (`├ └ │`), with spacer lines drawn automatically.
- Bullets: `•` note, `+` pro, `-` con, `!` important, `?` question. Bullets nest by indentation.
- Typing triggers at the start of an item: `# ` numbered, `* ` bullet, `+ ` pro, `- ` con, `! ` important, `? ` question. Ctrl+Shift+Space cycles the type. A top-level item can be numbered or a bullet.
- Bold and italic (Ctrl+B / Ctrl+I), on a selection or for text you are about to type.
- Tables with row and column controls, an optional header row, and Tab to move between cells.
- Drawings (Ctrl+D, the menu, Alt+Insert or Search Commands): [Excalidraw](https://excalidraw.com) opens inside the app, offline. **Done** puts the drawing under the item as a picture; **Edit Drawing** or a double-click opens it again. **Copy** above a drawing (or a click on it and Ctrl+C) copies that drawing alone, for TopCoding or another chapter. Adding, changing and deleting a drawing are undo steps. The drawing itself (not the picture) is saved in the chapter file.
- Configurable rules in `~/.config/notterizmus/rules.toml`:
  - numbering format per level
  - connector characters and spacing
  - spacer and blank lines
  - your own bullet markers

## Learning the controls
- **Search Commands** (Ctrl+Shift+P, or the menu): type a few letters of any command, in any order (“move up”, “rename”, “table”), and run it with Enter. Each result shows its key. Commands that are keys in the editor (indent, move item, Ctrl+Space…) do exactly what the key does.
- **Getting Started** (F1, the menu, or the start page) opens a practice chapter that explains each control as an outline, with exercises to try in place. Each time you open it, it starts fresh; it's kept apart from your notes.

## Editing
- Enter adds an item. Tab / Shift+Tab indent and outdent. Alt+↑/↓ moves an item.
- Enter on an empty bullet under `Ⅰ.1.a)` turns it into `Ⅰ.1.b)`. Ctrl+Enter adds the next numbered item at the current level.
- Alt+Insert opens an "add" menu that previews the labels new items will get: next, sub-level, parent-level, bullets, table, drawing.
- The Alt+Insert, item-prefix and Ctrl+Space popups number their first ten choices 1–9, 0; pressing the digit (top row or keypad) picks it.
- Clicking an item's prefix opens a menu to change its type, add items next to it, or delete it.
- Right-click menu: spelling suggestions, formatting, item type, add, selection, plain paste, undo/redo.
- Find (Ctrl+F) and replace (Ctrl+H or Ctrl+R) across the chapter, table cells included: every match highlighted, “3 of 12”, Enter / Shift+Enter (or Ctrl+G / Ctrl+Shift+G) for the next and previous match, Match Case and Whole Words (Cyrillic too). Replacing keeps the bold or italic of the replaced text; Replace All is one undo step. Esc closes the bar from anywhere in it (leaving the cursor on the match) or from the text (leaving the cursor where it is).
- Undo/redo across the whole chapter, covering text and structure. Each step is one word, one run of deletions, or one structural change.
- Ctrl+W / Ctrl+Shift+W expands and shrinks the selection: word → item text → item → section → everything.
- Ctrl+A selects all items. Shift+↑/↓ at the first or last line, or Shift+click, extends an item selection.
- Dragging the mouse from one item to another selects whole items (within one item it selects text). Past the top or bottom of the window the outline scrolls and the selection keeps growing.
- Selected items can be copied, cut, deleted, indented or formatted together. Only the selected items are affected: delete or cut a numbered item without the items under it, and they move up into its place.
- Multiple cursors: tap Ctrl twice, keep it held, then press ↑/↓. Typing, Backspace, Delete and cursor keys apply at every cursor.
- The editor's Ctrl and Alt shortcuts (Ctrl+A, Ctrl+B, Ctrl+Z and the rest) work on non-Latin keyboard layouts too, such as Bulgarian.

## Clipboard
- **Copy for TopCoding** (Ctrl+Shift+C) copies HTML that TopCoding's editor keeps as-is: spacing, bold, italic and real tables, with plain text as a fallback. A chapter with drawings is also offered in the editor's own clipboard format, which carries them as Excalidraw scenes (`[Drawing]` in the plain text).
- Ctrl+V works out the outline structure when pasting:
  - from the app's own output
  - from TopCoding's HTML; a copy there that has a drawing is read from the editor's own clipboard format instead, so the drawings arrive too (Chrome and Firefox)
  - from hand-written notes (`Ⅱ.1)`, `II.1)`, `2.1)`, bullets)

  Pasted items are renumbered to fit where they land.
- Text with no outline markers, such as paragraphs from a PDF, goes into the current item as one paragraph. Words hyphenated across lines are re-joined. A notification offers **One Item per Paragraph**.
- A table copied on its own (from a web page, say), or together with such text, is added after the current item. So is a drawing copied by itself in TopCoding.
- Ctrl+Shift+V pastes as plain text, joined into the current item.
- Items copied inside the app paste back with their exact structure.

## Spelling
- Uses Enchant/Hunspell, the engine GNOME apps use.
- A language button in the header bar. The language is remembered per chapter, and new chapters pick theirs from their text.
- Mixed alphabets: Latin words are checked with an English dictionary and Cyrillic words with a Bulgarian one.
- Suggestions, "Add to Dictionary" (your personal Enchant word list) and "Ignore", from the right-click menu or Ctrl+Space.

## Word completion
- Ctrl+Space completes the word at the cursor: words from the open chapter first, then from the book's other chapters, then from the spelling dictionary (English or Bulgarian by alphabet).
- Typing continues into the text and narrows the list; Enter or Tab picks, Space or Esc closes. Works in table cells too.
- Completions keep your capitalisation and only appear when they add at least two letters.

## Practicing assessments
- Import a TopCoding assessment report from its downloaded `.txt` (menu → **Import Assessment Report…**, a chapter's right-click menu, or by dropping the file on the Assessments window). Graded and ungraded downloads both work; a file that isn't a whole report is refused with the line and question at fault, and nothing is imported.
- Each report goes with a chapter: the app suggests the one whose title matches (case, punctuation and small typos aside) and you confirm it. It follows the chapter when it's renamed, renumbered or moved.
- The practice page: the questions in a list showing which you've drafted and revealed, a blank editor for each answer with live word and character counts, and progress for the attempt. **Reveal** shows your original answer with its score, the sample answer and the feedback; **Load My Original Answer** puts your answer in the editor, asking first if there's text, and Ctrl+Z takes it back. Ctrl+PgUp / Ctrl+PgDn go between questions; F9 shows or hides the list.
- Answers are saved as you type (800 ms after you stop), in the background. **Finish Attempt** keeps the attempt and starts a blank one; **Earlier Attempts** shows each attempt's answer, read-only, beside the sample answer if you like.
- Importing the same report again (same title and completion time) asks: **Skip**, or **Replace**, which keeps your drafts and attempts, so the graded download can follow an ungraded one.
- Everything is kept in a hidden `.assessments` folder in your notes folder, written in one step so a crash can't leave a half-written file; a draft another computer changed (through a sync tool) is kept as an attempt rather than overwritten.

## Files and desktop
- One autosaved `.notz` file (JSON) per book and chapter, under `Notterizmus/<Book>/` in your Documents folder (localized, e.g. `~/Документи`).
- Chapter Properties (F2): rename a chapter, change its number (a number another chapter has is swapped with it) or move it to another book. On a book in the list, F2 renames the book: its folder and the name stored in its chapters.
- Reorder chapters by dragging them in the list or with Alt+↑ / Alt+↓. Chapter numbers are the book's own, so reordering hands out the existing numbers in the new order (1, 2, 5 stay 1, 2, 5). Delete moves a chapter to the Trash, with Undo.
- The chapter list on the left (F9) shows every book in the notes folder with its chapters in order; click a chapter to open it, click a book to fold it. Ctrl+PgUp / Ctrl+PgDn open the previous or next chapter of the book. Drag the edge between the list and the text to resize it (the width is remembered; double-click the edge for the default). In a window too narrow for the list and the text side by side, the list slides over the text.
- Earlier Versions (menu): a copy of each chapter is kept when you open it and every 10 minutes while you edit, outside your notes folder. Older copies are thinned, not dropped: all from the last day, then one per hour for a week, one per day for three months and one per week after that. The dialog groups them by day and previews each one; Restore puts it in the editor, and Ctrl+Z takes it back. Copies follow a chapter when it's renamed or moved.
- If another program changes the open chapter's file (a sync tool, a second machine), the app asks before saving over it: Reload takes that version, and Ctrl+Z brings yours back; Keep Mine saves yours. The other version stays in Earlier Versions either way.
- The last chapter you had open reopens on start.
- Chapters saved by a newer version open safely: block types this version doesn't know are shown as a read-only note, kept unchanged in the file, and left out of Copy for TopCoding.
- Text size: Ctrl+= / Ctrl+- / Ctrl+0, Ctrl + scroll wheel, or the “− 100% +” row at the top of the menu (60–250%, remembered). Only the chapter's text changes size; the rest of the window doesn't.
- Native GTK 4 / libadwaita app: dark and light themes, keyboard shortcuts dialog (Ctrl+?), About dialog in the menu.
- `install.sh` adds the app and its icon to the GNOME app grid. No root needed.

## Planned
- Confirming real pastes of drawings in both directions: a chapter with a drawing from the app into TopCoding in Chrome, and a copy from TopCoding back into the app (see README → Known limits).
- Everything else planned is in [ROADMAP.md](ROADMAP.md).
