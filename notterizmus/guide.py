"""The Getting Started chapter: a practice outline that explains the controls (no GTK).

Keys are bold runs, "Try:" exercises start with an italic run. When a control
changes, change it here too; tests/test_guide.py checks every key against README.md.
"""
from __future__ import annotations

from .model import Document, Node, Run
from .rules import Rules

TITLE = "Getting Started"
BOOK = "Notterizmus"
# Words the English dictionary flags in the guide; ignored for the session while it's open.
# "misspeled" stays flagged: it's an exercise.
SPELL_IGNORE = ("Ctrl", "Esc", "PgUp", "PgDn", "Notterizmus", "Notterizmus's", "TopCoding",
                "TopCoding's", "compl", "txt")


def key(text):
    return Run(text, bold=True)


def _runs(parts):
    if isinstance(parts, (str, Run)):
        parts = (parts,)
    return [p if isinstance(p, Run) else Run(p) for p in parts]


def _try(*parts):
    return (Run("Try: ", italic=True), *parts)


def h(text, *children):
    return Node("heading", runs=_runs(text), children=list(children))


def b(text, *children):
    return Node("bullet", runs=_runs(text), marker="dot", children=list(children))


def table(rows, header=True):
    return Node("table", data={"header": header, "rows": [[_runs(c) for c in row] for row in rows]})


