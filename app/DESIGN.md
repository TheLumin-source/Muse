# Muse

A local visual board, in the spirit of Milanote. Infinite canvas, drag things
onto it, arrange them until the idea makes sense. Everything lives on this
machine, in plain folders you can back up or open in a text editor.

Working name. Renaming it is a find-and-replace on "Muse" plus the folder name.

## Shape

Same pattern as socialcast: FastAPI backend, vanilla-JS frontend, no build step.
`run.py` starts uvicorn on 127.0.0.1 and opens a pywebview desktop window
(`--browser` opens a normal browser tab instead).

```
Muse\
  app\
    run.py            launcher (uvicorn + desktop window)
    muse.ico
    muse/
      app.py          FastAPI routes
      store.py        projects and boards on disk
      links.py        URL preview fetching
    frontend/
      index.html
      styles.css
      js/*.js         ES modules, served as-is
  settings.json       last project and board opened
  Projects/           your data
```

Code and data are siblings under one folder deliberately: the Muse folder is the
whole thing, backup and all.

## Storage

One folder per project, one folder per board inside it. No database.

```
Projects/
  Studio rebrand/
    project.json
    boards/
      b_7f3a91/
        board.json
        board.bak.json
        assets/
          img_2c81.png
          spec.pdf
```

Project folders carry the project's own name rather than an id, because the
point of projects is that you can pick one up and move it. Renaming a project
renames the folder when Windows allows it; `project.json` holds the id and is
the authority if the two ever drift.

`board.json` is the whole board: elements, connectors, view position. Written
atomically (temp file + replace) so a crash mid-save can't shred a board, with
the previous generation kept beside it as `board.bak.json` and read
automatically if the main file ever fails to parse. Nested boards are separate
folders linked by id, not nested directories, so moving a board between parents
is a field change rather than a file move.

### Never losing work

Four overlapping mechanisms, because "it closed and I lost an hour" is the one
failure this app cannot have:

1. debounced save 500 ms after the last change
2. a 15 second sweep that saves anything still dirty
3. `pagehide`, `visibilitychange` and `beforeunload` force a flush, using
   `sendBeacon` to a POST route so it survives the page being torn down
4. the pywebview window intercepts its own close, triggers that flush and holds
   for 400 ms so the beacon reaches the server before the process ends

### board.json

```json
{
  "id": "b_7f3a91",
  "title": "Ideas",
  "parent_id": null,
  "created": "2026-07-22T10:00:00",
  "modified": "2026-07-22T10:31:00",
  "view": { "x": 0, "y": 0, "zoom": 1 },
  "elements": [ ... ],
  "connectors": [ ... ]
}
```

### Elements

Common fields: `id, type, x, y, w, h, color, parent` (parent = column id or
null). Type-specific:

| type     | extra fields                                  |
|----------|-----------------------------------------------|
| `note`   | `text` (rich text HTML), `title`              |
| `todo`   | `title`, `items: [{id, text, done}]`          |
| `image`  | `src`, `nw`, `nh` (natural size), `caption`   |
| `link`   | `url`, `title`, `desc`, `site`, `thumb`       |
| `file`   | `src`, `name`, `size`, `ext`                  |
| `board`  | `board_id`, `title`, `preview` (child colours)|
| `column` | `title`, `children: [element ids]`            |
| `text`   | `text` (plain heading text on canvas)         |

A column owns its children by id; children keep `parent` set and are laid out
by the column, so their own x/y are ignored while contained.

### Connectors

```json
{ "id": "c_1", "from": "el_a", "to": "el_b", "arrow": "end", "color": "slate" }
```

Endpoints are element ids; the path is recomputed from live geometry on every
render, so lines follow cards as they move. A free-floating endpoint is stored
as `{ "x": 100, "y": 200 }` instead of an id.

## Interaction model

The bits that make Milanote feel like Milanote, in priority order:

1. **Drag from the tool rail onto the canvas**, not "click tool then click
   canvas". The ghost follows the cursor and drops where you release.
2. **Everything is direct.** Click a card to select, click again to edit in
   place, drag it by any part that is not a text field, resize from the corner.
3. **Pan is cheap:** space-drag, middle-mouse drag, or two-finger scroll.
   Ctrl+wheel zooms toward the cursor.
4. **Drop anything in.** Images, PDFs, a URL from the address bar, a chunk of
   copied text. It becomes the right kind of card without asking.
5. **Boards inside boards.** A board card opens a fresh canvas; breadcrumbs
   and the left tree get you back.
6. **Projects are the outer ring.** Switching project swaps the whole tree,
   the search scope and the folder on disk.

Undo/redo is snapshot-based (whole-board JSON, capped stack). At the scale of a
hand-arranged board this is far simpler than command diffing and cannot desync.

## Templates

