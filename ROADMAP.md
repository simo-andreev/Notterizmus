# Notterizmus roadmap

Written 2026-11-06 after 1.1.0; brought up to date on 2026-11-17, after 1.4.2.
Items have IDs so we can refer to them.

Sizes: **S** one focused change · **M** several changes across modules ·
**L** needs a research spike before it can be sized.

## Decisions so far

- **Audience**: mainly you, and maybe other students on the TopCoding course
  later. Distribution (R17–R22) comes after the daily-use items, but before the
  app is shared with the course.
- **Order**: daily-use items come before drawings.
- **What slows you down now**: learning the controls. R23 and R24 were added to
  the daily-use items for that.
- **Source code**: public, on GitHub and Launchpad (R22).
- **Stores**: both the Snap Store and Flathub (R17, R21).
- **App ID**: `dev.simo_andreev.notterizmus`, all lowercase, from your domain
  `simo-andreev.dev` (R25). Flathub allows a dash only in the last part of an
  ID, so the domain's dash becomes an underscore, and Flathub turns it back into
  a dash when it verifies the domain. The ID passes the AppStream, desktop-file
  and GLib checks without warnings; the current ID gets a pedantic AppStream
  hint for its capital letter.
- **Sidebar follow-ups** (after R1): resizing the sidebar (R27), renaming a book
  (R28), and renaming and reordering chapters (added to R2).
