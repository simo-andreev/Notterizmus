"""The app's commands and their keys, and command search (Ctrl+Shift+P) (no GTK).

COMMANDS is the one list of commands (CR37 in CODE_REVIEW.md): the app's accelerators,
Search Commands (ui/command_search.build) and the Shortcuts dialog (SHORTCUTS) are made
from it, and tests/test_commands.py checks README.md and the guide against it.

Search: each word typed must appear in the command's title or keywords (any order, any
case); matches at the start of the title or of a word rank first.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Command:
    title: str
    run: object = None              # callable, run after the search closes
    accel: str = ""                 # GTK accelerator to show, e.g. "<Control>n"
    keywords: str = ""              # other words it can be found by
    section: str = ""               # shown dimmed: Chapter, Item, Text, …
    order: int = field(default=0)   # position when nothing is typed


def _words(text):
    return text.casefold().replace("…", " ").replace("/", " ").split()


def score(query, cmd):
    """Lower is better; None if cmd doesn't match."""
    q = _words(query)
    if not q:
        return cmd.order
    title = cmd.title.casefold()
    title_words = _words(cmd.title)
    other = _words(cmd.keywords) + _words(cmd.section)
    total = 0
    for w in q:
        if any(t.startswith(w) for t in title_words):
            total += 0 if title.startswith(w) else 1
        elif w in title:
            total += 3
        elif any(t.startswith(w) for t in other):
            total += 4
        else:
            return None
    return total * 1000 + len(cmd.title)


def search(query, commands):
    """Matching commands, best first."""
    ranked = [(s, i, c) for i, c in enumerate(commands) if (s := score(query, c)) is not None]
    ranked.sort(key=lambda t: (t[0], t[1]))
    return [c for _s, _i, c in ranked]


# -- the command table ------------------------------------------------------------------------

@dataclass(frozen=True)
class Spec:
    """One command. action is "win.…", "ed.…" or "app.…", with target (a string) when it
    takes one; "" means a key the editor handles, which Search Commands replays on the
    item the cursor is in. accels are installed as the app's accelerators (for win. and
    app. actions); shown is the key Search Commands shows when it has no accelerator (the
    editor's own keys). needs: "doc" (a chapter is open) or "book" (a chapter of a book).
    each: one command per "marker", "kind" or "language", made by Search Commands, whose
    title then holds {label}. listed: False keeps it out of Search Commands."""
    title: str
    action: str = ""
    section: str = ""
    keywords: str = ""
    accels: tuple = ()
    shown: str = ""
    target: str | None = None
    needs: str = ""
    each: str = ""
    listed: bool = True

    @property
    def key(self):
        """The key shown for it: its first accelerator, else `shown`."""
        return self.accels[0] if self.accels else self.shown


def _replay(title, key, section, keywords=""):
    return Spec(title, "", section, keywords, shown=key, needs="doc")


