# R34 — Section links

Requirements, written 2026-11-24. Status: **draft, to be agreed** (see
[Open questions](#open-questions)). Roadmap entry: [ROADMAP.md → R34](../../ROADMAP.md#richer-notes--not-started).

## Summary

When the text of any item names a section of the chapter (a numbered item, by its
title or by its label), that name becomes a link to the section. Ctrl+click or a key
on the link moves the cursor to the section; Alt+← goes back.

Example, in a chapter that has `Ⅱ.3) Garbage collection`:

```
Ⅳ) Performance
├ Ⅳ.1) Allocation
│   • Short-lived objects are cheap, see Garbage collection.
│   • The pauses are covered in Ⅱ.3.
```

Both `Garbage collection` and `Ⅱ.3` are links to `Ⅱ.3)`.

## Why

- Chapters run to ~200 items; notes refer back to earlier sections by name, and
  getting there today means scrolling or Ctrl+F.
- The references are already in the text. Making them live costs the user no extra
  typing and no markup.

## Terms

- **Section**: a numbered item (`heading` node), with its sub-items.
- **Title**: a section's text, normalised (see L3).
- **Label**: a section's number as the layout prints it, without the closing
  bracket: `Ⅱ`, `Ⅱ.3`, `Ⅱ.3.a`.
- **Mention**: a stretch of an item's text that matches a title or a label.
- **Link**: a mention the editor shows and lets the user follow.

## Decisions taken in this draft

Each can be overturned; the reasons are given so the trade-off is visible.

| # | Decision | Why |
|---|---|---|
| D1 | Links are **detected, not stored**. Nothing is added to the `.notz` file; mentions are found from the current text every time. | No file-format change, so 1.7 and older keep reading and writing new chapters losslessly (`Run.from_json` would drop an unknown run field). Renaming or deleting a section can never leave a dangling link. |
| D2 | Targets are **numbered items only**. Bullets are never targets. | Bullets are sentences, not names; matching them would link noise. "Point" in the feature name is read as a numbered sub-item (`Ⅱ.3.a`). |
| D3 | **Same chapter only** in this version. Other chapters of the book: [R34b](#later-r34b-r34d). | Keeps detection in memory and cheap; cross-chapter needs a book index (shared with R9, Search the book). |
| D4 | **Copy for TopCoding is unchanged**: links export as their plain text. | TopCoding's editor is one `<p>` with `<br>` per line in our export and has no anchor targets inside a note; whether it keeps `<a href>` at all is unchecked. See [R34c](#later-r34b-r34d). |
| D5 | Plain click keeps placing the cursor. **Ctrl+click** follows. | It is an editor first; this matches JetBrains and GNOME Builder. |

## Requirements

### Detection

- **L1** Every text in the chapter is searched for mentions: headings, bullets and
  table cells. Drawings and blocks from a newer version are not.
- **L2 Title mentions.** A mention matches a section's whole title, case-insensitively,
  on word boundaries (Unicode `\w`, as `find.pattern(whole=True)` does, so Cyrillic
  works).
- **L3 Title normalisation**, applied to the title and to the text it is matched
  against:
  - leading and trailing whitespace dropped, inner runs of whitespace treated as one
    space;
  - trailing `: . ; , – —` dropped from the title (`Garbage collection:` matches
    `garbage collection`);
  - bold and italic ignored; a mention may cross a formatting boundary.
- **L4 Minimum title.** A title is a target only if, after L3, it has at least
  **2 words or 6 letters**. `Ⅰ) Intro` is not a target; `Ⅱ.3) Garbage collection` is.
  Stops one common word from linking all over the chapter. The threshold is a rule in
  `rules.toml` (`links.min_title_letters`, `links.min_title_words`).
- **L5 Label mentions.** A mention matches a section's label when it:
  - uses Unicode or Latin Roman numerals for the parts the rules number that way, so
    `Ⅱ.3`, `II.3` and `ii.3` all match `Ⅱ.3)`, and Arabic or letter parts as the rules
    number them (reuse `importer.LABEL_RE`'s part grammar);
  - has **at least two parts**, or is one part followed by `)`. A bare `Ⅱ` or `2` in
    prose is not a link; `Ⅱ)` and `Ⅱ.3` are.
  - is not the item's own prefix (the prefix is layout, not text, so this holds
    already; tests must cover it).
  - is followed by an optional `)`, which is part of the link.
- **L6 Not a link:**
  - a mention inside the section it names, including the section's own title (a
    section doesn't link to itself or to its ancestors);
  - a mention inside a word (`Interrupts` in `Interruptstorm`);
  - in the Getting Started chapter, nothing is excluded: it should demonstrate the
    feature.
- **L7 Overlaps.** At one position, the longest mention wins (`Garbage collection
  roots` over `Garbage collection`). Mentions don't overlap; scanning resumes after the
  chosen one.
- **L8 Duplicate titles.** When two or more sections share a title, the mention links
  to all of them: following it opens a menu of the candidates (label + title + parent
  label), nearest one after the mention first. Label mentions are unique by
  construction.

### Appearance

- **L9** A link is drawn in the theme's accent colour with a dotted underline, over
  whatever bold or italic it has. It must stay readable in light and dark themes and
  with the find bar's highlights on top (find highlights take precedence).
- **L10** Holding Ctrl while hovering a link gives a solid underline and the pointer
  cursor. Without Ctrl, the cursor stays the text cursor.
- **L11** Hovering a link for the usual tooltip delay shows `Ⅱ.3) Garbage collection
  — Ctrl+click to go`; for duplicates, `2 sections — Ctrl+click to choose`.
- **L12** Spelling underlines still show inside links.
- **L13** A rule turns links off (`links.enabled = false`); then nothing is detected,
  drawn or followed.

### Following a link

- **L14 Ctrl+click** on a link, or **F12** with the cursor in or right after one, goes
  to the target. With an item selection or multiple cursors active, F12 does nothing.
- **L15 Going there** means:
  - the cursor goes to the start of the target's text, and the editor has focus;
  - the target row is scrolled into view with ~⅓ of the view above it (not pinned to
    the top edge), unless it is already fully visible;
  - the target row flashes its background once (~600 ms, eased), so the eye finds it.
    Respects GNOME's "reduce animation" setting (no flash, cursor only).
- **L16 Back and forward.** Each followed link pushes the cursor's position (item id
  and offset) on a back stack. **Alt+←** returns there, **Alt+→** goes forward again;
  following a new link clears the forward stack. The stacks are per chapter, kept
  in memory only, capped at 50, and cleared when another chapter opens. A position
  whose item was deleted falls back to the nearest surviving item in display order.
- **L17** Following a link is navigation, not an edit: it adds no undo step and does
  not mark the chapter as changed.
- **L18** If the target is inside a collapsed part of the outline (after R8, folding),
  its ancestors are unfolded first.

### Editing around links

- **L19** Links never change the text. Typing, Backspace, selection, copy and paste
  behave exactly as without them. Copying a link copies its text.
- **L20** After any edit, links reflect the new text within **200 ms** (the find bar's
  refind delay). Renaming a section re-links every mention of the new title and
  un-links the old one; renumbering (move, indent, delete) re-targets label mentions
  immediately.
- **L21** Label mentions follow the label, not the section: after `Ⅱ.3` moves to
  `Ⅱ.4`, the text `Ⅱ.3` links to whatever is `Ⅱ.3` now. This is the price of D1. A
  later version may rewrite label mentions when sections move ([R34d](#later-r34b-r34d)).

### Discoverability

- **L22** Ctrl+Space completes section titles: titles of targets in the chapter rank
  first among completions once at least two letters match, and picking one inserts
  the title as written in the heading. Its row in the popup shows the label
  (`Ⅱ.3`) at the right, in the same place a spelling fix shows its kind.
- **L23** Search Commands lists **Go to Section** (F12), **Back** (Alt+←) and
  **Forward** (Alt+→).
- **L24** Per the project rule for new controls: `commands.COMMANDS`, the shortcuts
  dialog, README.md, FEATURES.md and the Getting Started chapter (a short section with
  a link to follow and an exercise to rename a section and watch its mentions update).

## Non-functional

- **N1 Code layout.** Detection lives in a new GTK-free module `notterizmus/links.py`
  (pure functions: titles and labels in, `[(start, end, [target ids])]` out per text),
  unit-tested without a display. Drawing, hover and Ctrl+click go in the text views
  (`RichText`), following and back/forward in a new mixin `ui/outline_links.py`.
- **N2 Performance**, measured with `tests/ui/measure_drawings.py`'s 500-item chapter
  and the largest real chapter, on the UI tests' display:
  - a keystroke that doesn't change a title re-scans only its own text: ≤ 1 ms added
    per keystroke;
  - a title or structure change re-scans the chapter in one go, one compiled pattern
    for all titles and labels: ≤ 30 ms for 500 items, off the keystroke (debounced
    with L20's 200 ms);
  - opening a chapter: ≤ 20 ms added.
- **N3 Memory.** Link state is tags on each text buffer plus one pattern per chapter;
  no handler may hold a row or view (see R29c's rule in PROJECT_CONTEXT.md).
  `tests/ui/test_freeing.py` still passes.
- **N4 Accessibility.** Links are reachable without a mouse (F12, Alt+←/→); the
  tooltip text is exposed to screen readers as the link's description.
- **N5 Locale.** Matching is case-insensitive with Unicode casefolding, so Bulgarian
  titles work the same as English ones.

## Tests

- Unit (`tests/test_links.py`): title and label matching; normalisation (L3); the
  minimum (L4); Latin and Unicode Roman labels and the two-part rule (L5); self and
  ancestor exclusion (L6); longest match (L7); duplicates (L8); Cyrillic word
  boundaries; a title that is a substring of another word; titles with regex
  characters (`C++ (part 1)`); an empty chapter; a chapter with a newer-version block.
- UI (`tests/ui/test_links.py`): Ctrl+click goes to the target and flashes it; plain
  click places the cursor; F12; Alt+← / Alt+→ including after the source item was
  deleted; renaming a section updates links within 200 ms; moving a section re-targets
  a label mention; no undo step and no save after following; links in table cells.
- Export: Copy for TopCoding output is byte-for-byte the same with and without links
  (L19, D4).

## Out of scope

- Links to other chapters or books (R34b).
- Links to bullets, tables or drawings.
- Links to web pages (URLs).
- Any change to the `.notz` format or the clipboard formats.
- Clickable links in TopCoding (R34c).

## Later (R34b–R34d)

| ID | Item | Size |
|---|---|---|
| R34b | **Book-wide links**: titles of sections in the book's other chapters link too; following one opens that chapter at the section (back returns across chapters). Needs a cached index of titles per chapter, keyed by file mtime as `completion.BookWords` does; share it with R9. | M |
| R34c | **Links in TopCoding**. Spike: does TopCoding's Lexical editor keep `<a href>` from pasted HTML, and does it have any anchor a note can point to? If neither, keep D4. A possible middle way is a rule that appends the label in export: `Garbage collection (Ⅱ.3)`. | S spike |
| R34d | **Stable label references**: when a section moves, rewrite its label mentions in the chapter in the same undo step (`Ⅱ.3` → `Ⅱ.4`). Detection has to remember which section a label meant before the move. | M |

## Open questions

1. **Is the reading of "name" right?** This draft links both a section's **title**
   (`Garbage collection`) and its **label** (`Ⅱ.3`). Title only is simpler and never
   goes stale; label only is what hand-written notes often use. Recommendation: both.
2. **Bulgarian word forms.** Exact matching misses inflected mentions: the title
   `Модел на паметта` won't match `модела на паметта`. Options: (a) accept it; (b) let
   the last word of a mention take a definite-article ending (`-а -ът -та -то -те`);
   (c) stemming via Hunspell. Recommendation: (b), small and predictable.
3. **Duplicate titles** (L8): a chooser, or simply the nearest section after the
   mention?
4. **Keys.** F12 and Alt+←/→ aren't used anywhere in the app's code (to confirm
   GtkTextView binds neither). Acceptable, or prefer Ctrl+Alt+←/→ as in JetBrains?
5. **R34b now?** If most references are to other chapters, book-wide links should be
   part of the first version, not a follow-up.