`muse/templates.py` holds a small builder (`Board`) with one method per card
type and a grid helper, so a template is 10 to 20 readable lines rather than a
wall of JSON. Each one returns a spec: elements keyed by short local names,
connectors referencing those names, and nested child boards.

`store.create_from_spec` instantiates a spec depth-first: child boards are
created before the parent's elements so a board card can be handed the real id
of the board it opens. Keys are remapped to fresh ids on the way through, which
is also what keeps column children, connector endpoints and to-do item ids
unique across every copy of a template.

Templates that expect images emit `image` cards with an empty `src`. The canvas
renders those as dashed placeholders, and a dropped image lands *into* the
placeholder under the cursor rather than creating another card.

## Things that bit, worth not repeating

**`[hidden]` loses to any author `display` rule.** The cascade puts author
declarations above the UA sheet regardless of specificity, so `#picker { display:
flex }` silently defeated `<div id="picker" hidden>`. Two full-screen overlays
and the two floating toolbars were therefore always present, swallowing every
click on the canvas. `[hidden] { display: none !important }` sits near the top of
styles.css now and covers the whole class of bug. The same thing in a different
costume made an inline `<svg hidden>` sprite take 155px of layout early on.

**Floating UI inside the canvas container needs excluding from the canvas
pointer handler**, or its own buttons clear the selection before their click
handler runs.

**A dismiss-on-pointerdown listener kills the menu it belongs to.** The context
menu closed on any document pointerdown, including its own, which detached the
button before `click` could fire on it - so every menu item in the app did
nothing at all. The close handler must ignore presses inside the menu. The
generalisation: a popup that closes on `pointerdown` can never contain a
`click` handler.

**`prompt()` and `confirm()` do not work inside the desktop window.** WebView2
dismisses script dialogs when the host does not handle `ScriptDialogOpening`,
so they return null/false with no UI. `dialogs.js` provides `ask()` and
`confirmBox()`; nothing in Muse may call the native ones. They also work
better: the confirm styles its destructive button red, and both explain where
the deleted thing goes.

**`pythonw.exe` has no stdio, and uvicorn's logging dies on it.** `sys.stdout`
and `sys.stderr` are `None` under pythonw, so the server thread threw the
instant it started and the window opened on a port with nothing behind it.
`fix_stdio()` points them at `os.devnull` before anything else runs. Testing
the launcher under `python.exe` hides this completely: test the entry point that
actually ships.

**Wait for the port, do not sleep and hope.** The window now opens only once
something answers on the port, and says so in a message box if it never does,
because a shortcut launch has no console to print to.

**Never run JS from pywebview's `closing` event.** `evaluate_js` there executes
on the GUI thread while the webview is being destroyed and takes the process
down with it. The pause that lets a final save land belongs *after*
`webview.start()` returns, when the GUI loop is over and only the server thread
is left. The page saves itself on `pagehide` and on `blur`, with a 300 ms
debounce behind it, so there is nothing meaningful left to rescue at that point
anyway.

**A port in TIME_WAIT cannot be bound but is still ours to use**, so the free
port check connects rather than binds; otherwise a restart lands on a random
port and any open tab points at the wrong place.

## Moving cards between boards

Elements can carry assets, and assets live in the *board's* folder, so a move is
not just a JSON splice. `POST /boards/{id}/receive` takes the cards plus the id
of the board they came from, copies each `src`/`thumb` into the destination's
assets and rewrites the field, then appends. The client flushes first and
reloads afterwards so the server's copy wins; otherwise the client's in-memory
board would overwrite the freshly appended cards on its next save.

The same route serves both gestures: dragging a selection onto a sidebar board,
and pasting into a different board. Copy puts a `muse-cards:` prefixed payload on
the real system clipboard, so Ctrl+V is handled by the ordinary paste listener
and there is no second, competing shortcut to double-fire.

## Trash

Deleting a board moves its folder to `<project>/.trash/<board id>/` with a
`trash.json` recording title, parent and the delete that removed it. Deleting a
board with children trashes the whole subtree under one group id, and restoring
the parent brings the group back; if the original parent is gone by then, the
board reappears at the top level rather than nowhere. Projects go to
`Trash\<name> <date>`. Nothing in the app calls `rmtree` on a board or
project except emptying the trash.

## Live files

`livefiles.py` + the `live` and `watch` card types. A live card stores an
absolute path and the mtime it last saw; a watch card stores a folder path, a
filter, and the `seen` list of paths it has already noticed.

Freshness is polling, not filesystem watchers: every 4 s (only while the page
is visible) the client stats each card's path. One stat per card on a local
disk is nothing, and it sidesteps watchdog's problems with network shares and
editors that replace-on-save. Thumbnails are cached in `.cache\thumbs`
keyed on path+mtime+size, so a changed file gets a new cache entry and the old
one is simply never asked for again; the client busts the browser's cache by
putting the mtime in the query string.