COMMANDS = (
    Spec("New Chapter", "win.new", "Chapter", "create book", ("<Ctrl>n",)),
    Spec("Open Chapter…", "win.open", "Chapter", "file", ("<Ctrl>o",)),
    Spec("Previous Chapter", "win.prev-chapter", "Chapter", "back book", ("<Ctrl>Page_Up",), needs="book"),
    Spec("Next Chapter", "win.next-chapter", "Chapter", "forward book", ("<Ctrl>Page_Down",), needs="book"),
    Spec("Chapter Properties…", "win.rename", "Chapter", "rename number title move book", ("F2",), needs="book"),
    Spec("Earlier Versions…", "win.versions", "Chapter", "backup restore history undo", needs="book"),
    Spec("Assessments…", "win.assessments", "Assessment", "topcoding practice test quiz exam report attempt"),
    Spec("Import Assessment Report…", "win.import-assessment", "Assessment", "topcoding txt download practice"),
    Spec("Copy for TopCoding", "win.copy", "Chapter", "export html paste clipboard", ("<Ctrl><Shift>c",)),
    Spec("Show Plain Text", "win.show-plain", "Chapter", "export preview"),
    Spec("Save", "win.save", "Chapter", accels=("<Ctrl>s",)),
    Spec("Show or Hide the Chapter List", "win.sidebar", "List", "sidebar books panel", ("F9",)),
    Spec("Larger Text", "win.zoom-in", "Text size", "zoom in bigger font", ("<Ctrl>equal", "<Ctrl>plus", "<Ctrl>KP_Add")),
    Spec("Smaller Text", "win.zoom-out", "Text size", "zoom out font", ("<Ctrl>minus", "<Ctrl>KP_Subtract")),
    Spec("Normal Text Size", "win.zoom-reset", "Text size", "zoom reset 100 font", ("<Ctrl>0", "<Ctrl>KP_0")),
    Spec("Undo", "ed.undo", "Text", shown="<Ctrl>z", needs="doc"),
    Spec("Redo", "ed.redo", "Text", shown="<Ctrl><Shift>z", needs="doc"),
    Spec("Bold", "ed.bold", "Text", "format strong", shown="<Ctrl>b", needs="doc"),
    Spec("Italic", "ed.italic", "Text", "format emphasis", shown="<Ctrl>i", needs="doc"),
    _replay("Spelling Fixes and Word Completion", "<Ctrl>space", "Text", "complete suggest autocomplete"),
    Spec("Paste as Plain Text", "ed.paste-plain", "Text", shown="<Ctrl><Shift>v", needs="doc"),
    Spec("Find", "win.find", "Find", "search look", ("<Ctrl>f",), needs="doc"),
    Spec("Find and Replace", "win.replace", "Find", "search substitute change", ("<Ctrl>h", "<Ctrl>r"), needs="doc"),
    Spec("Find Next", "win.find-next", "Find", accels=("<Ctrl>g",), needs="doc"),
    Spec("Find Previous", "win.find-prev", "Find", accels=("<Ctrl><Shift>g",), needs="doc"),
    _replay("Add Menu", "<Alt>Insert", "Add", "insert new item"),
    Spec("Next Numbered Item", "ed.add", "Add", "heading sibling", shown="<Ctrl>Return", target="next", needs="doc"),
    Spec("Sub-item", "ed.add", "Add", "child nested numbered", target="child", needs="doc"),
    Spec("Parent-level Item", "ed.add", "Add", "up level numbered", target="parent", needs="doc"),
    Spec("Add {label}", "ed.add", "Add", "bullet", needs="doc", each="marker"),
    Spec("Insert Table", "win.insert-table", "Add", needs="doc"),
    Spec("Insert Drawing", "win.insert-drawing", "Add", "excalidraw graph diagram sketch picture",
         shown="<Ctrl>d", needs="doc"),
    Spec("Make It {label}", "ed.set-kind", "Item", "type change convert", needs="doc", each="kind"),
    _replay("Cycle Item Type", "<Ctrl><Shift>space", "Item", "change kind"),
    _replay("Indent Item", "Tab", "Item", "sub level deeper"),
    _replay("Outdent Item", "<Shift>Tab", "Item", "level up shallower"),
    _replay("Move Item Up", "<Alt>Up", "Item", "reorder"),
    _replay("Move Item Down", "<Alt>Down", "Item", "reorder"),
    Spec("Delete Item", "ed.delete-item", "Item", "remove", needs="doc"),
    Spec("Expand Selection", "ed.select-scope", "Selection", shown="<Ctrl>w", needs="doc"),
    _replay("Shrink Selection", "<Ctrl><Shift>w", "Selection"),
    Spec("Select All Items", "ed.select-all", "Selection", shown="<Ctrl>a", needs="doc"),
    Spec("Check Spelling", "win.spell", "Spelling", "spell checker on off"),
    Spec("Spelling Language: {label}", "win.spell-lang", "Spelling", "dictionary", each="language"),
    Spec("Edit Formatting Rules", "win.edit-rules", "Settings", "numbering connectors bullets"),
    Spec("Reload Formatting Rules", "win.reload-rules", "Settings"),
    Spec("Open Notes Folder", "win.open-folder", "Settings", "files documents"),
    Spec("Getting Started", "win.guide", "Help", "tutorial learn practice", ("F1",)),
    Spec("Keyboard Shortcuts", "win.shortcuts", "Help", "keys help", ("<Ctrl>question",)),
    Spec("About Notterizmus", "win.about", "Help", "version"),
    Spec("Search Commands", "win.commands", "Help", accels=("<Ctrl><Shift>p",), listed=False),
    Spec("Quit", "app.quit", accels=("<Ctrl>q",), listed=False),
)


def command(action, target=None):
    """The Spec for an action (and target)."""
    return next(c for c in COMMANDS if c.action == action and c.target == target)


def accelerators():
    """[(action, [accelerators])] the app installs: its window's and its own actions."""
    return [(c.action, list(c.accels)) for c in COMMANDS
            if c.accels and c.action.split(".", 1)[0] in ("win", "app")]


# -- the Shortcuts dialog (Ctrl+?) -----------------------------------------------------------