- **Ubuntu releases**: 20.04 onwards, using options A + D from
  [Ubuntu support](#ubuntu-support). The PPA covers 26.04 and newer, and the
  snap covers 20.04–24.04.
- **Platforms**: Linux only for now. A Windows or macOS port would add a lot of
  complexity to a tool that may end up used only by you.

## Where things stand

As of 2026-11-17:

- 1.4.2 was uploaded to the PPA, for Ubuntu 26.04 only. Users on 26.10 get
  nothing from it yet (R19), and 24.04 and older need the snap (R17).
- One user so far; one book, six chapters, the largest with 192 items. One
  chapter has three drawings and is the largest file: 257 KB, 137 KB of it the
  drawings' scenes.
- Strong: outline editing, clean paste into TopCoding, bilingual spelling and
  word completion.
- Closed since 1.1.0: the chapter list (R1), find (R3), earlier versions (R4),
  unknown block types (R6), drawings (R12), UI tests (R13) and the editor split
  (R14).
- Gaps found in the README's known limits and in the reviews:
  - An item is a single paragraph (R7).
  - Connectors drift in TopCoding's proportional font (R11).
  - Undo is lost on close; Earlier Versions (R4) is the way back.
  - Drawings haven't been pasted for real between the app and TopCoding, in
    either direction (R30).
  - An autosave can overwrite a chapter that a sync tool changed on disk (R16).
  - The UI is English only (R20).
  - The app doesn't show up in App Center search (R17).
  - The GitHub repository has no CI (R22).

## Bugs to fix

| ID | Bug | Why | Size |
|---|---|---|---|
| R32 | **Ctrl+I with nothing selected doesn't toggle italic** for the text typed next (reported 2026-11-18). The Getting Started chapter says it should (`guide.py`, "Formatting and undo"). Check Ctrl+B in the same state too | Italic has to be typed first and selected afterwards | S |

## Proposed releases

The groups were first planned as 1.2, 1.3 and 2.0. The daily-use items shipped
in 1.2.0 and 1.3.0 and drawings in 1.4.0, so the groups are now named by theme
and get a version number when they ship.

### Daily-use gaps — done in 1.2.0 and 1.3.0

| ID | Item | Why | Size |
|---|---|---|---|
| R23 | **Getting Started chapter**: F1, the menu or the start page opens a practice chapter that explains each control as an outline you can edit, with the keys in bold | You're still learning the controls. The shortcuts dialog lists the keys but doesn't show them in use | S. **Done** in 1.2.0 |
| R24 | **Command search**: one shortcut opens a search over every command; type a few letters to find and run one, with its shortcut shown next to it | You can use a feature before you remember its key, and you see the key each time you use it | M. **Done** in 1.3.0: Ctrl+Shift+P |
| R1 | **Chapter sidebar**: books and chapters in a collapsible side panel; click to open; Ctrl+PgUp / Ctrl+PgDn for the previous or next chapter | The file dialog is the only way to switch, and it gets slower with every chapter | M. **Done** in 1.2.0; F9 shows or hides it |
| R2 | **Chapter rename and order**: rename a chapter or change its number; reorder chapters by dragging them in the sidebar (or Alt+↑/↓ there); move one to another book or to Trash. Reordering renumbers the files (`<NN> <Title>.notz`) and the number stored in each chapter | The number and title are fixed at creation and are part of the filename, so chapters can't be renamed or put in a different order | M. **Done** in 1.2.0: F2 opens Chapter Properties; reordering hands out the book's existing numbers |
| R28 | **Rename a book** from the sidebar: renames its folder and the book name stored in each of its chapters; refuses a name another book already has | A book's name is fixed when its first chapter is created | S. **Done** in 1.2.0 (F2 on a book in the list) |
| R27 | **Resizable sidebar**: drag the edge between the chapter list and the text; the width is remembered. The split view used now has no drag handle, so this needs one of our own (or a `Gtk.Paned` in the wide layout, keeping the overlay for narrow windows) | Long book or chapter titles get cut off at the fixed width | S. **Done** in 1.2.0: a handle over the edge; double-click resets |
| R3 | **Find and replace** in the chapter (Ctrl+F, Ctrl+H): matches highlighted across items, with case and whole-word options | There is no find at all | M. **Done** in 1.3.0 |
| R4 | **Rolling backups**: keep the last few saved versions of each chapter and restore one from the menu | Autosave overwrites the only copy. A bad paste followed by closing the app can't be undone | S. **Done** in 1.3.0: Earlier Versions in the menu |
| R5 | **Zoom**: Ctrl+= / Ctrl+- / Ctrl+0, remembered | Text size is fixed in CSS | S. **Done** in 1.3.0; also Ctrl + scroll and a menu row |
| R6 | **Unknown block types**: show them as a read-only "made with a newer version" row and leave them out of Copy for TopCoding | A file with a drawing (R12) opened in an older version would otherwise show an empty item; text typed there isn't saved | S. **Done** in 1.2.0. Also keeps unknown fields of known items (1.1 dropped them) |

### Richer notes — not started

| ID | Item | Why | Size |
|---|---|---|---|
| R7 | **Line breaks inside an item** (Shift+Enter): continuation lines are indented under the label, with `│` where the tree continues; exported as `<br>` | Listed known limit; quotes and short lists need it | M (touches model, layout, export and paste) |
| R8 | **Fold sections**: click a label or press Ctrl+. to fold; the folded state is saved per chapter and doesn't affect export | Long chapters | M |
| R9 | **Search the book** (or all books); results open the chapter at the match | Builds on how completion already reads the other chapters | M |
| R10 | **Drag to reorder**: drag an item by its prefix to move it or change its level | Alt+↑/↓ is the only way to move items | M |
| R11 | **Connectors that line up in TopCoding**: pad with Unicode spaces sized to Roboto's character widths so the `│` columns align | Listed known limit. `export.code_prefix` aligns them but adds a code background | L (spike: measure in the browser and confirm TopCoding keeps those spaces) |
| R33 | **`!` and `?` bullet types** for important points and for uncertain ones (added 2026-11-18): built-in markers next to `•`, `+` and `-`, typed as `! ` and `? ` at the start of an item and reached by Ctrl+Shift+Space. Today they can only be added by hand in Edit Formatting Rules | Marks what to remember and what to check later, and the marks travel with the notes to TopCoding | S |

### Drawings — done in 1.4.0

| ID | Item | Why | Size |
|---|---|---|---|
| R12 | **Excalidraw block**. Spike first: can a native app put Lexical's clipboard JSON (`application/x-lexical-editor`) on the clipboard so that Chrome on Linux passes it to TopCoding? Then choose how to edit drawings: an embedded Excalidraw (adds a WebKitGTK dependency) or opening excalidraw.com and pasting the drawing back | The planned block type; TopCoding has a native Excalidraw node | L. **Done** in 1.4.0: embedded Excalidraw in WebKitGTK, bundled for offline use; Ctrl+D. Paste spike (2026-11-17): TopCoding's Excalidraw node has no HTML import, so a chapter with a drawing is copied as Lexical clipboard JSON inside Chrome's `chromium/x-web-custom-data` (`lexical.py`), and since 1.4.1 inside Firefox's `application/x-moz-custom-clipdata` too; the editor accepts that JSON (synthetic paste, same text and tables as the HTML path). The real pastes are still to try (R30) |

### Drawing follow-ups

Added 2026-11-17, after drawings shipped in 1.4.0.

| ID | Item | Why | Size |
|---|---|---|---|
| R29 | **Excalidraw performance**. Measure first, as in R15: time to open the drawing window, typing and drawing delay inside it, time to Done, preview rendering when a chapter with several drawings opens, and the effect of large scenes (pasted images) on autosave, undo and Earlier Versions. Then fix what is slow. Candidates: keep one warm, hidden web view instead of starting a new one (and a new web process loading the 5.6 MB bundle) for every Ctrl+D or Edit Drawing; render previews in parallel or ahead of time; keep scene data out of the undo snapshots. Undo turns the whole chapter into JSON after every edit, drawings included, and keeps up to 500 such snapshots | Drawings are new and untested at the scale of a real chapter; each one adds a WebKit page and its scene to every save and undo step. The one real chapter with drawings is 257 KB, 137 KB of it the scenes of its three drawings | S to measure, then M |
| R30 | **Excalidraw copy and paste polish**. First confirm the two untried real pastes: the app → TopCoding in Chrome (Ctrl+V into the notes editor), and TopCoding → the app (a real Ctrl+C there, read by `lexical.pasted_items`; built after 1.4.2, not released yet). Fix what they turn up. Then, to be agreed: paste a selection copied in Excalidraw itself (excalidraw.com or the drawing window) as a new drawing; offer a copied drawing as a PNG too, for apps that don't take Excalidraw scenes; and match the header cells TopCoding makes from HTML (we write `headerState` 1 everywhere, it uses 3 in the first column) | Copy and paste is how drawings reach TopCoding, and both directions are built only from synthetic pastes and checked node shapes | M |

### Review assistant

| ID | Item | Why | Size |
|---|---|---|---|
| R31 | **Built-in LLM review box**: a panel beside the chapter where a language model reviews the notes, for example gaps against the chapter's headings, unclear or wrong statements, and spelling and grammar in English and Bulgarian. Suggestions are shown for you to accept one at a time, each as an undo step; nothing is changed without you. Spike first: which provider and model, where the API key is kept, how the chapter is sent (the app makes no network requests today, and the project has no pip dependencies, so plain HTTPS from the standard library), what is sent (text only, or drawings as pictures too) and what it costs | A second reader for the notes before they go to TopCoding | L (spike: provider, privacy and cost, see Open questions) |

## Foundations (alongside the daily-use items)

| ID | Item | Why | Size |
|---|---|---|---|
| R13 | **UI tests**: turn this project's test-harness scripts (drive keys, step the GTK main loop, check row positions frame by frame) into `tests/ui/` that run without a visible window | The hidden cursor and the tall first item were caught by hand | M. **Done**: `scripts/ui-tests.sh`; real key presses through Broadway since 1.3.1 |
| R14 | **Split `ui/outline.py`** into keys, selection, clipboard, menus, multi-cursor and undo modules, with no change in behavior | Every item above lands in this one file | M. **Done** in 1.3.1: `outline.py` plus eight `outline_*.py` mixins, methods moved unchanged |
| R15 | **Large-chapter check**: generate a 500-item chapter and measure open time, typing delay and memory. Only if it's slow, create rows lazily | Every item is its own GtkTextView; the largest real chapter has 192 items (56 on 2026-11-06) | S to measure |
| R16 | **Changes on disk**: notice when the open file changes outside the app (Syncthing, Nextcloud, a second machine) and offer to reload | Chapters are plain JSON in Documents, so they're easy to sync. Without this, an autosave could silently overwrite the other copy | S |

## Distribution and reach

| ID | Item | Why | Size |
|---|---|---|---|
| R25 | **New app ID** `dev.simo_andreev.notterizmus`. Rename 11 files (desktop entry, metainfo, MIME definition, 8 icons) and update the ID wherever `git grep dev.simo.Notterizmus` finds it (`APP_ID`, `debian/install`, `debian/copyright`, `snap/snapcraft.yaml`, `install.sh`, the renamed files themselves, docs). Add a `<replaces>` entry for the old ID `dev.simo.Notterizmus` to the metainfo so App Center treats the PPA upgrade as the same app. The `.notz` MIME type and `~/.config/notterizmus` stay as they are | Flathub accepts only IDs whose domain you control, and it doesn't allow a rename shortly after acceptance, so the new ID has to come first | S |
| R26 | **A page on `simo-andreev.dev`** (for example GitHub Pages on that domain) that links to the app and serves Flathub's verification file at `/.well-known/org.flathub.VerifiedApps.txt`. A DNS TXT record at `_flathub.simo-andreev.dev` also works for verification | The domain has no website yet. Flathub wants the domain reachable over HTTPS and prefers a page linking it to the app; the page can also be the app's homepage in App Center | S |
| R19 | **Every current Ubuntu release in the PPA**: copy each app version to 26.10 (`stonking`) and to each new Ubuntu release as it comes out (Launchpad copies the built package; nothing is rebuilt) | 26.10 users can't install the app today | S per release |
| R22 | **Public source repository**: GitHub for issues and CI (unit tests, lintian, release checks); Launchpad imports it, so snap builds (R17) and the PPA live next to the code | Needed for R17, R18 and R21, and for bug reports from others | S. **Partly done**: public on GitHub (`simo-andreev/Notterizmus`) with issues on; no CI yet; the Launchpad import isn't checked |
| R17 | **Snap Store**: Launchpad builds the snap from the repository and uploads it to the store, so publishing doesn't need snapcraft and LXD on your machine (they're still the quickest way to test). App Center search then finds the app, and the snap covers Ubuntu 20.04–24.04 | Today App Center lists the app only once it's installed, and the PPA can't reach older releases | M (needs your store account) |
| R18 | **Store listing**: screenshots and a short feature list in the AppStream metadata | Shown by App Center, the Snap Store and Flathub; screenshots need a public URL (R22) | S |
| R21 | **Flathub**: GNOME runtime, the English and Bulgarian dictionaries bundled, and access to the Documents folder (checked against the localized path, as was done for the snap) | Reaches Linux Mint, Fedora and other distributions where snaps are rare | M |
| R20 | **Translations**: gettext and a Bulgarian UI | Your desktop is in Bulgarian, and course students would expect it too | M |