Auto-add ("add new files to this board") works off the `seen` list. The first
listing after it is switched on only records the baseline - otherwise flipping
the switch would dump the whole folder's history onto the board. Files are
never removed by the watcher; a live card whose file disappears flags
`missing` but stays, because the card position and caption carry meaning even
when the file is gone.

Paths come from a real file dialog (pywebview's when in the desktop window,
tkinter's when in a browser), because the web file input deliberately never
reveals a path. A pasted absolute path is recognised on the canvas and becomes
a live/watch card directly.

## Quick capture

`capture.py`. The hotkey is a real `RegisterHotKey` on a thread with its own
message loop, so it fires from any application. Rather than building a region
picker, firing it presses **Win+Shift+S for the user** - Windows' own snip
already handles multi-monitor and DPI - then watches `GetClipboardSequenceNumber`
and lifts the resulting image off the clipboard into `.inbox`.

The page cannot be written to directly (the client owns the open board and
would clobber a server-side edit on its next save), so captures sit in the
inbox until the open page claims them: a 2.5 s poll calls
`/api/captures/{name}/claim`, which moves the file into the board's assets
atomically - first claimant wins, so two open pages cannot double-pin.

Hotkey choice degrades: `win+shift+t` if the OS allows it, else `ctrl+alt+t`,
overridable via `capture_hotkey` in settings.json. The tray menu displays
whichever armed. Two lessons paid for here: pystray's detached thread is not a
daemon, so `capture.stop()` must run after `webview.start()` returns or the
process outlives its window invisibly; and the synthetic Win+Shift+S needs a
250 ms delay so it does not mix with the keys the user is still holding.

## Present and export

Present mode is CSS plus a step list: `body.presenting` hides the chrome, a
transition on `#world` makes view changes glide, and the step order is derived
at entry - cards clustered into rows by vertical overlap, rows read left to
right. Every drag pans while presenting; editing is simply unreachable.
Navigating into a board card keeps presenting and re-derives the order.

`export.py` renders a board to one static HTML file: absolutely positioned
divs mirroring the canvas CSS, connectors re-drawn with the same bezier maths
ported to Python, every image inlined as a data URI. Live and watch cards are
frozen at their export-time state, which is exactly what a client review wants.
Files land in `Exports` and get revealed in Explorer rather than pushed
through the browser's download machinery, which pywebview handles badly.

## Code cards

`code.py` highlights with Pygments server-side (598 languages) so the export
inherits highlighting and no JS highlighter is vendored. Results cache by
content hash. The card shows a read-only highlighted `<pre>`; double-click swaps
in a plain `<textarea>`, because a caret inside highlight spans is a losing
battle. `paintCode` must NOT bail on `!pre.isConnected`: render() builds a node
and calls the renderer before appending it, so on a cache hit the pre is briefly
detached - gating on connectedness left every re-rendered code card as plain
text.

## Theme

Dark is the default and lives in the `:root` / `:root[data-theme="dark"]` block;
`:root[data-theme="light"]` restores the original paper look. Card colours are
classes (`.el.c-yellow`) not inline styles, so the theme restyles them centrally;
a custom colour is stored as a hex string and applied inline instead. The toggle
persists to localStorage and re-renders so code cards re-highlight in the
matching Pygments style.

## Board icons

A board's icon (an emoji) lives on its `board.json` (source of truth for the
sidebar tree) and is mirrored onto the board *card* element for display. Clicking
the card's icon opens a curated emoji popover; picking one mutates the card and
PATCHes the board so both card and tree stay in step.

## The frontend cache trap

The WebView keeps ES modules in its loader cache; `location.reload()` does not
refetch them, so an updated Muse can run stale JS (this bit hard during dev). A
`no_cache_frontend` middleware sends `Cache-Control: no-cache` on `.js/.css/.html`
so the browser always revalidates. In the preview browser specifically, the
reliable refresh is `fetch(url, {cache:'reload'})` on the changed file, then
navigate.

## Deliberately not in v1

- Multi-user / realtime. Single machine, single window, no locking.
- Auth. Binds 127.0.0.1 only.
- Version history beyond undo. The folder format makes external backup easy;
  that's the answer for now.
- Mobile/touch layout. Desktop pointer assumptions throughout.

## Open questions

- Does a board card want a live thumbnail of its child canvas, or is a colour
  swatch grid enough? (Starting with swatches; thumbnails need offscreen render.)
- Should a project be exportable as a single zip, or is "copy the folder" the
  whole answer? Copying is enough today.
- Moving a board between projects has no UI yet. On disk it is a folder move
  plus a `parent_id` reset, so it is cheap to add when it is actually wanted.