# (section, [(label, keys)]): each key is an action of COMMANDS, which stands for its first
# accelerator or shown key, or a key itself ("<Ctrl>r"), for the editing keys that are no
# command (Return, BackSpace, Escape, …) and a command's second accelerator.
SHORTCUTS = (
    ("Outline", [
        ("New item (splits at the cursor)", ("Return",)),
        ("Next numbered item at this level", ("ed.add:next",)),
        ("Add component menu", ("<Alt>Insert",)),
        ("Indent / outdent", ("Tab", "<Shift>Tab")),
        ("Move item up / down", ("<Alt>Up", "<Alt>Down")),
        ("Cycle item type", ("<Ctrl><Shift>space",)),
        ("Join with the item above", ("BackSpace",)),
    ]),
    ("Enter on an empty item", [
        ("Bullet under Ⅰ.1.a) becomes Ⅰ.1.b)", ("Return",)),
    ]),
    ("Selection", [
        ("Expand / shrink selection (word, item, section…)", ("ed.select-scope", "<Ctrl><Shift>w")),
        ("Select all items", ("ed.select-all",)),
        ("Extend item selection", ("<Shift>Up", "<Shift>Down")),
    ]),
    ("Multiple cursors", [
        ("Add cursor above / below (tap Ctrl twice, hold, then arrow)", ("<Ctrl>Up", "<Ctrl>Down")),
        ("Back to one cursor", ("Escape",)),
    ]),
    ("Text size", [
        ("Larger / smaller text (also Ctrl + scroll wheel)", ("win.zoom-in", "win.zoom-out")),
        ("Normal text size", ("win.zoom-reset",)),
    ]),
    ("Find", [
        ("Find in the chapter", ("win.find",)),
        ("Find and replace", ("win.replace", "<Ctrl>r")),
        ("Next / previous match", ("win.find-next", "win.find-prev")),
    ]),
    ("Text", [
        ("Spelling fixes and word completion", ("<Ctrl>space",)),
        ("Bold", ("ed.bold",)),
        ("Italic", ("ed.italic",)),
        ("Undo / redo", ("ed.undo", "ed.redo")),
        ("Paste (detects outline structure)", ("<Ctrl>v",)),
        ("Paste as plain text", ("ed.paste-plain",)),
    ]),
    ("Tables", [
        ("Insert table", ("<Ctrl>t",)),
        ("Next / previous cell", ("Tab", "<Shift>Tab")),
    ]),
    ("Drawings", [
        ("Insert drawing (Excalidraw)", ("win.insert-drawing",)),
    ]),
    ("File", [
        ("New chapter", ("win.new",)),
        ("Open chapter", ("win.open",)),
        ("Save", ("win.save",)),
        ("Previous / next chapter of the book", ("win.prev-chapter", "win.next-chapter")),
        ("Chapter properties: rename, number, book (on a book: rename it)", ("win.rename",)),
        ("Copy for TopCoding", ("win.copy",)),
    ]),
    ("Assessments window", [
        ("Previous / next question", ("<Ctrl>Page_Up", "<Ctrl>Page_Down")),
        ("Show or hide the question list", ("F9",)),
    ]),
    ("Chapter list", [
        ("Show or hide", ("win.sidebar",)),
        ("Move the chapter up / down", ("<Alt>Up", "<Alt>Down")),
        ("Move the chapter to Trash", ("Delete",)),
        ("All chapter actions", ("Menu",)),
    ]),
    ("Help", [
        ("Search commands (find any command and its key)", ("win.commands",)),
        ("Getting Started (a practice chapter)", ("win.guide",)),
        ("Keyboard shortcuts", ("win.shortcuts",)),
    ]),
)


def shortcut_keys(keys):
    """A SHORTCUTS item's keys as accelerators: an action ("win.find", or "ed.add:next"
    with a target) stands for its key in COMMANDS."""
    out = []
    for k in keys:
        if "." in k and not k.startswith("<"):
            action, _, target = k.partition(":")
            out.append(command(action, target or None).key)
        else:
            out.append(k)
    return out


# -- keys as people read them ---------------------------------------------------------------------

_MODS = (("<Ctrl>", "Ctrl"), ("<Control>", "Ctrl"), ("<Alt>", "Alt"), ("<Shift>", "Shift"))
_NAMES = {"Return": "Enter", "Up": "↑", "Down": "↓", "Page_Up": "PgUp", "Page_Down": "PgDn",
          "Escape": "Esc", "BackSpace": "Backspace", "space": "Space", "question": "?",
          "equal": "=", "minus": "-", "plus": "+"}


def key_label(accel):
    """A GTK accelerator as README.md and the guide write it: "<Ctrl><Shift>p" is
    "Ctrl+Shift+P", "<Alt>Up" is "Alt+↑", "<Ctrl>Page_Up" is "Ctrl+PgUp"."""
    mods, name = [], accel
    while name.startswith("<"):
        tag, name = name[:name.index(">") + 1], name[name.index(">") + 1:]
        mods.append(dict(_MODS).get(tag, tag.strip("<>")))
    order = {"Ctrl": 0, "Alt": 1, "Shift": 2}
    mods.sort(key=lambda m: order.get(m, 3))
    name = _NAMES.get(name, name.upper() if len(name) == 1 else name)
    return "+".join(mods + [name])