## Ubuntu support

What each release ships, checked on Launchpad on 2026-11-06, compared with
what the app needs: GTK 4.12, libadwaita 1.8 (1.5 apart from the shortcuts
dialog) and Python 3.11.

| Release | Support | GTK | libadwaita | Python | Native package possible? |
|---|---|---|---|---|---|
| 20.04 `focal` | Ubuntu Pro (ESM) only since 2025 | none | none | 3.8 | No |
| 22.04 `jammy` | until 2027 | 4.6 | 1.1 | 3.10 | Only with fallbacks for about ten widgets |
| 24.04 `noble` | until 2029 | 4.14 | 1.5 | 3.12 | Yes, with a fallback for the shortcuts dialog |
| 26.04 `resolute` | until 2031 | 4.22 | 1.9 | 3.14 | Yes (today) |
| 26.10 `stonking` | until mid-2027 | 4.24 | 1.10 | 3.14 | Yes, by copying the package |

| Option | Covers | Pros | Cons | Work |
|---|---|---|---|---|
| **A. PPA for current releases** (R19) | 26.04, 26.10 and newer | No code changes; native look and speed | Nothing before 26.04, so 24.04 LTS users are left out | S per release |
| **B. A plus 24.04 in the PPA** | adds 24.04 | Native on the previous LTS; small code change | Every release must also be tested on GTK 4.14, where the text-view workarounds may behave differently; slightly older look; newer libadwaita widgets need fallbacks | S–M once, then a test pass per release |
| **C. B plus 22.04 in the PPA** | adds 22.04 | Native on 22.04 | Fallbacks for about ten widgets and the scrolling code, Python 3.10, GTK 4.6's older text view; doubles testing for a release whose standard support ends in 2027 | L, ongoing |
| **D. Snap for older releases** (R17) | 20.04 and newer, with one build | Same GTK and libadwaita as 26.04 everywhere; snapd is preinstalled on Ubuntu; App Center search finds it; updates arrive automatically; the only way to reach 20.04 | The first install also downloads the shared GNOME runtime (`gnome-core26`, about 500 MB); slower first start; settings live in `~/snap/notterizmus/` (notes stay in Documents); installing both the snap and the PPA package gives two icons | M once |
| **E. Flathub** (R21) | 20.04 and newer, plus other distributions | Reaches beyond Ubuntu | Not preinstalled on Ubuntu and not shown in App Center, so users install Flatpak and add Flathub first (on 20.04 from the Flatpak PPA, since the archive has Flatpak 1.6 from 2020) | M once |

