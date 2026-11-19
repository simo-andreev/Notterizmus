# Code review and fix plan

Reviewed 2026-11-18 at `fd5baf4`, together with the uncommitted R29g work
(`drawing_web._EvenSize`, `EvenSizeTest`). The review covers every Python module, the
drawing page's source (`web/drawing`), the scripts, the Debian and snap packaging and both
test suites. It doesn't cover the generated bundle in `notterizmus/drawing_web/`, and only
skims the internals of `tests/ui/broadway_input.py` and `tests/ui/measure_drawings.py`.

Issues have IDs **CR1–CR52** (code review), so commit messages can name them beside
ROADMAP's R-numbers, e.g. "Save the open chapter before switching (CR4)".

## How to read this

- **Severity.** High: can block a release or lose data in normal use. Medium: wrong
  behaviour, or data at risk, in a plausible situation. Low: edge cases and hygiene.
- **Fix.** Easy: under an hour. Moderate: a few hours. Hard: a redesign, a day or more.
- **✔** The issue was confirmed by running the code during the review: throwaway probes
  against the real modules in temporary folders, and UI probes on the UI tests' private
  Broadway display. Unmarked issues come from reading the code.
- **Phase.** Where the issue is fixed in the [roadmap](#roadmap).

## Summary

- 52 issues: 1 High, 9 Medium, 42 Low. 21 were confirmed by running the code.
- By category: 21 probable bugs, 6 performance, 6 code smells, 5 code debt,
  4 partial implementations (3 of them are already in ROADMAP.md as R32, R16 and R30),
  4 test problems, 2 security, 2 leftover stubs, 2 verbose or unreadable code.
- The biggest risks:
  - The package build runs tests that need GTK, which the build doesn't install (CR1).
    It has already failed on Launchpad for 1.4.2 and 1.5.0, so the PPA still serves 1.4.0.
  - Four ways to lose, duplicate or hide notes (CR3–CR6).
  - A common Shift+click that raises an exception (CR2).
- Baseline: the unit suite passes (367 tests, 31 skipped). The full UI suite wasn't run
  during the review; in phase 0 it passed (248 tests in 194 s), with and without the real
  Excalidraw.
- No exploitable security issue was found. The drawing page is well contained: its own URI
  scheme, a file server that checks paths, an ephemeral session, a CSP that blocks the
  network, and navigation blocked.

## Issues

| ID | Category | Description | Location | Severity | Fix | Phase |
|---|---|---|---|---|---|---|
| CR1 | Flawed or partial tests | ✔ The package build (`override_dh_auto_test`) runs `unittest discover -s tests`, which also imports `tests/ui`. `test_selection.py` imports `gi.repository.Gdk` at module level, and `PreferGpuTest` (a plain `TestCase`, new since 1.5.0) imports `ui/drawing_web.py`, which loads GTK and libadwaita. Neither PyGObject nor those typelibs are Build-Depends. With PyGObject hidden, the unit run ends with 5 errors. Launchpad's builders don't have PyGObject (found in phase 0): 1.4.2 and 1.5.0 failed to build on `test_selection`'s import, so the PPA still serves 1.4.0. It also contradicts PROJECT_CONTEXT ("the UI suites skip themselves"). | [rules:10](debian/rules#L10), [control:4](debian/control#L4), [test_selection.py:2](tests/ui/test_selection.py#L2), [test_drawings.py:479](tests/ui/test_drawings.py#L479) | High | Easy | 1 |
| CR2 | Probable bug | ✔ Shift+click on another item raises `ValueError` when items are selected without an anchor. Ctrl+W up to item level, and a click on a drawing, set `sel` but not `sel_anchor` (left None, or pointing at a deleted node), and `on_click` calls `order.index(self.sel_anchor)`. The click does nothing. | [outline_menus.py:252](notterizmus/ui/outline_menus.py#L252), [outline_selection.py:249](notterizmus/ui/outline_selection.py#L249), [rows.py:423](notterizmus/ui/rows.py#L423) | Medium | Easy | 3 |
| CR3 | Probable bug | ✔ The paste toasts' buttons (Paste as Plain Text, One Item per Paragraph) call `undo()` without checking that the paste is still the last step. After a word was typed within the toast's 6 seconds, the button undid the word, kept the pasted items and added the same text again as plain text. | [outline_clipboard.py:223](notterizmus/ui/outline_clipboard.py#L223), [:246](notterizmus/ui/outline_clipboard.py#L246) | Medium | Moderate | 2 |
| CR4 | Probable bug | ✔ `set_doc` doesn't save the open chapter first, and its pending 800 ms autosave then saves the newly opened chapter instead. `App.do_open` (a file opened from Files) and the Trash toast's Undo open a chapter without saving, so the previous chapter's last edits are lost. The trigger is narrow, but the loss is silent. | [window.py:327](notterizmus/ui/window.py#L327), [app.py:75](notterizmus/ui/app.py#L75), [window.py:609](notterizmus/ui/window.py#L609) | Medium | Easy | 2 |
| CR5 | Probable bug | ✔ When chapters whose file names differ only in the number swap places (untitled chapters, or chapters with the same title), `backups.move` moves their copy folders one at a time, and the first move merges into the other chapter's folder. After `01.notz` and `02.notz` swapped, chapter 01 listed both chapters' copies and 02 listed none, so Restore can bring another chapter's text into this one. | [backups.py:103](notterizmus/backups.py#L103), [window.py:391](notterizmus/ui/window.py#L391) | Medium | Moderate | 2 |
| CR6 | Probable bug | ✔ `renumber` (reorder, Alt+↑/↓, number swaps) rolls back only for `FileExistsError`. When the second chapter's write failed (a full disk, simulated), `01 One` stayed behind as a hidden `.moving-….notz` file and vanished from the chapter list. `set_chapter` can also raise after `renumber` has already moved files (two chapters with the same number in one book), and the open chapter is then not re-pointed. | [library.py:181](notterizmus/library.py#L181), [:155](notterizmus/library.py#L155) | Medium | Moderate | 2 |
| CR7 | Probable bug | ✔ `safe_name` turns a book name into a folder name but keeps a leading dot, and keeps "." and "..". ".NET in Action" becomes a hidden folder that `scan()` skips, so the book never shows in the list and Ctrl+PgUp/PgDn say the chapter isn't in the notes folder. Book "." puts the chapter file loose in the notes folder, and book ".." puts it in Documents itself. | [library.py:46](notterizmus/library.py#L46), [:95](notterizmus/library.py#L95), [window.py:765](notterizmus/ui/window.py#L765), [:530](notterizmus/ui/window.py#L530) | Medium | Easy | 3 |
| CR8 | Probable bug | ✔ `Adw.Toast` treats its title as Pango markup (`use-markup` is on by default in libadwaita 1.9), but toasts include chapter and book titles, file names and system error text. A chapter titled "Q&A" gives a "moved to Trash" toast with no text (its Undo button is still there) and a GTK warning. | [window.py:261](notterizmus/ui/window.py#L261) (callers :370, :463, :512, :594, :599, :603, :694, :994) | Medium | Easy | 3 |
| CR9 | Partial implementation | Known as R32: Ctrl+B or Ctrl+I with nothing selected should format the next typed text. ✔ On the Broadway test display with real keys it works ("xyz" came out italic), so the editor's logic is right there. On the desktop, something, most likely the input method, sets the cursor mark between the toggle and the typing, and `_on_mark_set` then drops `_pending`. | [richtext.py:207](notterizmus/ui/richtext.py#L207), [:245](notterizmus/ui/richtext.py#L245) | Medium | Moderate | 3 |
| CR10 | Partial implementation | Known as R16: autosave overwrites a chapter that another program changed on disk (a sync tool, a second machine). Nothing is checked before saving. | [window.py:709](notterizmus/ui/window.py#L709) | Medium | Moderate | 2 |
| CR11 | Probable bug | ✔ "Top-level items are always numbered" (README, PROJECT_CONTEXT, `test_guide`) is enforced only by `outdent` and `remove_promote`. `set_kind` accepts a top-level bullet, so typing "* " at the start of a top-level item makes one, as do Ctrl+Shift+Space and the item-type menu; a paste into an empty first item can too. Copy for TopCoding then starts with an unnumbered "• …". | [model.py:323](notterizmus/model.py#L323), [outline.py:357](notterizmus/ui/outline.py#L357), [outline_items.py:28](notterizmus/ui/outline_items.py#L28), [outline_clipboard.py:274](notterizmus/ui/outline_clipboard.py#L274) | Low | Easy | 3 |
| CR12 | Probable bug | ✔ `display_order()` includes the sub-items of blocks from a newer version, and those sub-items have no rows. Backspace at the start of the item after such a block joined its text into the block's hidden sub-item (saved to the file), then raised `KeyError`. The app changed data it promises to keep unchanged. Latent until a newer version writes such blocks. | [outline_keys.py:213](notterizmus/ui/outline_keys.py#L213), [model.py:215](notterizmus/model.py#L215) | Low | Easy | 2 |
| CR13 | Probable bug | ✔ The item menu's Delete Block, on a block from a newer version, uses `delete_node`, which calls `remove_promote` and so moved the block's sub-items up into the chapter. The block's trash button (`delete_items`) removes it whole. | [outline_menus.py:233](notterizmus/ui/outline_menus.py#L233), [outline_items.py:147](notterizmus/ui/outline_items.py#L147) | Low | Easy | 3 |
| CR14 | Security | ✔ Clipboard data from any app is read with too few exception handlers. A `TypeError` (a table cell whose `children` is a number) and a `RecursionError` (deep nesting) escape `lexical.pasted_items`, so Ctrl+V does nothing instead of falling back to the HTML. The app's own `…nodes+json` and `…runs+json` types are parsed with no guard at all. The worst outcome is a failed paste. | [lexical.py:270](notterizmus/lexical.py#L270), [:306](notterizmus/lexical.py#L306), [outline_clipboard.py:174](notterizmus/ui/outline_clipboard.py#L174) | Low | Easy | 3 |
| CR15 | Probable bug | ✔ New Chapter calls `doc.save()` without handling errors. A title of more than about 127 Cyrillic characters exceeds the 255-byte file-name limit (`ENAMETOOLONG`), and so can a long book name; so does an unwritable folder. The dialog closes and nothing happens, with a traceback only on stderr. | [window.py:772](notterizmus/ui/window.py#L772), [model.py:462](notterizmus/model.py#L462), [library.py:95](notterizmus/library.py#L95) | Low | Easy | 3 |
| CR16 | Probable bug | ✔ New Chapter's "already exists" check is the glob `f"{n:02d}*.notz"`, so creating chapter 10 opens chapter 100 ("That chapter already exists"). `library.chapter_numbered` does the check correctly. | [window.py:766](notterizmus/ui/window.py#L766) | Low | Easy | 3 |
| CR17 | Probable bug | The drawing window's `changed()` compares the sum of the versions of the elements that aren't deleted. Deleting an element takes its version out of the sum, so a few edits elsewhere (arrow-key nudges, say) can bring the sum back to its opening value, and Cancel then discards without asking. A change of the background alone is never noticed. | [main.jsx:116](web/drawing/main.jsx#L116) | Low | Easy | 3 |
| CR18 | Performance | ✔ Sidebar chapter rows are never freed: their drag-source handlers hold the row, the same cycle through GTK that R29c fixed for editor rows. Every rebuild of the list (a chapter switch, folding a book, a changed folder) leaks the chapter rows shown: 0 of 5 were freed, against 2 of 2 book rows. | [sidebar.py:126](notterizmus/ui/sidebar.py#L126) | Low | Easy | 5 |
| CR19 | Probable bug | If the chapter changes while the modal drawing window is open (possible only through `App.do_open`), `insert_drawing`'s callback falls back to `self.current` and puts the drawing in the other chapter, and `edit_drawing`'s callback drops the edit. | [outline_items.py:110](notterizmus/ui/outline_items.py#L110), [:132](notterizmus/ui/outline_items.py#L132) | Low | Easy | 3 |
| CR20 | Probable bug | A typed trigger that `set_kind` refuses ("# " under a bullet, "* " on an item with numbered sub-items) is deleted anyway, before the refusal message appears. | [outline.py:360](notterizmus/ui/outline.py#L360) | Low | Easy | 3 |
| CR21 | Probable bug | Opening Getting Started adds its words (Ctrl, TopCoding, compl, …) to Enchant's session list. The dictionaries are cached for the whole run, so those words stay unflagged in every chapter opened afterwards. | [window.py:333](notterizmus/ui/window.py#L333), [spell.py:164](notterizmus/spell.py#L164) | Low | Easy | 3 |
| CR22 | Probable bug | `state.json` is written non-atomically and read without type checks. A file that isn't a JSON object, or a value of the wrong type (`"zoom": "big"`, `"last_file": 5`), raises in `Window.__init__`, and the app doesn't start. rules.toml has this protection; state.json doesn't. | [window.py:35](notterizmus/ui/window.py#L35), [:196](notterizmus/ui/window.py#L196), [:250](notterizmus/ui/window.py#L250), [:255](notterizmus/ui/window.py#L255) | Low | Easy | 4 |
| CR23 | Probable bug | ✔ The rules check misses three cases. A user marker with trigger "#" silently takes over numbered items. Two markers with one trigger shadow each other. Unknown `numbering.levels` names silently become Arabic numbers. | [rules.py:122](notterizmus/rules.py#L122), [:187](notterizmus/rules.py#L187) | Low | Easy | 4 |
| CR24 | Probable bug | ✔ Paste treats any 1–4 Latin letters before ")" as a label, so "Yes) that is right" and "Also) …" became numbered items. Cyrillic labels ("а)", "б)"), usual in Bulgarian notes, aren't recognised. | [importer.py:17](notterizmus/importer.py#L17) | Low | Moderate | 4 |
| CR25 | Probable bug | ✔ Saves replace the file atomically, but never fsync the file or its folder, and the new file keeps `mkstemp`'s 0600 mode. Every save changes a chapter's permissions (0644 became 0600), which sync tools and shared folders notice. `drawing.store_preview` does the same. | [model.py:437](notterizmus/model.py#L437), [drawing.py:103](notterizmus/drawing.py#L103) | Low | Easy | 2 |
| CR26 | Probable bug | Earlier Versions copies are named by naive local time. In the hour that repeats when daylight saving ends, names collide (the copy is skipped) or sort in the wrong order, so the "newest" copy and the 10-minute check can be wrong. | [backups.py:27](notterizmus/backups.py#L27), [:67](notterizmus/backups.py#L67) | Low | Easy | 2 |
| CR27 | Code debt | Error paths that raise into GTK callbacks instead of telling the user: `App.do_open` with a non-local file (`get_path()` is None), Edit Formatting Rules' template write, Trash Undo's write-back, `_after_move`'s reload, a malformed metainfo file (About), and `dictionary_words` on an `.aff` file with a bare `SET` or an encoding Python doesn't know. | [app.py:75](notterizmus/ui/app.py#L75), [window.py:987](notterizmus/ui/window.py#L987), [:607](notterizmus/ui/window.py#L607), [:397](notterizmus/ui/window.py#L397), [paths.py:78](notterizmus/paths.py#L78), [completion.py:96](notterizmus/completion.py#L96) | Low | Easy | 4 |
| CR28 | Partial implementation | Known as R30: drawings through TopCoding's clipboard JSON are built from synthetic pastes only, in both directions. Header cells are written with `headerState` 1 everywhere, where TopCoding uses 3 in the first column. | [lexical.py:33](notterizmus/lexical.py#L33), [:72](notterizmus/lexical.py#L72) | Low | Moderate | With you |
| CR29 | Leftover stub | Mermaid is replaced by a stub that throws, and Excalidraw's own Mermaid (text-to-diagram) entry probably still shows and fails; this wasn't checked in a running page. The shape library is hidden only by CSS on an internal class name (`.default-sidebar-trigger`), which may stop working after an Excalidraw upgrade. | [mermaid-stub.js:1](web/drawing/mermaid-stub.js#L1), [index.html:14](web/drawing/index.html#L14) | Low | Easy | 4 |
| CR30 | Partial implementation | The snap manifest (R17) has never been built or run. The Debian package recommends only English dictionaries, although Bulgarian is one of the app's two languages (`hunspell-bg`). | [snapcraft.yaml](snap/snapcraft.yaml), [control:18](debian/control#L18) | Low | Easy | 4 |
| CR31 | Security | Hardening gaps in the otherwise well-contained drawing page: the CSP's `default-src 'self' data: blob:` also allows data: and blob: frames and connections; the page may read the clipboard without a user gesture; download responses aren't refused in `decide-policy`. No exploit was found. | [index.html:6](notterizmus/drawing_web/index.html#L6), [drawing_web.py:114](notterizmus/ui/drawing_web.py#L114), [:128](notterizmus/ui/drawing_web.py#L128) | Low | Easy | 4 |
| CR32 | Performance | ✔ Earlier Versions loads, parses and byte-compares every kept copy on the main thread before the dialog appears: 0.66 s for a 4 MB chapter with 54 copies (files in the cache), more from a cold disk. | [window.py:897](notterizmus/ui/window.py#L897) | Low | Moderate | 5 |
| CR33 | Performance | Every `refresh()` (Enter, Tab, Alt+↑/↓, undo, paste) schedules a 20 ms timeout that re-measures every text view of the chapter. The timeouts aren't merged, so key repeat queues many. The cost grows with chapter size; R15 never measured it. | [outline.py:239](notterizmus/ui/outline.py#L239), [:245](notterizmus/ui/outline.py#L245) | Low | Moderate | 5 |
| CR34 | Performance | While the Ctrl+Space popup is open, each keystroke recounts every word of the chapter and re-reads the word counts of every chapter of the book (a stat and a resolve per file). | [outline_assist.py:68](notterizmus/ui/outline_assist.py#L68), [completion.py:53](notterizmus/completion.py#L53) | Low | Easy | 5 |
| CR35 | Performance | `DrawingRow.reload` hashes the whole scene twice: JSON and SHA-1 in `preview_key`, then again through `preview_path`. That is several MB per call for a drawing with pasted pictures. | [rows.py:426](notterizmus/ui/rows.py#L426), [:439](notterizmus/ui/rows.py#L439), [drawing.py:84](notterizmus/drawing.py#L84) | Low | Easy | 5 |
| CR36 | Performance | Quadratic helpers, from slices or joins inside loops: `layout.children`, `copy_items` (per spacer line), `count_words` (per word), `join_lines` (re-joins all earlier text per line) and `FindBar._show_current` (clears the whole buffer once per match). | [layout.py:93](notterizmus/layout.py#L93), [outline_clipboard.py:67](notterizmus/ui/outline_clipboard.py#L67), [completion.py:40](notterizmus/completion.py#L40), [importer.py:60](notterizmus/importer.py#L60), [findbar.py:204](notterizmus/ui/findbar.py#L204) | Low | Easy | 5 |
| CR37 | Code debt | Shortcuts and commands are listed in five places: the app's accelerators, the Shortcuts dialog, Search Commands, the guide, and README with FEATURES. Only the guide and README are checked against each other. | [app.py:47](notterizmus/ui/app.py#L47), [window.py:1015](notterizmus/ui/window.py#L1015), [command_search.py:64](notterizmus/ui/command_search.py#L64) | Low | Moderate | 7 |
| CR38 | Code debt | `window.py` is one 1,124-line class: the header, menus, about 40 actions, five dialogs, file operations, zoom, sidebar sizing and spelling, with a ~200-line `__init__`. R14 split the editor but not the window. | [window.py:48](notterizmus/ui/window.py#L48) | Low | Hard | 7 |
| CR39 | Code debt | The editor mixins share undeclared state and call each other's private helpers (`_prev_text_node`, `_insert_leaf`, rows' internals). Kind changes and table row and column edits change the document outside `_op()` and rely on a later commit, against the project's own rule. | [outline_items.py:19](notterizmus/ui/outline_items.py#L19), [rows.py:309](notterizmus/ui/rows.py#L309) | Low | Moderate | 7 |
| CR40 | Code debt | XDG folders are looked up in three places with different fallbacks (`rules.config_dir` uses `expanduser`, `paths.data_dir` and `drawing.cache_dir` use `$HOME`), plus `completion._dic_dirs`. | [rules.py:93](notterizmus/rules.py#L93), [paths.py:41](notterizmus/paths.py#L41), [drawing.py:93](notterizmus/drawing.py#L93), [completion.py:75](notterizmus/completion.py#L75) | Low | Easy | 7 |
| CR41 | Code smell | Module-level state: `richtext.SPELL` (spelling for every view), `_ZOOM_PROVIDER`, `drawing_web._renderer` and `_context`, `completion._DICT_CACHE`. `drawing_web` changes `os.environ` when it is imported, which switches the whole app to GL on NVIDIA's driver. | [richtext.py:12](notterizmus/ui/richtext.py#L12), [window.py:1076](notterizmus/ui/window.py#L1076), [drawing_web.py:29](notterizmus/ui/drawing_web.py#L29), [:79](notterizmus/ui/drawing_web.py#L79), [:252](notterizmus/ui/drawing_web.py#L252) | Low | Moderate | 7 |
| CR42 | Code smell | ✔ UI modules import `gi.repository` without `gi.require_version` and depend on `app.py` being imported first. Imported alone, they warn: the unit run prints two PyGIWarnings. | [drawing_web.py:18](notterizmus/ui/drawing_web.py#L18), [rows.py:6](notterizmus/ui/rows.py#L6), [test_selection.py:2](tests/ui/test_selection.py#L2) | Low | Easy | 1 |
| CR43 | Code smell | Python attributes stuck on GTK widgets as data, some read from other modules: `row._path`, `_book` and `_folder` (read by window.py), `row._cb`, `_choice`, `_act` and `_target`, `row._backup`, `row._cmd`, `lbl._markup`, `view.ntz_loaded` and `ntz_waiting`. | [sidebar.py:110](notterizmus/ui/sidebar.py#L110), [window.py:429](notterizmus/ui/window.py#L429), [:911](notterizmus/ui/window.py#L911), [outline_menus.py:166](notterizmus/ui/outline_menus.py#L166), [drawing_web.py:120](notterizmus/ui/drawing_web.py#L120) | Low | Moderate | 7 |
| CR44 | Code smell | Test hooks in production code: `Window._command_search` and `Window._versions_preview` keep the last dialog alive only for the tests; `ChapterSidebar.chapter_rows()` is "used by the tests"; `drawing_web.shutdown()` is called only by tests. | [window.py:872](notterizmus/ui/window.py#L872), [:927](notterizmus/ui/window.py#L927), [sidebar.py:257](notterizmus/ui/sidebar.py#L257), [drawing_web.py:412](notterizmus/ui/drawing_web.py#L412) | Low | Easy | 7 |
| CR45 | Leftover stub | Dead or redundant code: the unused `_owned` parameter of `_Layout.leaf`; `enchant_broker_free_dict` declared, but the broker and dictionaries are never freed; the public alias `runs_html = _runs_html`; `KeyError` caught around `Document.load`, which never raises it; function-local imports with no import cycle to avoid. | [layout.py:104](notterizmus/layout.py#L104), [spell.py:70](notterizmus/spell.py#L70), [export.py:112](notterizmus/export.py#L112), [window.py:369](notterizmus/ui/window.py#L369), [library.py:102](notterizmus/library.py#L102) | Low | Easy | 7 |
| CR46 | Code smell | `RichText` coordinates edits through three re-entrancy flags (`_loading`, `_inserting`, `_raw`) and a pending format that any move of the insert mark clears. This is fragile, and the likely seat of R32 (CR9). | [richtext.py:46](notterizmus/ui/richtext.py#L46), [:217](notterizmus/ui/richtext.py#L217) | Low | Moderate | 7 |
| CR47 | Code smell | `TableRow.rows` writes to the node when read (`setdefault`). A table with ragged rows (from a hand-edited or newer file) makes `del_col` raise `IndexError` and Tab skip cells. | [rows.py:202](notterizmus/ui/rows.py#L202), [:263](notterizmus/ui/rows.py#L263), [:335](notterizmus/ui/rows.py#L335) | Low | Easy | 4 |
| CR48 | Verbose or unreadable code | Tuple-index lambdas used as statements (`lambda: (x.grab_focus(), False)[1]`, 12 places) and conditional method calls (`(w.add_css_class if c else w.remove_css_class)(…)`). | [window.py:253](notterizmus/ui/window.py#L253), [outline.py:198](notterizmus/ui/outline.py#L198), [outline_assist.py:150](notterizmus/ui/outline_assist.py#L150), [outline_selection.py:60](notterizmus/ui/outline_selection.py#L60) | Low | Easy | 7 |
| CR49 | Verbose or unreadable code | Long functions full of nested closures: `_popup` (~110 lines, four closures), `show_assist` (~110 lines, six) and `on_versions` (~80 lines mixing UI and logic). | [outline_menus.py:101](notterizmus/ui/outline_menus.py#L101), [outline_assist.py:92](notterizmus/ui/outline_assist.py#L92), [window.py:876](notterizmus/ui/window.py#L876) | Low | Moderate | 7 |
| CR50 | Flawed or partial tests | 80 fixed-time `ui.pump(0.1–0.3)` waits across 15 UI test files, plus a `time.sleep(1.1)`, against PROJECT_CONTEXT's rule "wait for a condition, never for a time". Most are padding after synchronous actions (a slower suite); where the state is deferred, they make the test timing-dependent. | [test_sidebar.py](tests/ui/test_sidebar.py) (20), [test_real_keys.py](tests/ui/test_real_keys.py) (10), [test_chapters.py](tests/ui/test_chapters.py) (9), [test_backups.py:49](tests/ui/test_backups.py#L49) | Low | Moderate | 6 |
| CR51 | Flawed or partial tests | No test covers CR2–CR8, CR11–CR16 or CR18. `test_freeing.py` checks editor rows but not sidebar rows. `test_drawing.py` tries garbage clipboard bytes, but not well-formed JSON with the wrong types. | [test_freeing.py](tests/ui/test_freeing.py), [test_drawing.py:318](tests/test_drawing.py#L318) | Low | Moderate | 6 |
| CR52 | Flawed or partial tests | `assertEqual(len(…) >= 2, True)` can't say what went wrong. `test_release.py` checks four version sources but not README's title or FEATURES.md, and its rule that CHANGELOG's first heading is the current version leaves no place for finished but unreleased work (R29f, R29g and R33 are only in ROADMAP). | [test_chapters.py:188](tests/ui/test_chapters.py#L188), [test_release.py:22](tests/test_release.py#L22) | Low | Easy | 6 |

## Roadmap

The phases go in order of risk: first what can block a release, then what can lose data,
then what is visibly broken, then robustness, speed, the test suite and code health.
Sizes follow ROADMAP.md: **S** one focused change, **M** several changes across modules,
**L** large. Each item gives the fix and the test or check that proves it; the boxes track
progress.

| Phase | Theme | Issues | Size | Release |
|---|---|---|---|---|
| 0 | Baseline and checks of your notes | (none fixed) | S | |
| 1 | Unblock the package build | CR1, CR42 | S | |
| 2 | Data safety | CR3, CR4, CR5, CR6, CR10, CR12, CR25, CR26 | M | 1.6.0 waited for phase 4 |
| 3 | Broken or surprising behaviour | CR2, CR7, CR8, CR9, CR11, CR13, CR14, CR15, CR16, CR17, CR19, CR20, CR21 | M | |
| 4 | Robustness and configuration | CR22, CR23, CR24, CR27, CR29, CR30, CR31, CR47 | M | **Released as 1.6.0** on 2026-11-19, with phases 1–4, R29f, R29g and R33 |
| 5 | Performance and memory | CR18, CR32, CR33, CR34, CR35, CR36 | M | When convenient |
| 6 | Test suite | CR50, CR51, CR52 | S–M | When convenient |
| 7 | Code health, no change in behaviour | CR37, CR38, CR39, CR40, CR41, CR43, CR44, CR45, CR46, CR48, CR49 | L | When convenient |
| With you | Needs your input | CR28 (R30), and the decision CR11 depends on | S | |

Related issues to fix together: CR11 with CR20 (the same trigger code), CR9 with CR46,
CR1 with CR41 (both move `_prefer_gpu`), CR5 with CR6 (the same two-phase move), CR12
with CR13 (blocks from a newer version), CR22 with CR25 (one atomic-write helper).

### Rules for every fix

1. **Test first.** Write the regression test, run it on the unfixed code and see it fail
   for the reason described; then fix it and see it pass. PROJECT_CONTEXT: "Add a UI test
   for every UI bug fixed."
2. Logic without GTK gets a unit test in `tests/`. Anything that needs the editor gets a
   UI test in `tests/ui/` that waits for a condition (`ui.wait_for`), never for a time.
   Any exception the app raises in a callback fails the test by itself.
3. After each fix, both suites pass:
   `python3 -m unittest discover -s tests -t .` and `scripts/ui-tests.sh`, which also fails
   on any GTK or Python warning.
4. Fixes that touch timing in the UI also pass the load check (see
   [Commands](#commands)).
5. Fixes to the drawing page: rebuild it with `scripts/build-drawing-editor.sh`, commit
   `notterizmus/drawing_web/` and run `NOTTERIZMUS_UI_WEBKIT=1 scripts/ui-tests.sh`.
6. A control or shortcut that changes is updated in `guide.py`, README.md, FEATURES.md and
   the Shortcuts dialog (PROJECT_CONTEXT).
7. One commit per issue, or per group of related issues, with the ID in the message.

### Phase 0: Baseline and checks of your notes (S)

Know the starting point, and find out whether the bugs already touched your notes.

- [x] Record the baseline: the unit suite's result; the full `scripts/ui-tests.sh` result
  and how long it takes; the drawing measurements for phase 5
  (`NOTTERIZMUS_UI_WEBKIT=1 NOTTERIZMUS_UI_TEST_TIMEOUT=900 scripts/ui-tests.sh -p 'measure_*.py'`).
- [x] Read the 1.5.0 build log on Launchpad: did `dh_auto_test` import
  `tests.ui.test_selection` and run it? That shows whether the builders have PyGObject,
  and so how urgent CR1 is.
- [x] Check your notes with the read-only commands under
  [Checks of your notes](#checks-of-your-notes): chapters stranded by a failed reorder
  (CR6), hidden book folders and chapters saved in the wrong place (CR7), top-level bullets
  (CR11), and backup folders with copies of more than one chapter (CR5). Repair what they
  find before phase 2 changes the code around it.

#### Phase 0 results

Done 2026-11-19 at `23307f2`, on this machine (16 cores, NVIDIA's driver loaded).

**Baseline.**

| Run | Result | Time |
|---|---|---|
| Unit suite | 367 tests pass, 31 skipped; two PyGIWarnings (CR42) | 2.1 s |
| Unit suite with PyGObject hidden | 5 errors, as CR1 says: `test_selection`'s import and the four `PreferGpuTest` tests | 2.1 s |
| CR42's check command | Fails on the Gdk PyGIWarning, as CR42 says | |
| `scripts/ui-tests.sh` | 248 tests pass, 4 skipped (the real-Excalidraw tests); no warnings. A second run took the same time; no test takes more than 2.6 s | 194 s |
| `NOTTERIZMUS_UI_WEBKIT=1 scripts/ui-tests.sh` | 248 tests pass, none skipped | 199 s |
| The load check ([Commands](#commands)): the suite on one CPU beside two busy loops | 248 tests pass, 4 skipped; no test takes more than 4.4 s | 243 s |
| Drawing measurements | Ran twice; the runs agree within a few percent. The numbers below are the first run's | 74 s |

The drawing measurements, for phase 5 (medians, or median / max):

| What | Measured |
|---|---|
| Drawing window, until Excalidraw is ready | 1,262 ms the first time, then 868–974 ms |
| Inside Excalidraw, an input until it is drawn | 38–64 ms; moving all 440 elements with the arrow keys 80 / 112 ms, 23 ms of it in Excalidraw's handler |
| Done, until back in the chapter (110 elements / 440 / a 1 MB picture) | 136 / 180 / 157 ms, frozen at most 41 / 48 / 51 ms |
| Opening a chapter with 8 drawings, previews cached | Blocked 288 ms, all pictures shown at 407 ms, 31 MB of textures |
| The same with a new preview page | Blocked 234 ms, all pictures shown at 1,189 ms |
| Undo | 28–32 KB a step (14–16 MB for 500); a keystroke 0.4 ms; undo and redo about 2 ms |
| Autosave (text only / 8 drawings / 3 pictures / chapter 10) | 1.2 / 30 / 22 / 7.1 ms |
| Loading the same chapters | 0.4 / 7.9 / 15 / 1.8 ms |
| Earlier Versions, at most: making a copy / restoring one | 2.8 / 17 ms |

They match R29's numbers after its fixes, with one exception: R29 measured 12 ms for
Excalidraw to move all 440 elements, and both runs here 23 ms. These runs aren't quite
R29's, though. Since R29f, `_prefer_gpu` runs in the tests too, and on this machine it
gives WebKit `WEBKIT_FORCE_DMABUF_RENDERER=1` there (the runner names GTK's renderer, not
WebKit's). Phase 5 must measure with the same setting, and CR1 and CR41 move that call:
check that it still happens in the tests, or set the variable for the run. CR33, CR34 and
CR36 need their own measurements, taken before each fix.

**Launchpad.** The builders don't have PyGObject, and the last two uploads failed to
build. For 1.4.2 (2026-11-17) and 1.5.0 (2026-11-18), `dh_auto_test` couldn't import
`tests.ui.test_selection` (`ModuleNotFoundError: No module named 'gi'`; 1 error in 363
tests for 1.5.0). The import came in with 52dd9ad ("Make editor shortcuts work on
non-Latin keyboard layouts"), after 1.4.0, the last good build (343 tests, OK). So the PPA
publishes the 1.5.0 source, but anyone installing from it still gets 1.4.0; this machine
runs 1.5.0 from a local `.deb`. The next upload would also fail on the four
`PreferGpuTest` tests. CR1 is urgent.

**Your notes.** Read-only checks of the one book (7 chapters) and its 119 Earlier
Versions copies:

- CR6: no `.moving-*` files. CR7: no hidden book folders, and no chapters outside a book
  folder or loose in Documents. CR11: no top-level bullets; every top-level item is
  numbered. Each chapter's book, number and title match its file name.
- CR5: one folder is flagged, `09 Design a web cralwer`, with copies numbered 8 and 9.
  It's a renumber, not a merge: the chapter was number 8 until 2026-11-11 18:38 and 9 from
  20:08 that day, with the same title and text, growing steadily.
- `state.json` and `rules.toml` load cleanly and hit none of the cases in CR22 or CR23.
- All 7 chapter files are 0600, as CR25 predicts. CR25's fix keeps a file's mode, so they
  will stay that way unless you change them.

Nothing the bugs did needs repairing. One thing they didn't cause: chapter 10's oldest
copy (2026-11-17 16:50, untitled then) holds 33 items of general SDI notes ("Goal of the
SDI…", "4-step framework", steps 3 and 4, "Other notes") that are in no chapter and not in
the Trash. The next copy, at 17:28, is a single empty item, so the chapter was most likely
cleared on purpose before the notification-system notes began. Earlier Versions deletes
that copy with the first new copy of chapter 10 made after 2026-11-24 17:28. Restoring it
would replace chapter 10, so to keep those notes, copy them out before then (see
[With you](#with-you)).

### Phase 1: Unblock the package build (S)

- [x] **CR1. Unit tests that need no GTK.**
  - Fix: move `_prefer_gpu`, which is pure environment logic, out of
    `ui/drawing_web.py` into a module without GTK (e.g. `notterizmus/gpu.py`). Call it at
    the top of `ui/app.py`, before `from .window import Window`, so it still runs before
    GTK's first window and WebKit's first page; `scripts/measure-drawing-stroke.py`
    relies on today's import-time call and must call it too. Move `PreferGpuTest` to
    `tests/test_gpu.py`, and add the module to PROJECT_CONTEXT's list of modules kept free
    of GTK.
  - Fix: in `tests/ui/test_selection.py`, import `Gdk` inside the tests that use it, as
    `test_unknown.py` does.
  - Guard: a unit test that runs the unit discovery in a subprocess with PyGObject
    blocked (`sys.modules["gi"] = None`), skipping itself inside that subprocess through
    an environment variable, so a module-level GTK import in a test can't come back. Later,
    R22's CI runs the unit suite in a container without python3-gi.
  - Verify: the unit run with PyGObject hidden has no errors (today: 5); see
    [Commands](#commands).
  - Verify: a build in a clean Ubuntu 26.04 with only the Build-Depends installed (a
    container or sbuild) passes `dh_auto_test`.
  - Verify: on the desktop with NVIDIA's driver, `scripts/measure-drawing-stroke.py` still
    shows about 60 frames a second, and `webkit://gpu` still reports the GPU (R29f
    unchanged).
- [x] **CR42. Declare GTK versions.**
  - Fix: `gi.require_version(...)` before every `from gi.repository import …`, or one
    small module that every UI module imports first.
  - Verify: the unit run prints no PyGIWarning, and this command, which fails today,
    succeeds:
    `python3 -c 'import warnings, gi; warnings.simplefilter("error", gi.PyGIWarning); import notterizmus.ui.rows'`

Done when the clean build passes and the unit run is free of errors and warnings.

#### Phase 1 results

Worked on 2026-11-19. Both fixes are in and tested. CR1's last two checks were done later
the same day, once podman was installed and the screen was unlocked: the clean 26.04 build
passes (`dh_auto_test`: 400 tests, OK, 38 skipped; no PyGObject in the container), and a
stroke in the drawing window draws at 61 frames a second (see Phase 4 results).

- CR1: `_prefer_gpu` is now `gpu.prefer_gpu` in `notterizmus/gpu.py`, with no GTK. It is
  called at the top of `ui/app.py`, before GTK loads, and by
  `scripts/measure-drawing-stroke.py`. Its tests moved to `tests/test_gpu.py`, which also
  checks that order, and that no other module calls it when imported. That is CR41's GPU
  half: importing `drawing_web` no longer changes `os.environ`. `test_selection.py`
  imports Gdk inside the one test that uses it. The guard, `tests/test_without_gtk.py`,
  failed before the fix with the 5 errors and passes now.
- CR42: `notterizmus/ui/__init__.py` (the folder was a namespace package) declares Gtk,
  Gdk, Adw, Pango and Graphene once, before any UI module loads; `app.py`'s own
  declarations are gone. `tests/test_gi_versions.py` checks that every library a UI module
  imports has a declared version, and imports each UI module on its own with
  `PyGIWarning` as an error: 16 of the 17 warned before, none now. The review's command
  succeeds.
- Unit suite: 372 tests pass, 31 skipped, no warnings, in 5.0 s (2.1 s before; the guard
  runs the suite a second time). With PyGObject hidden: 372 pass, no errors (5 before).
- UI suite: 244 tests pass (the 4 GPU tests moved to the unit suite), 4 skipped, no
  warnings, in 194 s; with the real Excalidraw all 244 pass, in 199 s. Both took as long
  as in phase 0.
- Package build: none of podman, docker, sbuild or mmdebstrap is installed, so the clean
  26.04 build (see [Commands](#commands)) wasn't run. Instead the package was built from
  the tree with PyGObject hidden by the shim. At `5c90436` that build failed in
  `dh_auto_test` with the same 5 errors; with the fixes it builds (372 tests pass, 32
  skipped), the `.deb` holds both new modules, and lintian reports nothing. The next PPA
  upload is the real check (Release gate, step 6).
- Left for your desk: R29f's check. The screen was locked and the monitor off, so the
  drawing window got no frames and `scripts/measure-drawing-stroke.py` timed out on both
  of WebKit's paths. It should still show about 60 frames a second, with
  `WEBKIT_FORCE_DMABUF_RENDERER=1` and GTK's GL renderer (see
  [Manual checks](#manual-checks-on-the-desktop)).

### Phase 2: Data safety (M)

- [x] **CR4. Save the open chapter before switching.**
  - Fix: at the start of `Window.set_doc`, when another chapter is open and has a pending
    save, `_flush_save()` it. The scattered `self.save(quiet=True)` calls before
    `open_path` then become redundant.
  - Test (UI): open chapter A, type, then at once `win.open_path(B)` (what `App.do_open`
    does). A's file holds the typed text. The same through the Trash toast's Undo.
- [x] **CR3. Toast buttons undo only their own paste.**
  - Fix: remember the snapshot the paste committed, and the undo depth. `_resplit` and
    `_replace_with_plain` act only while that snapshot is still the current one;
    otherwise they say "The paste was changed since; use Ctrl+Z" and do nothing. Also
    dismiss the toast on the editor's next `changed` signal (`Window.toast` returns the
    `Adw.Toast` for that).
  - Test (UI): paste a three-line outline, type a word, run the toast's callback: the
    chapter is unchanged (no second copy, the word kept). Without the typing, the button
    still converts the paste.
- [x] **CR6. Renumbering that can't half-finish.**
  - Fix: `library.renumber` rolls back on any exception, not only `FileExistsError`:
    staged files go back under their original names and numbers, best effort, collecting
    the files it couldn't restore, and the exception is raised again. The same for the
    final rename loop. `set_chapter` makes every check (a free target name, duplicate
    numbers) before `renumber` moves anything.
  - Fix: at startup, or in `scan()`, offer to restore leftover `.moving-*.notz` files
    (a crash or power cut halfway also leaves them).
  - Test (unit): make `Document.save` or `Path.rename` fail at each step (the first write,
    the second write, the final rename). Afterwards every chapter is back under its
    original name and number, `scan()` lists them all, and no `.moving-*` file is left.
  - Test (unit): `set_chapter` into a book that has two chapters numbered 5 raises before
    any file moves.
- [x] **CR5. Earlier Versions follow swapped chapters.**
  - Fix: `backups.move` in two phases, like `renumber`: first move every source folder to
    a hidden temporary name, then each to its destination, merging only with copies
    already there that aren't part of this move.
  - Test (unit): swap untitled `01.notz` and `02.notz`; rotate three chapters with the same
    title. Afterwards each chapter's folder holds exactly its own copies, and the existing
    backup tests pass.
- [x] **CR12. Keep the cursor out of blocks from a newer version.**
  - Fix: a model helper (e.g. `editable_order(root)`) that leaves out the sub-items of
    blocks from a newer version, used by `KeysMixin._order()`, `_prev_text_node`,
    `focus_neighbor` and the selection code; rows are looked up with `.get()`.
  - Test (UI): in `test_unknown.py`, a block with sub-items. Backspace and Delete next to
    it don't join into it, nothing raises, and the block's JSON in the saved file is
    unchanged.
- [x] **CR25. Durable saves that keep permissions.**
  - Fix: in `Document.save`, flush and `os.fsync()` the temporary file, give it the
    existing file's mode (or `0o666 & ~umask` for a new file) before `os.replace`, then
    fsync the folder. Share this helper with CR22.
  - Test (unit): a 0644 chapter is still 0644 after a save; a new chapter follows the
    umask; `os.fsync` is called (patched).
- [x] **CR26. Backup names across daylight-saving changes.**
  - Fix: name new copies in UTC (`…Z`), read both forms, show local time.
  - Test (unit): two copies at 03:30 local time on 2026-10-25 (Europe/Sofia, the repeated
    hour) get distinct names and sort in the right order; copies with the old local-time
    names are still listed and thinned.
- [x] **CR10 (R16). Changes made on disk.**
  - Fix: remember the file's `st_mtime_ns` and size after loading and after each save.
    Before an autosave, if they changed, don't overwrite: keep both versions (save ours as
    a conflict copy) or ask Reload or Keep Mine.
  - Test (UI): change the open chapter's file on disk, then type. The other version isn't
    overwritten, and the choice is offered.

Done when all phase 2 tests pass, phase 0's checks are done and anything they found is
repaired. Then release (suggested 1.6.0).

#### Phase 2 results

Done 2026-11-19. All eight are fixed, each with tests that failed before the fix.

- CR4: `open_path` and `set_doc` first write an autosave that is still waiting
  (`_save_pending`), before the new file is read, since it may be the same chapter; F1
  writes the open chapter before it writes a fresh guide. The extra saves before
  `open_path` are gone. UI tests: a chapter opened through `App.do_open` (another one,
  and the open one itself), and the Trash toast's Undo.
- CR3: the paste toasts' buttons act only while the paste is still the last change
  (`undo_mark()` and `unchanged_since()` in the undo mixin); otherwise they say "The paste
  was changed since: use Ctrl+Z". The window dismisses such a toast on the editor's next
  change (`Window.toast` returns the toast now).
- CR6: `renumber` puts every chapter back on any error, without ever overwriting a
  chapter: a failed write at each step, a failed final rename, and with the disk still
  full at least the names come back. `set_chapter` checks everything first (a number two
  chapters share is refused) and undoes its swap if the final rename fails. Chapters left
  hidden by a crash are found by `library.stranded()` and named again by
  `restore_stranded()`, which the window offers at start-up and after a failed change.
  An existing test caught a mistake in my first version: a chapter's file counts as freed
  by a swap only if its number really changes.
- CR5: `backups.move` puts every moving folder aside first, so untitled chapters that
  swap, or chapters with one title that rotate, keep their own copies.
- CR12: `model.editable_order()` leaves out the sub-items of blocks from a newer version;
  the cursor uses it, and Backspace and Delete also check that the item they would join
  has a row before changing anything.
- CR25: `files.atomic_write` (new, no GTK) syncs the file before it replaces the old one
  and the folder after, and keeps the file's mode (a new file follows the umask).
  `Document.save` and the drawing previews use it; `state.json` can too (CR22).
- CR26: copies are named in UTC (`…Z.notz`), older local-time names are still read, and
  `Backup.when` carries its offset, so copies sort by when they were taken; thinning
  counts the time that really passed. Tested in Sofia's doubled hour on 2026-10-25; the
  backup tests pass in seven time zones, Lord Howe's half-hour change included. Two older
  tests built their copies by wall-clock time and now use real ages.
- CR10 (R16): a chapter remembers its file's inode, modification time and size when it
  reads or writes it. A save that finds the file changed asks "Changed on Disk": Reload
  (the default: your version goes to Earlier Versions, and Ctrl+Z brings it back) or Keep
  Mine (the other version goes to Earlier Versions first); Escape decides nothing. Where
  no answer can wait (another chapter opens, the window closes, a file operation), yours
  is written and the other is kept, never dropped for a copy taken in the same second; an
  open question counts as unsaved edits. Two of the UI tests found holes in my first
  version: a same-second copy that was dropped, and a question still open while another
  chapter opened. The change is noticed at the next save, not the moment it happens.
- Results: unit suite 395 tests pass (5.4 s), with and without PyGObject. UI suite 256
  tests pass (210 s; it ran just before the last test was added), and all 257 with the
  real Excalidraw (216 s) and in the load check (264 s).
- Left for you: the release (suggested 1.6.0, with 1.5.0's unbuilt fixes and phase 1), and
  phase 0's open question about the SDI notes.

### Phase 3: Broken or surprising behaviour (M)

- [x] **CR2. Shift+click after any kind of item selection.**
  - Fix: `set_selection` sets `sel_anchor` and `sel_head` (the first and last of the nodes
    in outline order) unless they are given. `on_click` falls back to `self.current` when
    the anchor isn't in the outline, as `extend_selection` does. `delete_items` and
    `clear_selection` reset the anchor.
  - Test (UI): Ctrl+W three times, then Shift+click another item: the range is selected and
    nothing raises. The same after clicking a drawing, and after deleting the anchor item.
- [x] **CR8. Toasts show text as it is.**
  - Fix: `use_markup=False` on the `Adw.Toast` in `Window.toast` and on the zoom toast.
    Check the other widgets that show user text and default to markup: `Adw.ActionRow`
    and `Adw.ComboRow` titles, and `Adw.ShortcutsItem`.
  - Test (UI): trash a chapter titled `Q&A <1>`. The toast's title is exactly that text,
    and the runner's warning check shows no markup error.
- [x] **CR7. Book names that stay inside the notes folder and visible.**
  - Fix: `library.safe_name` never returns a hidden name, ".", or "..". Replace a leading
    dot (".NET in Action" becomes "_NET in Action") and map "." and ".." to "Unsorted".
    The dialogs show the folder name that will be used. `scan()` keeps skipping dot-folders
    (`.Trash-1000`, Syncthing's `.stfolder`).
  - Test (unit): `safe_name` cases; chapters created the way New Chapter does it, in the
    books ".NET in Action", "." and "..", end up in a listed book folder inside the notes
    folder.
  - Test (UI): New Chapter in book ".NET in Action" appears in the list.
- [x] **CR15. New Chapter reports what goes wrong, and long names fit.**
  - Fix: catch `OSError` around New Chapter's `doc.save()` (a toast, and the dialog's
    values kept). `chapter_filename` and `safe_name` shorten names to 255 bytes of UTF-8;
    the full title stays inside the file, and the list shows the shortened name.
  - Test (unit): a 200-character Cyrillic title gives a file name of at most 255 bytes
    that round-trips through `parse_name`.
  - Test (UI): New Chapter with that title creates the chapter; an unwritable notes folder
    gives a toast.
- [x] **CR16. "Already exists" by chapter number.**
  - Fix: `library.chapter_numbered(folder, n)` instead of the glob.
  - Test: with only `100 Appendix.notz` in the book, New Chapter 10 creates chapter 10.
- [x] **CR11 and CR20. Top-level items stay numbered.**
  - Decide first (see [With you](#with-you)): keep the rule (README, the guide) or allow
    top-level bullets. Phase 0 shows whether your chapters already have any.
  - Fix, if the rule stays: `set_kind` refuses a bullet at the top level. The trigger code
    changes the kind first and deletes the typed trigger only when that worked (CR20).
    Ctrl+Shift+Space and the item-type menu leave out bullets at the top level.
    `insert_forest` turns bullets that land at the top level into numbered items, as
    `outdent` does.
  - Test (unit): `set_kind` at the top level.
  - Test (UI): "* " at the start of a top-level item keeps it numbered and keeps the text;
    "# " under a bullet keeps the typed "# "; pasting bullets into an empty first item
    gives numbered items. `test_guide` is unchanged.
- [x] **CR13. Delete Block deletes the whole block.**
  - Fix: the item menu's Delete Block uses `delete_items([node])` for blocks, like the
    trash button.
  - Test (UI): on a block from a newer version with sub-items, Delete Block removes it with
    its sub-items, and Ctrl+Z brings them back.
- [x] **CR14. Foreign clipboard data can't break a paste.**
  - Fix: `lexical.pasted_items` returns None on any error reading the data (add
    `TypeError`, `AttributeError` and `RecursionError`), and `_Reader.table` checks that
    `children` is a list. `_pasted` guards the app's own `…nodes+json` and `…runs+json`
    types and falls back to the next format.
  - Test (unit, `tests/test_drawing.py`): wrong types in every position and 10,000-deep
    nesting give None, without an exception.
  - Test (UI): with a bogus `application/x-notterizmus-nodes+json` on the clipboard,
    Ctrl+V pastes the plain-text alternative.
- [x] **CR17. The drawing window notices every change.**
  - Fix (`web/drawing/main.jsx`): at open, remember a version over all elements, deleted
    ones included (`getSceneVersion(api.getSceneElementsIncludingDeleted())`), and the kept
    appState; `changed()` compares both. Rebuild the page.
  - Test (UI, WebKit): through the page's API, delete an element and raise another
    element's version by the deleted one's version: `changed()` is true. A background
    change alone: true.
  - Manual: Cancel after such edits asks before discarding.
- [x] **CR19. Drawings land in the chapter they came from.**
  - Fix: while a drawing window is open, `App.do_open` doesn't switch chapters (it presents
    the drawing window and says why), and the done-callbacks act only on the chapter they
    were opened from.
  - Test (UI, with the tests' stand-in drawing window): open one, call `do_open` with
    another file, press Done. The drawing is in the original chapter, never in the other.
- [x] **CR21. Getting Started's words stay with the guide.**
  - Fix: keep those words in an ignore set inside `Speller` that applies only while the
    guide is open, instead of Enchant's session list.
  - Test (UI, skipped without an en_US dictionary): open Getting Started, then a chapter
    containing "TopCoding" and "Ctrl": both are underlined.
- [ ] **CR9 (R32). Ctrl+B and Ctrl+I with nothing selected.**
  - First reproduce it on the desktop, logging in `RichText._on_mark_set` who clears
    `_pending`. Compare `GTK_IM_MODULE=simple` with your usual input method, and the
    English with the Bulgarian layout.
  - Likely fix: drop the pending format only when the cursor moves to another offset
    (store the offset with `_pending`, update it after each insertion). Do it together
    with CR46.
  - Test (UI): toggle italic, place the cursor again at the same offset (as an input method
    may), type: the text is italic.
  - Manual: the guide's "Formatting and undo" exercise on the desktop.

Done when all tests pass and the manual checks for CR8, CR9 and CR17 are done.

#### Phase 3 results

Done 2026-11-19, except the checks at your desk. Each fix has tests that failed before it.

- CR2: `set_selection()` gives every selection ends (its first and last items) unless the
  caller set them inside it, and Shift+click falls back to the current item when the
  anchor is gone; `clear_selection()` and `delete_items()` reset them. UI tests: after
  Ctrl+W, after deleting the item a selection began at, and after clicking a drawing.
- CR8: toasts (the window's, the zoom toast, the drawing window's) have
  `use_markup=False`. The other rows that show your text are plain labels, or escape it;
  a book named `Q&A <1>` in Chapter Properties and a marker labelled `Pros & cons <x>` in
  the Shortcuts dialog showed no warning.
- CR7: `safe_name()` never returns a hidden name, "." or ".." (".NET in Action" becomes
  "_NET in Action"; the chapters keep the name you typed). I didn't add the folder name
  to the dialogs: the list shows it.
- CR15: names are shortened to 255 bytes in the file name only (`model.fit_name`), and
  New Chapter reports a file it can't write and asks again with what you typed.
- CR16: "already exists" goes by `library.chapter_numbered()`.
- CR11 and CR20: the rule stays, as README and the guide state it (your decision is open
  below; it is easy to reverse). `set_kind` refuses a top-level bullet, the menu and
  Ctrl+Shift+Space leave bullets out there, a paste turns top-level bullets into
  numbered items, and a typed trigger is deleted only when it applies.
- CR13: Delete Block goes through `delete_items()`, so a newer block keeps its sub-items.
- CR14: `lexical.pasted_items()` gives None on any error reading the data (10,000-deep
  nesting included), its table reader checks its lists, and the app's own clipboard JSON
  is read before it is used, falling back to the next format.
- CR17: `changed()` counts deleted elements too, and the kept view state. The page was
  rebuilt with the build script's steps but not its `npm ci` (no download; `node_modules`
  matched the lockfile); only `main.js` changed. The WebKit test failed against a build
  with the old `changed()`.
- CR19: the editor knows its drawing window; `App.do_open` brings it to the front and says
  why instead of opening the file, and Done acts only on the chapter it was opened from.
- CR21: `Speller.ignore_while_open()` passes the guide's words only while it is open.
- CR9: the pending format is dropped only when the cursor moves to another offset. Not
  reproduced on the desktop first, as planned (the screen was locked), so the box stays
  open until the manual check: the fix covers the likely cause, an input method setting
  the cursor again in place, which the UI test does.
- Results: unit suite 400 tests pass. UI suite 273 tests (222 s), all of them with the
  real Excalidraw (229 s) and in the load check (283 s); one old test expected CR20's
  behaviour (a refused trigger deleted) and now expects the fix.
- Left for your desk: the manual checks for CR8, CR9 and CR17 (Manual checks, below).

### Phase 4: Robustness and configuration (M)

- [x] **CR22. A state file that can't stop the app.**
  - Fix: move `load_state` and `save_state` to a module without GTK. Loading returns the
    defaults for a file that isn't an object, and per key for a value of the wrong type;
    saving is atomic (CR25's helper).
  - Test (unit): `[]`, `{"zoom": "big"}`, `{"last_file": 5}` and truncated JSON all give
    the defaults; a write that fails leaves the old file.
- [x] **CR23. A stricter rules check.**
  - Fix: `rules._problem` reports a trigger used twice or equal to the numbered-item
    trigger, and unknown `numbering.levels` names (listing the known ones).
  - Test (unit, `tests/test_rules.py`): each case is reported in `.error`, and the
    defaults are used.
- [x] **CR24. Paste labels.**
  - Fix: letter labels only as a single letter or a roman numeral (i, iv, xii), plus
    single Cyrillic letters (а), б), в)); longer words before ")" stay text.
  - Test (unit, `tests/test_importer.py`): "Yes) …" and "Also) …" stay text; "а) …" and
    "б) …" are labels; the app's own output and the existing hand-written examples parse
    as before.
- [x] **CR27. Error paths that tell the user.**
  - Fix: guard each path listed in the issue with a toast, or by skipping the faulty item.
  - Test (unit): a malformed metainfo file gives `(None, "")`; an `.aff` file with a bare
    `SET`, or with an unknown encoding, skips that dictionary.
  - Test (UI): `do_open` with a non-local `Gio.File` gives a toast, not an exception.
- [x] **CR31. A tighter drawing page.**
  - Fix: a narrower CSP, with scripts and styles as now:
    `default-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' data: blob:; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'`.
    Ignore download responses in `decide-policy`. Keep clipboard access only if
    Excalidraw's copy and paste need it.
  - Test: `NOTTERIZMUS_UI_WEBKIT=1 scripts/ui-tests.sh` (open, edit, Done, previews).
  - Manual, with `NOTTERIZMUS_WEB_DEBUG=1`: paste a picture, copy and paste shapes; the
    console shows no CSP errors.
- [ ] **CR30. Packaging.**
  - Fix: add `hunspell-bg` to `Recommends` in `debian/control`. Build the snap once (R17)
    and run it.
  - Verify: `lintian dist/*.deb`; the built package's `Recommends` lists hunspell-bg; the
    snap starts and opens a chapter in Documents.
- [x] **CR29. Leftovers in the drawing page.**
  - Check in the running drawing window whether Excalidraw still offers Mermaid or
    text-to-diagram. If it does, hide it through a stable hook (its `data-testid` or an
    Excalidraw option); hide the library the same way.
  - Test (UI, WebKit): the page has no Mermaid entry and no library trigger.
- [x] **CR47. Rectangular tables.**
  - Fix: square tables when they are read (pad short rows, as `importer._square` does), and
    `TableRow.rows` stops writing on read.
  - Test (unit): a ragged table loads square and keeps its cells' text.
  - Test (UI): delete a column of a table that was ragged in the file.

Done when all tests pass. Then release (suggested 1.6.1 or 1.7.0).

#### Phase 4 results

Done 2026-11-19, except the snap (CR30). Each fix has tests that failed before it.

- CR22: `state.py` (new, no GTK) reads `state.json`: a file that isn't a JSON object counts
  as empty, and a setting of the wrong kind is left out, so the window's default applies;
  saving goes through `files.atomic_write`, and a failed save no longer raises.
- CR23: the rules check reports a marker with the numbered item's trigger, two markers
  with one trigger, and unknown `numbering.levels` names (listing the known ones). Your
  own `rules.toml` passes.
- CR24: a label of one part is a number, a roman numeral or a single letter, Cyrillic
  ones included, so "Yes) …" stays text; dotted labels keep letter parts ("Ⅱ.1.ab)"), and
  with letters at the top level so does a single part, so the app's own labels still
  round-trip.
- CR27: a file opened from outside this computer, the rules template, Undo's write-back,
  a moved chapter that can't be read, a broken metainfo file and an `.aff` file with a
  bare `SET` or an unknown encoding now give a toast or are skipped.
- CR31: the narrower CSP (no frames, objects, forms; `img-src data: blob:` for pictures),
  download responses refused and downloads cancelled. Clipboard access stays on until
  copy and paste in the drawing window have been tried without it. WebKit's console
  doesn't reach the test log, so the check is a WebKit test in the page itself: a `data:`
  and a `blob:` picture load, and a frame is refused (it loaded under the old CSP).
- CR29: More tools offered Mermaid to Excalidraw (it fails on the stub) and Web Embed
  (web pages the page may not load); both are hidden by their shared `data-testid`. No
  text-to-diagram entry is shown. The library's button stays hidden by its class, and the
  WebKit test now catches it if an Excalidraw upgrade brings it back. A synthetic 0 key
  didn't open the library; a real press is worth a look at your desk.
- CR47: tables are squared when read; `TableRow.rows` no longer writes on read.
- CR30: `hunspell-bg` is in Recommends. The snap wasn't built: snapcraft needs LXD or
  Multipass, which this machine doesn't have.
- Phase 1's desktop check, done this time: a stroke in the drawing window draws at 61
  frames a second (59 in the window), the app at 9% CPU, with WebKit's GPU path and GTK's
  GL renderer, as in R29f.
- Results: unit suite 412 tests pass, with and without PyGObject. UI suite 277 tests
  (223 s), all of them with the real Excalidraw (232 s) and in the load check (286 s).
- Released as 1.6.0 on 2026-11-19, together with phases 1–3: built in a clean Ubuntu
  26.04 container (podman, with only the Build-Depends) and then on Launchpad, whose log
  shows the 412 unit tests ran (38 skipped there). `lintian` shows nothing above pedantic.

### Phase 5: Performance and memory (M)

Measure first, on the same machine and chapters, change, and measure again. Record the
numbers in ROADMAP.md as R29 did.

- [x] **CR18. Free the sidebar's rows.**
  - Fix: the drag handlers find their row through the controller's widget when the event
    comes, without holding `row` or `ch`.
  - Test (UI, `tests/ui/test_freeing.py`): every chapter row is freed after `_rebuild()`,
    and the drag-to-reorder tests still pass.
- [x] **CR32. Earlier Versions opens at once.**
  - Fix: show the list at once, and fill in the item counts and "same as now" from an
    idle callback, or from a thread that only reads files and hands its results to the
    main thread.
  - Measure: open time for a 4 MB chapter with 54 copies (0.66 s today before anything
    shows; target under 0.1 s).
  - Test (UI): the subtitles appear (`wait_for`), and Restore still works.
- [x] **CR33. Re-measure only what changed.**
  - Fix: one pending re-measure at a time, only for rows that are new or whose prefix
    width changed.
  - Measure (R15): in a 500-item chapter, time Enter, Tab, Alt+↓ and undo, and count the
    re-measured views.
  - Test: the "nothing jumps" UI tests (`test_layout.py`, `test_window.py`) still pass.
- [x] **CR34. Count words once per popup.**
  - Fix: count the chapter's and the book's words when the popup opens; while typing,
    only the current word changes.
  - Measure: time per keystroke with a book of 30 chapters.
  - Test: the completion unit tests and the Ctrl+Space UI tests are unchanged.
- [x] **CR35. Hash a scene once.**
  - Fix: compute the preview key once per `reload()` and pass the path on; cache it per
    scene dict, since scenes are never changed in place (R29d).
  - Measure: `tests/ui/measure_drawings.py` with the chapter of 1 MB pictures.
- [x] **CR36. Linear helpers.**
  - Fix: replace slices in loops with index tracking or precomputed neighbours, and make
    `FindBar._show_current` clear each view once.
  - Measure: micro-benchmarks before and after (a 2,000-item layout, a 5,000-line paste,
    1,000 find matches); the unit tests are unchanged.

Done when the numbers are recorded, with no regression in the R29 drawing measurements.

#### Phase 5 results

Done 2026-11-19. The numbers, before and after, are in ROADMAP.md under "Code review phase
5 measurements"; `tests/ui/measure_drawings.py` has three new measurements for them
(Earlier Versions with 54 copies, a chapter of 500 items, Ctrl+Space in a book of 30
chapters).

- CR18: the chapter list's drag handlers find their row through the controller, so every
  chapter row is freed after a rebuild (0 of 2 before). UI test in `test_freeing.py`.
- CR32: Earlier Versions shows its list at once (67 ms instead of 893 ms for 54 copies of
  the 4 MB chapter) and fills in each copy's details from an idle callback, stopping if
  the dialog closes. UI test: "…" at first, then the details.
- CR33: after a refresh, only rows that are new or whose prefix changed are re-measured,
  with one pending timeout (0–3 views instead of about 500 per Enter, Tab or undo in a
  500-item chapter). The layout tests ("nothing jumps") pass unchanged.
- CR34: the chapter's and the book's word counts are taken once per popup (0.09 ms a key
  instead of 2.8 ms). A first measurement read 2.7 s a key: my mistake in its units, which
  a profile of one keystroke showed.
- CR35: a drawing row hashes a scene once, and only when its data is a new dict (opening
  the chapter with pictures blocks 218 ms instead of 243).
- CR36: the five helpers are linear. Joining 5,000 pasted lines takes 98 ms instead of
  16.8 s, and counting 100,000 words 75 ms instead of 1.4 s. The layout of 2,000 items
  was 6.5 ms either way (other work dominates at that size), and Find's change isn't
  measured.
- The full measurement run after the whole phase, against the one before it (the end of
  phase 4), shows no regression in the R29 drawing measurements: Done brings the drawing
  back into the chapter in 127–176 ms (134–179 before), opening a chapter with drawings or
  pictures blocks 191–284 ms (205–289), and typing, undo, autosave and backups are
  unchanged. The 8-drawing chapter's load read 10 ms instead of 7.7, in `Document.load`,
  which phase 5 didn't change: noise between runs.
- Results: unit suite 412 tests pass, with and without PyGObject. UI suite 279 tests on
  this commit's tree (224 s); with the real Excalidraw (233 s) and in the load check
  (288 s) on the working tree, which also had the first, test-only changes of phase 6.

### Phase 6: Test suite (S–M)

- [x] **CR51. Every confirmed bug has its test.** The tests are written with the fixes in
  phases 1–5. Here, check the list is complete: CR2–CR8, CR11–CR16 and CR18 each have a
  regression test that fails without the fix, and `test_freeing.py` covers the sidebar.
- [x] **CR50. Wait for conditions.**
  - Fix: replace `ui.pump(0.x)` followed by an assert with `ui.wait_for(cond, "...")`, and
    drop the pumps after synchronous actions. Replace `time.sleep(1.1)` in
    `tests/ui/test_backups.py` by giving the backup a time. Add a test that fails on new
    `ui.pump(0.` calls outside `tests/ui/support.py`.
  - Verify: the suite's duration before and after; five runs in a row and the load check
    without a failure.
- [x] **CR52. Precise assertions and release checks.**
  - Fix: `assertGreaterEqual`. `test_release.py` also checks README's title
    ("Notterizmus 1.5"). Allow a "## Unreleased" section above the newest release in
    CHANGELOG.md, and have `scripts/release.sh` refuse to build while it is there.
  - Verify: the unit tests; `scripts/release.sh deb` on a commit with "## Unreleased"
    refuses.

#### Phase 6 results

Done 2026-11-19.

- CR50: no UI test waits for a fixed time any more. All 85 `ui.pump(…)` waits in 16
  files (the review counted 80) and the `time.sleep(1.1)` are gone, and so are 14 fixed
  pauses passed to the helpers (`wait=0.3`, `wait=0.4`). Where the state comes later, the test waits for it with
  `ui.wait_for`, for example a dialog closed, a row scrolled into sight, a command run
  after Search Commands closed, or an underline back. The pumps that followed synchronous
  actions are dropped: file operations, actions, clipboard writes, a popover's `popup()`.
  Where a test checks that nothing changed, or a layout no state reports, it waits for
  painted frames with the new `ui.frames(n)`. `test_backups` no longer waits for the clock
  to pass a second: it dates the first copy back by the interval, which also exercises
  the real interval instead of setting it to 0. `test_mouse` waits only for what is left
  of GTK's double-click time since the last real press (`ui.past_double_click()`).
  `tests/test_ui_waits.py` fails on any `ui.pump(` or `time.sleep(` in `tests/ui` outside
  `support.py`, `broadway_input.py` and `measure_drawings.py`.
- CR50, durations: the UI suite's 279 tests take 170–172 s (five runs in a row,
  none failed) instead of 222–224 s; with the real Excalidraw 180 s instead of 233, and in
  the load check (on one CPU beside two busy loops) 232 s instead of 288, without a
  failure.
- CR51: each issue's regression test, and whether it failed on the code from just before
  its fixing commit (the fix's tests run on its parent, in a scratch clone). A file named
  without a folder is in `tests/ui`.

  | Issue | Test | Fails without the fix |
  |---|---|---|
  | CR2 | `test_selection`: `test_shift_click_extends_a_selection_however_it_was_made` | yes: the `ValueError` itself |
  | CR3 | `test_clipboard`: `test_the_toasts_button_leaves_an_outline_paste_alone_once_something_changed` | yes |
  | CR4 | `test_chapters`: `test_a_chapter_opened_from_files_saves_the_open_one_first` | yes |
  | CR5 | `tests/test_backups.py`: `SwapTest` (2 tests) | yes |
  | CR6 | `tests/test_library.py`: `InterruptedChangeTest`; `test_chapters`: `test_a_chapter_left_hidden_by_an_interrupted_change_can_be_restored` | yes, as errors: the fix added `restore_stranded` and `_offer_stranded`, which they call |
  | CR7 | `tests/test_library.py`: `test_a_book_name_never_becomes_a_hidden_folder_or_leaves_the_notes_folder`; `test_chapters`: `test_a_book_whose_name_starts_with_a_dot_is_listed` | yes, both |
  | CR8 | `test_chapters`: `test_titles_in_toasts_are_shown_as_they_are`; `test_window`: `test_your_own_marker_names_are_shown_as_they_are` | the toast test yes; the marker-names test passed before the fix too (a guard for the dialogs, not the bug) |
  | CR11 | `tests/test_model.py`: `test_a_top_level_item_cannot_become_a_bullet`; `test_editing`: `test_a_top_level_item_stays_numbered_and_a_refused_trigger_stays_typed`; `test_clipboard`: `test_bullets_pasted_at_the_top_level_become_numbered_items` | yes, all three |
  | CR12 | `tests/test_unknown_blocks.py`: `test_the_editors_order_leaves_out_its_children`; `test_unknown`: `test_keys_next_to_one_with_sub_items_leave_them_alone` | yes, both |
  | CR13 | `test_unknown`: `test_delete_block_removes_it_with_its_sub_items` | yes |
  | CR14 | `tests/test_drawing.py`: `test_data_of_the_wrong_shape_gives_nothing_and_never_raises` (well-formed JSON with the wrong types, as this review asked); `test_clipboard`: `test_unreadable_editor_data_on_the_clipboard_falls_back_to_the_text` | yes, both |
  | CR15 | `tests/test_library.py`: `test_long_names_fit_the_file_name_limit`; `test_chapters`: `test_new_chapter_with_a_long_title_or_where_it_cannot_be_written` | yes, both |
  | CR16 | `test_chapters`: `test_new_chapter_10_is_not_chapter_100` | yes |
  | CR18 | `test_freeing`: `test_the_chapter_list_frees_its_rows_when_it_is_rebuilt` | yes |

- CR52: `assertGreaterEqual` in `test_chapters`. `test_release.py` lets an
  `## Unreleased` section stand above the newest release in CHANGELOG.md, and checks the
  "Notterizmus X.Y" titles of README.md and FEATURES.md. `scripts/release.sh` refuses to
  build while `## Unreleased` is there. The README's release steps and PROJECT_CONTEXT's
  version rule say so. CHANGELOG.md has that section now, for what is done since 1.6.0
  (phase 5 and CR28). Checked: `scripts/release.sh deb` on a clean commit with the section,
  in a scratch clone, stops with that message and builds nothing.
- Found on the way, fixed after: a real key press in `RealKeysTest` timed out when the test
  ran right after some other modules, without the full suite's earlier mouse tests
  (`scripts/ui-tests.sh -k test_command_search -k test_clipboard -k test_window -k
  test_zoom …`, which picks up `test_zoom_keys`). HEAD before phase 6 did the same. Cause:
  Broadway sends a key to the surface it last gave keyboard focus, and
  `test_drawings.EvenSizeTest` presents plain windows with no transient parent and
  destroys them, so the focus stayed on a surface that was gone until a real click
  (`test_mouse`, in the full suite) moved it. `support.real_key`/`real_type` now present
  the main window first, and wait until it is active, when it isn't and no other window
  of ours is open (`_keys_to_window`). With it, that command passes (163 tests), and so do
  a full run (172 s), the WebKit run (180 s) and the load check (233 s).
- Results: unit suite 415 tests pass, with and without PyGObject (35 skipped
  without it). UI suite 279 tests: see the durations above.

### Phase 7: Code health, no change in behaviour (L)

Small and mechanical changes first; the window split last, once the earlier phases' tests
cover it. Each is a refactor, so the full unit and UI suites, unchanged, are the
verification, plus the checks named.

- [ ] **CR37.** One table of commands (title, action, accelerator, section, keywords) in a
  module without GTK, used by the app's accelerators, the Shortcuts dialog and Search
  Commands. A unit test checks that every accelerator appears in README.md; the guide test
  reads from the table.
- [x] **CR40.** One XDG helper in `paths.py`. `tests/test_paths.py` covers set, unset and
  empty variables for config, data and cache.
- [ ] **CR45.** Remove the unused parameter, the alias, the redundant `KeyError`s and the
  local imports. Free the Enchant dictionaries on shutdown, or drop the declaration. A
  pyflakes pass (`sudo apt install pyflakes3`, a development tool only) reports nothing
  new.
- [ ] **CR48.** Small helpers (`run_once(fn, *args)` returning `GLib.SOURCE_REMOVE`,
  `set_class(widget, name, on)`) instead of tuple-index lambdas and conditional method
  calls.
- [ ] **CR44.** Tests find dialogs through `get_visible_dialog()` and the widget tree;
  `chapter_rows()` moves to `tests/ui/support.py`; `drawing_web.shutdown()` is called when
  the app shuts down, or moves to the tests.
- [ ] **CR43.** Row classes with real attributes (`ChapterRow`, `BookRow`, menu rows), and
  `ChapterSidebar.focused_target()` instead of window.py reading `row._path`.
- [ ] **CR41.** Spelling state owned by the editor and passed to the views; the GPU
  environment set explicitly when the app starts (done with CR1). A test checks that
  importing `drawing_web` no longer changes `os.environ` (done with CR1:
  `tests/test_gpu.py` checks that only `ui/app.py` calls `gpu.prefer_gpu()` when imported).
- [ ] **CR39.** Kind changes and table edits happen inside `with self._op():`; the
  attributes the mixins share are listed at the top of `outline.py`. UI tests: each is one
  undo step.
- [ ] **CR46.** One context manager for programmatic buffer changes instead of three flags
  (together with CR9).
- [ ] **CR49.** An `AssistPopover` class, a menu-list builder and a `VersionsDialog` class
  out of the long functions.
- [ ] **CR38.** Split `window.py` as R14 split the editor (dialogs, chapter files, zoom and
  sidebar sizing), methods moved unchanged; `git diff --color-moved` shows only moves.

#### Phase 7 results

- CR40: `paths.config_dir()`, `data_dir()` and `cache_dir()` share one rule
  (`_xdg_home`: the variable when set and not empty, else under `$HOME`, else the password
  database's home), and `paths.data_dirs()` reads `$XDG_DATA_DIRS` for the metainfo and the
  Hunspell dictionaries. `rules.config_dir` is gone (its callers import it from `paths`),
  and `drawing.cache_dir()` is `paths.cache_dir() / "drawings"`. Only one thing changes: an
  empty `XDG_DATA_DIRS` now means the default list for the dictionaries too, as the XDG
  rule says and as the metainfo lookup already did (it used to mean `/usr/share` alone).
  `tests/test_paths.py` covers set, empty and unset variables for all three folders, the
  system list, and that rules, state and drawings use them. On the way: an unused
  `config_dir` import in `window.py` and three unused `import os`.

### With you

- [ ] **CR28 (R30).** The two real pastes between the app and TopCoding, and header cells
  with `headerState` 3 in the first column.
  - Header cells: done 2026-11-19. A header row's first cell gets 3 (row and column
    header) and its other cells 1, as TopCoding makes them from our HTML's `<th>` cells.
    Unit tests in `tests/test_drawing.py`; not released yet.
  - Left for you: the two real pastes, in chapter 999 of assignment 2522, the page you made
    for tests, in Chrome and in Firefox. Copy a chapter with a drawing in the app and paste
    it there; then select all there, press Ctrl+C, and paste into the app. Claude in
    Chrome's key events neither copy nor paste for real (tried 2026-11-19).
- [ ] Top-level bullets: are they allowed at all? Phase 3 kept the rule README and the
  guide state (top-level items are always numbered); say if you want bullets there.
- [x] The version numbers of the releases, and whether one should follow phase 1 at once:
  1.6.0 came after phase 4, with phases 1–4 (your call, 2026-11-19). Launchpad built it,
  so the PPA no longer stops at 1.4.0.
- [ ] The SDI notes in chapter 10's oldest copy (phase 0): copy them out before
  2026-11-24, or let them go.

## Verification

### Commands

```bash
# Unit tests (the Debian build runs these too)
python3 -m unittest discover -s tests -t .

# The unit tests without PyGObject, as in a clean build (CR1); expect no errors
shim=$(mktemp -d) && mkdir "$shim/gi" && echo 'raise ImportError("no PyGObject")' >"$shim/gi/__init__.py"
PYTHONPATH="$shim" python3 -m unittest discover -s tests -t .

# UI tests on a private Broadway display; they fail on any GTK or Python warning
scripts/ui-tests.sh
scripts/ui-tests.sh -k name          # only some

# The load check (PROJECT_CONTEXT): the suite on one busy CPU
taskset -c 0 python3 -c 'while True: pass' & taskset -c 0 python3 -c 'while True: pass' &
taskset -c 0 scripts/ui-tests.sh; kill %1 %2

# With the real Excalidraw (needs gir1.2-webkit-6.0)
NOTTERIZMUS_UI_WEBKIT=1 scripts/ui-tests.sh

# Drawing performance report, and a pen stroke on your own display (R29, R29f)
NOTTERIZMUS_UI_WEBKIT=1 NOTTERIZMUS_UI_TEST_TIMEOUT=900 scripts/ui-tests.sh -p 'measure_*.py'
scripts/measure-drawing-stroke.py

# The package
scripts/release.sh deb && lintian dist/*.deb
```

A build in a clean Ubuntu 26.04 with only the Build-Depends installed (CR1). This needs
podman or docker, or sbuild, none of which is installed on this machine yet, so the
command hasn't been run:

```bash
git archive --prefix=notterizmus/ HEAD | podman run --rm -i ubuntu:26.04 sh -euc '
  apt-get update -qq && apt-get install -y -qq build-essential debhelper dh-python python3 >/dev/null
  mkdir /b && cd /b && tar -x && cd notterizmus && dpkg-buildpackage -b -us -uc'
```

Without a container, a local build with PyGObject hidden by the shim catches a GTK import
in the tests (CR1), though not other missing Build-Depends. It reproduced Launchpad's
failure before phase 1:

```bash
shim=$(mktemp -d) && mkdir "$shim/gi" && echo 'raise ImportError("no PyGObject")' >"$shim/gi/__init__.py"
work=$(mktemp -d) && git archive --prefix=notterizmus/ HEAD | tar -x -C "$work"
(cd "$work/notterizmus" && PYTHONPATH="$shim" dpkg-buildpackage -b -us -uc)
```

### Checks of your notes

Read-only. They find what the bugs may already have done (phase 0).

```bash
notes="$(xdg-user-dir DOCUMENTS)/Notterizmus"

# CR6: chapters left under a hidden staging name by a failed reorder
find "$notes" -name '.moving-*.notz'

# CR7: hidden book folders, and chapters saved loose in the notes folder or in Documents
find "$notes" -mindepth 1 -maxdepth 1 -type d -name '.*'
ls "$notes"/*.notz "$notes"/../*.notz 2>/dev/null
```

```bash
# CR11: top-level bullets in your chapters
python3 - "$(xdg-user-dir DOCUMENTS)/Notterizmus" <<'EOF'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
for p in sorted(root.glob("*/*.notz")):
    try:
        content = json.loads(p.read_text(encoding="utf-8")).get("content") or []
    except ValueError:
        continue
    n = sum(1 for c in content if isinstance(c, dict) and c.get("kind") == "bullet")
    if n:
        print(f"{p.relative_to(root)}: {n} top-level bullet(s)")
EOF
```

```bash
# CR5: backup folders with copies of more than one chapter number. Renaming or reordering
# a chapter also does this; a merge shows two chapters' texts alternating in time.
python3 - "${XDG_DATA_HOME:-$HOME/.local/share}/notterizmus/backups" <<'EOF'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
for folder in sorted(p for p in root.glob("*/*") if p.is_dir()):
    numbers = set()
    for f in folder.glob("*.notz"):
        try:
            numbers.add((json.loads(f.read_text(encoding="utf-8")).get("chapter") or {}).get("number"))
        except ValueError:
            pass
    if len(numbers) > 1:
        print(f"{folder.relative_to(root)}: copies numbered {sorted(numbers, key=str)}")
EOF
```

### Manual checks on the desktop

Things the test displays can't show. Do them before each release that contains the fix.

- [ ] CR9: with nothing selected, Ctrl+I then typing gives italic text, and Ctrl+B bold;
  with your usual input method, in the English and the Bulgarian layout.
- [ ] CR8: move a chapter titled "Q&A" to the Trash. The toast reads "“Q&A” moved to
  Trash", and Undo brings the chapter back.
- [ ] CR17: in the drawing window, delete one element and nudge another a few times with
  the arrow keys, then Cancel: it asks before discarding. Change only the background, then
  Cancel: it asks.
- [ ] CR32: Earlier Versions on your largest chapter opens at once.
- [ ] CR7 and CR15: New Chapter in book ".NET in Action" with a long Bulgarian title shows
  up in the chapter list.
- [ ] CR1 and CR41: with NVIDIA's driver, a stroke in the drawing window still draws at
  about 60 frames a second (`scripts/measure-drawing-stroke.py`).
- [ ] CR10: edit a chapter, change its file from another program, keep editing: you are
  asked, and neither version is lost.
- [ ] CR28: the real pastes with TopCoding, in chapter 999 of assignment 2522.

### Release gate

For each release, the steps from README.md and PROJECT_CONTEXT.md, plus the checks above:

1. Bump the version in `notterizmus/__init__.py`, the metainfo `<release>`, CHANGELOG.md,
   `debian/notterizmus.1` and `debian/changelog` (through `dch`); `tests/test_release.py`
   checks that they agree. Name the fixed CR issues that users notice in CHANGELOG.md and
   the release notes.
2. Commit. `scripts/release.sh` builds from the last commit and refuses uncommitted or
   untracked files, this one included.
3. `scripts/ui-tests.sh`, and the load check for phases that touched timing.
4. Phase 1 onward: build once in a clean Ubuntu 26.04 (container or sbuild), or at least
   with PyGObject hidden (see [Commands](#commands)).
5. `scripts/release.sh deb`, install it, do the manual checks, and check that
   `lintian dist/*.deb` shows nothing above pedantic.
6. When you say so, `scripts/release.sh ppa`. Then confirm on Launchpad that the build
   succeeded and that its log shows the unit tests ran.
7. Update ROADMAP.md ("Where things stand") and PROJECT_CONTEXT.md where a rule changed
   (new modules without GTK, the state module, the command table).

## How the confirmed issues were checked

The ✔ issues were found again by small throwaway programs, not kept in the repository:
calls into the real modules in temporary folders, and UI probes run on the UI tests'
private Broadway display through a copy of `scripts/ui-tests.sh` pointed at a scratch test
module. Those probes asserted the faulty behaviour. The tests in this roadmap assert the
correct behaviour, so each fails before its fix and passes after it.