def build(rules=None):
    """The guide's root node, using the typing triggers from the given rules."""
    rules = rules or Rules()
    types = [b((key(rules["heading"]["trigger"]), " then Space: a numbered item"))]
    for m in rules["markers"].values():
        if m.get("trigger"):
            types.append(b((key(m["trigger"]), f" then Space: {m.get('label', 'bullet').lower()} {m['symbol']}")))
    con = rules["markers"].get("minus", {}).get("trigger") or "-"
    dot = rules["markers"].get("dot", {}).get("symbol") or "•"
    label = rules.label

    return Node("root", children=[
        h("Welcome to Notterizmus",
          b(("This is a practice chapter, so change anything you like. Opening Getting Started again (",
             key("F1"), ", or from the menu) brings back a fresh copy.")),
          b(("Each item explains a control. Lines that start with ", Run("Try:", italic=True),
             " are exercises to do right there.")),
          b(("Can't remember a key? ", key("Ctrl+Shift+P"), " searches every command by name, runs it, "
             "and shows its key so you learn it on the way.")),
          b(("For real notes, press ", key("Ctrl+N"), " to create a chapter."))),

        h("Writing the outline",
          h("New items",
            b(("Press ", key("Enter"), " to add an item below. In the middle of a line, it splits the text in two.")),
            b(_try("put the cursor at the end of this line, press ", key("Enter"), " and type something."))),
          h("Levels",
            b((key("Tab"), " makes an item a sub-item of the one above it, and ", key("Shift+Tab"),
               " moves it back out.")),
            b(_try("press ", key("Tab"), " in this line, then ", key("Shift+Tab"), "."))),
          h("The next numbered item",
            b((key("Ctrl+Enter"), " adds the next numbered item at this level from anywhere in it: after ",
               label([2, 3]), " comes ", label([2, 4]), ". ", key("Enter"),
               " on an empty bullet does the same, so a second ", key("Enter"), " ends a list of bullets.")),
            b((key("Backspace"), " at the start of an item joins it with the item above. An empty item is deleted.")),
            b(_try("press ", key("Ctrl+Enter"), " here and type a title, then press ", key("Backspace"),
                   " until the new item is gone.")))),

        h("Item types",
          b("Type one of these at the start of an item:", *types),
          b((key("Ctrl+Shift+Space"), " switches the type of the item you're in. Clicking an item's label, "
             f"such as {label([3])} or {dot}, opens a menu with the types, plus adding and deleting.")),
          b("A top-level item can be a bullet too. Bullets can hold bullets and tables, but not numbered items."),
          b(_try("put the cursor at the very start of this line and type ", key(con), " and Space. Then press ",
                 key("Ctrl+Shift+Space"), " a few times."))),

        h("Adding with menus",
          b((key("Alt+Insert"), " opens the add menu: the next item, a sub-item, an item one level up, "
             "bullets or a table. Each choice shows the label the new item will get.")),
          b("Right-click opens the context menu: spelling, formatting, item type, adding, selection, "
            "plain-text paste, and undo and redo."),
          b("In these menus, press a choice's number (1–9, then 0) to pick it."),
          b(_try("press ", key("Alt+Insert"), " here and pick a choice by its number."))),

        h("Selecting and moving",
          b((key("Ctrl+W"), " selects a little more each time: the word, the item's text, the item, the "
             "section, everything. ", key("Ctrl+Shift+W"), " goes back a step.")),
          b((key("Ctrl+A"), " selects all items. ", key("Shift+↑"), " or ", key("Shift+↓"),
             " on the first or last line of an item, or ", key("Shift+click"), ", extends a selection of items.")),
          b("Dragging the mouse from one item to another selects the items in between; within one "
            "item it selects text, as usual."),
          b(("Selected items can be copied (", key("Ctrl+C"), "), cut (", key("Ctrl+X"), "), deleted (",
             key("Delete"), "), indented (", key("Tab"), ") or made bold (", key("Ctrl+B"), ") together. "
             "Delete a numbered item without the items under it, and they move up into its place.")),
          b((key("Alt+↑"), " and ", key("Alt+↓"), " move an item up or down.")),
          b((key("Ctrl+F"), " finds text anywhere in the chapter, tables included. ", key("Enter"), " and ",
             key("Shift+Enter"), " go to the next and previous match, ", key("Esc"), " leaves the cursor on it, "
             "and ", key("Ctrl+H"), " (or ", key("Ctrl+R"), ") also replaces.")),
          b(_try("press ", key("Ctrl+W"), " four times in this line, then ", key("Ctrl+Shift+W"),
                 ". Then press ", key("Alt+↑"), " to move this line up."))),

        h("Formatting and undo",
          b((key("Ctrl+B"), " and ", key("Ctrl+I"), " make the selection bold or italic. With nothing "
             "selected, they apply to what you type next.")),
          b((key("Ctrl+Z"), " undoes one word, one run of deletions or one change to the structure at a "
             "time. ", key("Ctrl+Shift+Z"), " or ", key("Ctrl+Y"), " redoes.")),
          b((key("Ctrl+="), " and ", key("Ctrl+-"), " make the chapter's text larger or smaller (so does ",
             key("Ctrl"), " with the scroll wheel), and ", key("Ctrl+0"), " brings it back to normal. The menu "
             "has the same at its top.")),
          b(_try("double-click a word in this line, press ", key("Ctrl+I"), ", then ", key("Ctrl+Z"), "."))),

        h("Tables",
          b((key("Ctrl+T"), " inserts a table. In a cell, ", key("Tab"),
             " moves to the next cell and adds a row at the end.")),
          b("The buttons above a table add and remove rows and columns, turn the header row on or off, "
            "and delete the table."),
          b((key("Ctrl+D"), " opens a drawing: boxes, arrows, text and freehand lines. Done puts it under the "
             "item as a picture; double-click the picture to change it. Copy above the picture copies only the drawing.")),
          b("Six keys worth remembering:",
            table([
                ["Key", "What it does"],
                [key("Ctrl+Space"), "Complete a word or fix its spelling"],
                [key("Alt+Insert"), "Add an item or a table"],
                [key("Ctrl+Enter"), "Next numbered item"],
                [key("Ctrl+W"), "Select more"],
                [key("Ctrl+Shift+C"), "Copy for TopCoding"],
                [key("Ctrl+?"), "All keyboard shortcuts"],
            ]))),

        h("Spelling and word completion",
          b("The language button in the header bar picks the spelling language or turns checking off. "
            "Latin words are checked in English and Cyrillic words in Bulgarian."),
          b((key("Ctrl+Space"), " completes the word at the cursor with words from this chapter, then from "
             "the book's other chapters, then from the dictionary. Keep typing to narrow the list; ",
             key("Enter"), " or ", key("Tab"), " picks and ", key("Esc"), " closes.")),
          b(("On a misspelled word, ", key("Ctrl+Space"), " lists fixes. Right-click shows them too, with "
             "Add to Dictionary and Ignore.")),
          b(_try("type “compl” at the end of this line and press ", key("Ctrl+Space"), ": ")),
          b(_try("this line has a misspeled word. Put the cursor inside it and press ", key("Ctrl+Space"), "."))),

        h("Multiple cursors",
          b(("Tap ", key("Ctrl"), " twice and keep it held, then press ", key("↑"), " or ", key("↓"),
             " to add a cursor above or below. Typing, ", key("Backspace"), ", ", key("Delete"),
             " and the arrow keys then work at every cursor. ", key("Esc"), " goes back to one cursor.")),
          b(_try("put the cursor at the start of this line, add a cursor on the next line and type “Note: ”.")),
          b("This line gets the same text.")),

        h("Copying and pasting",
          b((key("Ctrl+Shift+C"), " (Copy for TopCoding, in the header bar) copies the whole chapter, formatted. "
             "Paste it into TopCoding's notes editor with ", key("Ctrl+V"), " while Notterizmus is still open.")),
          b((key("Ctrl+V"), " finds the outline structure in what you paste: Notterizmus's own output, "
             "TopCoding's notes, or hand-written notes like II.1) or 2.1). Pasted items are renumbered to fit.")),
          b(("Text without outline markers, such as paragraphs from a PDF, joins the current item. ",
             key("Ctrl+Shift+V"), " always pastes as plain text.")),
          b("Show Plain Text in the menu shows the chapter as plain text.")),

        h("Practicing assessments",
          b("On a TopCoding assessment report, choose Download .txt. Import Assessment Report in the menu brings "
            "the file in and asks which chapter it goes with; you can also drop the file on the Assessments "
            "window. The button at the end of a chapter in the chapter list opens its assessment or, if it has "
            "none, imports one for that chapter without asking."),
          b("Each question starts with a blank answer, to write from memory. Reveal shows the answer you gave, "
            "its score, the sample answer and the feedback; Load My Original Answer puts your answer in the "
            "editor. Answers are saved as you type, and checked for spelling in the chapter's language: "
            "right-click an underlined word for suggestions."),
          b("A revealed score also shows in the question list, in TopCoding's colors: green from 0.8, amber "
            "from 0.5 and red below, which includes a question left unanswered. The original score at the top "
            "is colored by its percentage: green from 80%, amber from 65% and red below. The color button in "
            "the header bar turns the colors off; the scores stay."),
          b((key("Ctrl+PgUp"), " or ", key("Ctrl+PgDn"), " goes to the previous or next question, and ",
             key("F9"), " shows or hides the question list. Drag the edge of the list to make it wider.")),
          b("Finish Attempt keeps your answers in Earlier Attempts, where you can compare them with the sample "
            "answer, and starts a blank attempt.")),

        h("More",
          b((key("Ctrl+N"), " creates a chapter and ", key("Ctrl+O"), " opens one. Each chapter of a book is "
             "its own file, saved automatically.")),
          b(("The chapter list on the left shows each book's chapters in order; click one to open it, or click "
             "a book to fold it. ", key("F9"), " shows or hides the list, and ", key("Ctrl+PgUp"), " or ",
             key("Ctrl+PgDn"), " opens the previous or next chapter of the book. Drag the edge between the "
             "list and the text to make the list wider; double-click the edge for the default width.")),
          b((key("F2"), " (or Chapter Properties in the menu) renames the chapter, changes its number or moves "
             "it to another book; on a book in the list, it renames the book. In the list, drag a chapter or "
             "press ", key("Alt+↑"), " or ", key("Alt+↓"), " to reorder, and ", key("Delete"),
             " moves it to the Trash (Undo brings it back). Right-click shows all of these.")),
          b((key("Ctrl+?"), " lists every keyboard shortcut, and ", key("F1"), " opens this guide again.")),
          b("Edit Formatting Rules in the menu changes the numbering, connectors, spacing and bullet markers."),
          b("Open Notes Folder in the menu shows your chapter files."),
          b("Earlier Versions in the menu lists copies of the chapter kept when you opened it and every 10 "
            "minutes while you edited it. Pick one to see it, and Restore puts it back; Ctrl+Z undoes that.")),
    ])


def document(path, rules=None):
    """A fresh Getting Started document, to be saved at path."""
    return Document(build(rules), BOOK, 0, TITLE, path, lang="en_US")


def keys(root):
    """Every bold run in the guide (the keys it teaches)."""
    out = []
    for n in root.walk():
        cells = [c for row in n.data.get("rows", []) for c in row] if n.kind == "table" else [n.runs]
        out += [r.text for runs in cells for r in runs if r.bold]
    return out