**Chosen: A + D** (2026-11-06), with E coming later through R21. That covers
20.04 onwards with a single code path. B and C are dropped. When R19 and R17
land, the README's install section should say: PPA for 26.04 and newer, snap
for 20.04–24.04.

Publishing both the snap and the Flatpak has no major drawback. The costs are:
- two build manifests to keep working;
- dictionaries bundled in each;
- settings stored in a different folder per package type;
- the app ID change (R25), done once, before either store sees the app.

## Not planned

- General word processing or Markdown. The README keeps the scope to chapter notes.
- Built-in sync or accounts. The files are plain JSON in Documents, and R16
  makes folder-sync tools safe to use.
- Undo that survives closing the app. R4's backups cover recovery more simply;
  say if you still want it.
- Paste targets other than TopCoding (Google Docs, Notion). The HTML may already
  work there, but it's untested and not designed for.
- Windows and macOS. Linux only for now (decided 2026-11-06).
- Native PPA builds for 22.04 and 24.04. The snap covers them (options B and C
  under Ubuntu support).

## Suggested order

1. R23, then R13 and R6. R23 helps you right away. Tests come before the big
   changes, and R6 should be on users' machines well before any file contains a
   drawing. **Done.**
2. R2 and R28 (renaming and reordering), R27, R4, R24, then R3 and R5. **Done.**
3. R14, the split, once the tests cover the keys and clipboard. **Done.**
4. Before sharing with the course: R25 (the new ID), R19, R22 with R26, R17
   and R18, and later R21 and R20. R22 is partly done.
5. Richer notes in the order R7, R8, R9, R10, with R11 as a separate spike.
6. Drawings (R12). **Done** in 1.4.0, ahead of steps 4 and 5.
7. Added 2026-11-17 and not yet placed against steps 4 and 5: R30's two
   real-paste checks, which are quick; then R29's measurements, R30's fixes and
   R31's spike.
8. Added 2026-11-18: the R32 fix, at any time; R33 with the richer notes in
   step 5.

## Open questions

- **R31, the review box**: which provider and model (a cloud API, or a local
  model that keeps notes on the machine)? Is a paid API key acceptable? "Not
  planned" rules out built-in accounts, and a provider key is close to one.
  What should a review check: content against the book, wording, spelling,
  the outline's structure?
- **R30**: which of the candidate polish items matter to you (Excalidraw → app
  paste, PNG copy, matching TopCoding's header cells)?
